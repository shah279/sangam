package com.sangam.model

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class Channel(
    @SerialName("channel_id") val channelId: String,
    val name: String,
    val handle: String? = null,
    @SerialName("source_type") val sourceType: String? = null,
    @SerialName("is_sebi_registered") val isSebiRegistered: Boolean? = null,
    val platform: String? = "youtube",
    val active: Boolean? = true,
)

@Serializable
data class Video(
    @SerialName("video_id") val videoId: String,
    @SerialName("channel_id") val channelId: String? = null,
    val title: String? = null,
    val summary: String? = null,
    val url: String? = null,
    @SerialName("published_at") val publishedAt: String? = null,
    @SerialName("is_short") val isShort: Boolean? = false,
    @SerialName("transcript_status") val transcriptStatus: String? = null,
)

@Serializable
data class MentionChannel(
    val name: String? = null,
    @SerialName("source_type") val sourceType: String? = null,
    @SerialName("is_sebi_registered") val isSebiRegistered: Boolean? = null,
    val platform: String? = "youtube",
)

@Serializable
data class MentionVideo(
    val title: String? = null,
    val url: String? = null,
    @SerialName("published_at") val publishedAt: String? = null,
    @SerialName("channel_id") val channelId: String? = null,
    val channel: MentionChannel? = null,
)

@Serializable
data class Mention(
    val id: Long? = null,
    @SerialName("video_id") val videoId: String,
    @SerialName("raw_mention") val rawMention: String? = null,
    @SerialName("resolved_symbol") val resolvedSymbol: String? = null,
    @SerialName("instrument_type") val instrumentType: String? = null,
    val action: String? = null,
    val conviction: Int? = null,
    val note: String? = null,
    @SerialName("long_note") val longNote: String? = null,
    val evidence: String? = null,
    val source: String? = null,
    val video: MentionVideo? = null,
)

@Serializable
data class ChannelVideoDate(
    @SerialName("channel_id") val channelId: String? = null,
    @SerialName("published_at") val publishedAt: String? = null,
)

@Serializable
data class Run(
    val id: Long? = null,
    @SerialName("started_at") val startedAt: String? = null,
    @SerialName("finished_at") val finishedAt: String? = null,
    val status: String? = null,
    @SerialName("new_videos") val newVideos: Int? = 0,
    val transcribed: Int? = 0,
    val mentions: Int? = 0,
    val error: String? = null,
)

data class ConsensusItem(
    val name: String,
    val instrumentType: String?,
    val channels: Int,
    val mentions: Int,
    val avgConviction: Double,
    val topConviction: Int,
    val actionCounts: Map<String, Int>,
    val sampleNote: String?,
    val latestAt: String? = null,   // most recent mention's video publish time (ISO)
)
