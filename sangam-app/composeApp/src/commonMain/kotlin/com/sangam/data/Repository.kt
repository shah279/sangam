package com.sangam.data

import com.sangam.model.*
import com.sangam.net.Supabase
import io.ktor.http.encodeURLQueryComponent
import com.sangam.util.parseInstant
import kotlinx.datetime.Clock

object Repository {

    private const val MENTION_EMBED =
        "video:videos(title,url,published_at,channel_id,channel:channels(name,source_type,is_sebi_registered,platform))"

    suspend fun runs(): List<Run> =
        Supabase.select("runs", "select=*&order=id.desc&limit=40")

    suspend fun health(): HealthSnapshot {
        val states: List<PipelineState> =
            Supabase.select("videos", "select=transcript_status,extract_status&limit=2000")
        val queued = setOf("pending", "retry")
        return HealthSnapshot(
            runs = runs(),
            totalVideos = states.size,
            captionBacklog = states.count { it.transcriptStatus in queued },
            extractionBacklog = states.count { it.extractStatus in queued },
            terminalErrors = states.count {
                it.transcriptStatus == "error" || it.extractStatus == "error"
            },
        )
    }

    private const val TTL_MS = 120_000L
    private fun now() = Clock.System.now().toEpochMilliseconds()
    private var mentionsCache: Pair<Long, List<Mention>>? = null
    private var channelsCache: Pair<Long, List<Channel>>? = null

    suspend fun channels(): List<Channel> {
        channelsCache?.let { if (now() - it.first < TTL_MS) return it.second }
        val data: List<Channel> = Supabase.select("channels", "select=*&order=name")
        channelsCache = now() to data
        return data
    }

    suspend fun videosForChannel(channelId: String): List<Video> =
        Supabase.select("videos", "channel_id=eq.$channelId&select=*&order=published_at.desc&limit=60")

    suspend fun video(videoId: String): Video? =
        Supabase.select<Video>("videos", "video_id=eq.$videoId&select=*&limit=1").firstOrNull()

    suspend fun mentionsForVideo(videoId: String): List<Mention> =
        Supabase.select("mentions", "video_id=eq.$videoId&select=*,$MENTION_EMBED")

    /** All mentions across a creator's videos = that creator's stock recommendations. */
    suspend fun mentionsForChannel(channelId: String): List<Mention> {
        val ids = videosForChannel(channelId).map { it.videoId }
        if (ids.isEmpty()) return emptyList()
        val inList = ids.joinToString(",")
        return Supabase.select<Mention>("mentions", "video_id=in.($inList)&select=*,$MENTION_EMBED").latestFirst()
    }

    suspend fun mentionsForStock(name: String): List<Mention> {
        val n = name.encodeURLQueryComponent()
        return Supabase.select<Mention>(
            "mentions",
            "or=(resolved_symbol.eq.$n,raw_mention.eq.$n)&select=*,$MENTION_EMBED"
        ).latestFirst()
    }

    // Sort mentions newest-first by the source video's publish date.
    private fun List<Mention>.latestFirst(): List<Mention> =
        sortedByDescending { parseInstant(it.video?.publishedAt)?.toEpochMilliseconds() ?: 0L }

    /** Raw recent mentions (with creator embedded) — grouped in the UI so date
     *  filters can be applied before aggregating. */
    suspend fun recentMentions(): List<Mention> {
        mentionsCache?.let { if (now() - it.first < TTL_MS) return it.second }
        val data: List<Mention> =
            Supabase.select("mentions", "select=*,$MENTION_EMBED&order=created_at.desc&limit=1000")
        mentionsCache = now() to data
        return data
    }

    /** Latest cached close per symbol (from the `latest_prices` view), keyed by symbol. */
    suspend fun latestPrices(symbols: List<String>): Map<String, PricePoint> {
        if (symbols.isEmpty()) return emptyMap()
        val inList = symbols.joinToString(",") { it.encodeURLQueryComponent() }
        val points: List<PricePoint> = Supabase.select("latest_prices", "symbol=in.($inList)&select=*")
        return points.associateBy { it.symbol }
    }

    suspend fun watchlist(): List<WatchlistItem> =
        Supabase.select("watchlist", "select=*&order=added_at.desc")

    suspend fun addToWatchlist(symbol: String, entryPrice: Double?, note: String? = null): WatchlistItem =
        Supabase.insert<NewWatchlistItem, WatchlistItem>("watchlist", NewWatchlistItem(symbol, entryPrice, note)).first()

    suspend fun removeFromWatchlist(id: Long) = Supabase.delete("watchlist", "id=eq.$id")

    /** Creators sorted by their most recent published video (most active on top). */
    suspend fun creatorsByRecency(): List<Pair<Channel, String?>> {
        val chans = channels()
        val recent: List<ChannelVideoDate> =
            Supabase.select("videos", "select=channel_id,published_at&order=published_at.desc&limit=1500")
        val latest = recent.groupBy { it.channelId }
            .mapValues { (_, vs) -> vs.maxByOrNull { parseInstant(it.publishedAt)?.toEpochMilliseconds() ?: 0L }?.publishedAt }
        return chans.map { it to latest[it.channelId] }
            .sortedByDescending { parseInstant(it.second)?.toEpochMilliseconds() ?: 0L }
    }
}

private val GENERIC_INSTRUMENT_MENTIONS = setOf(
    "etf", "etfs", "index fund", "mutual fund", "mutual funds", "sip",
    "stock market", "active etfs", "passive funds", "global etfs",
)

/** Pure: group mentions into a cross-creator consensus (call after date-filtering). */
fun buildConsensus(mentions: List<Mention>): List<ConsensusItem> =
    mentions
        .filter {
            !it.rawMention.isNullOrBlank() &&
                it.rawMention.trim().lowercase() !in GENERIC_INSTRUMENT_MENTIONS &&
                it.source != "description" &&
                (it.confidence == null || it.confidence >= 0.55)
        }
        .groupBy { (it.resolvedSymbol ?: it.rawMention!!).trim() to it.instrumentType }
        .map { (key, ms) ->
            val creatorMentions = ms.groupBy {
                it.video?.channelId ?: "video:${it.videoId}"
            }.values.mapNotNull { creatorRows ->
                creatorRows.maxWithOrNull(
                    compareBy<Mention> { it.confidence ?: 0.0 }
                        .thenBy { it.conviction ?: 0 }
                        .thenBy {
                            parseInstant(it.video?.publishedAt)?.toEpochMilliseconds() ?: 0L
                        }
                )
            }
            val convictions = creatorMentions.mapNotNull { it.conviction }
            ConsensusItem(
                name = key.first,
                instrumentType = key.second,
                channels = creatorMentions.size,
                mentions = ms.size,
                avgConviction = if (convictions.isEmpty()) 0.0 else convictions.average(),
                topConviction = convictions.maxOrNull() ?: 0,
                actionCounts = creatorMentions.mapNotNull { it.action }.groupingBy { it }.eachCount(),
                sampleNote = creatorMentions.maxByOrNull {
                    parseInstant(it.video?.publishedAt)?.toEpochMilliseconds() ?: 0L
                }?.note,
                latestAt = ms.mapNotNull { it.video?.publishedAt }
                    .maxByOrNull { parseInstant(it)?.toEpochMilliseconds() ?: 0L },
            )
        }
        .sortedWith(compareByDescending<ConsensusItem> { it.channels }
            .thenByDescending { it.avgConviction })
