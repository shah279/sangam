package com.sangam.ui.screens

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.sangam.data.Repository
import com.sangam.model.Mention
import com.sangam.ui.*
import com.sangam.ui.components.*
import com.sangam.util.relativeDay
import kotlinx.coroutines.launch
import kotlin.math.round

@Composable
fun StockDetailScreen(nav: Navigator, name: String, instrumentType: String?) {
    val listState = rememberLazyListState()
    val scope = rememberCoroutineScope()
    val state by loadState(name) { Repository.mentionsForStock(name) }
    val priceState by loadState(name) { Repository.latestPrices(listOf(name))[name] }
    var addedNote by remember(name) { mutableStateOf<String?>(null) }

    AsyncContent(state) { mentions ->
        LazyColumn(Modifier.fillMaxSize(), state = listState, contentPadding = PaddingValues(vertical = 8.dp)) {
            item {
                Column(Modifier.padding(16.dp)) {
                    Text(name, style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
                    instrumentType?.let { Pill(it, MaterialTheme.colorScheme.secondary) }
                    Spacer(Modifier.height(4.dp))
                    Text("${mentions.size} mentions across ${mentions.mapNotNull { it.video?.channelId }.distinct().size} channels",
                        style = MaterialTheme.typography.labelMedium)
                    Spacer(Modifier.height(8.dp))
                    val price = (priceState as? Async.Success)?.data?.close
                    Button(
                        enabled = price != null && addedNote == null,
                        onClick = {
                            scope.launch {
                                Repository.addToWatchlist(name, price)
                                addedNote = "Added to radar at ₹${price?.let { round(it * 100) / 100 }}"
                            }
                        },
                    ) { Text(addedNote ?: if (price == null) "No price cached yet" else "Add to radar") }
                }
            }
            items(mentions) { m -> MentionByCreatorRow(m) { m.videoId.let { nav.push(Screen.VideoDetail(it, m.video?.title ?: "")) } } }
        }
    }
}

/** A stock's take from one creator: who said it, action, conviction, short note. */
@Composable
fun MentionByCreatorRow(m: Mention, onClick: () -> Unit) {
    Card(Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 6.dp).clickable(onClick = onClick)) {
        Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text(m.video?.channel?.name ?: "Unknown creator", fontWeight = FontWeight.SemiBold)
            SourceBadges(m.video?.channel?.sourceType, m.video?.channel?.isSebiRegistered, m.video?.channel?.platform)
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                ActionPill(m.action); ConvictionPill(m.conviction)
            }
            // short note only (long note lives on the Video detail screen)
            m.note?.let { Text(it, style = MaterialTheme.typography.bodyMedium) }
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                m.video?.title?.let { Text(it, style = MaterialTheme.typography.labelSmall, maxLines = 1, modifier = Modifier.weight(1f)) }
                Text(relativeDay(m.video?.publishedAt), style = MaterialTheme.typography.labelSmall)
            }
        }
    }
}
