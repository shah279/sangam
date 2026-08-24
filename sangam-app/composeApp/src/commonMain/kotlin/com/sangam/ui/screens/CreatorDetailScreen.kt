package com.sangam.ui.screens

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.KeyboardArrowDown
import androidx.compose.material.icons.filled.KeyboardArrowUp
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.sangam.data.Repository
import com.sangam.model.Mention
import com.sangam.model.Video
import com.sangam.ui.*
import com.sangam.ui.components.*
import com.sangam.util.DateFilter
import com.sangam.util.relativeDay

@Composable
fun CreatorDetailScreen(nav: Navigator, channelId: String, name: String) {
    var filterName by rememberSaveable { mutableStateOf(DateFilter.ALL.name) }
    val filter = DateFilter.valueOf(filterName)
    var recosOpen by rememberSaveable { mutableStateOf(true) }
    var videosOpen by rememberSaveable { mutableStateOf(false) }   // collapsed by default — the long one
    val listState = rememberLazyListState()
    val recos by loadState(channelId) { Repository.mentionsForChannel(channelId) }
    val vids by loadState(channelId) { Repository.videosForChannel(channelId) }

    val calls = (recos as? Async.Success)?.data
        ?.filter { it.action != null && it.action != "neutral" }
        ?.ifEmpty { (recos as Async.Success).data } ?: emptyList()
    val videosFiltered = (vids as? Async.Success)?.data?.filter { filter.matches(it.publishedAt) } ?: emptyList()

    LazyColumn(Modifier.fillMaxSize(), state = listState, contentPadding = PaddingValues(bottom = 16.dp)) {
        item { Text(name, Modifier.padding(16.dp), style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold) }
        item { DateFilterRow(filter) { filterName = it.name } }

        // --- Stock recommendations (collapsible) ---
        item { CollapsibleHeader("Stock recommendations", calls.size, recosOpen) { recosOpen = !recosOpen } }
        if (recosOpen) {
            when (recos) {
                is Async.Loading -> item { LinearProgressIndicator(Modifier.fillMaxWidth().padding(16.dp)) }
                is Async.Error -> item { Text("Couldn't load recommendations", Modifier.padding(16.dp)) }
                is Async.Success ->
                    if (calls.isEmpty()) item { EmptyHint("No stock mentions yet.") }
                    else items(calls) { m -> RecoRow(m) { nav.push(Screen.StockDetail(m.rawMention ?: "", m.instrumentType)) } }
            }
        }

        // --- Recent videos (collapsible; collapsed by default) ---
        item { CollapsibleHeader("Recent videos", videosFiltered.size, videosOpen) { videosOpen = !videosOpen } }
        if (videosOpen) {
            when (vids) {
                is Async.Loading -> item { LinearProgressIndicator(Modifier.fillMaxWidth().padding(16.dp)) }
                is Async.Error -> item { Text("Couldn't load videos", Modifier.padding(16.dp)) }
                is Async.Success ->
                    if (videosFiltered.isEmpty()) item { EmptyHint("No videos in this range.") }
                    else items(videosFiltered) { v -> VideoRow(v) { nav.push(Screen.VideoDetail(v.videoId, v.title ?: "")) } }
            }
        }
    }
}

@Composable
private fun CollapsibleHeader(title: String, count: Int, expanded: Boolean, onToggle: () -> Unit) {
    Row(
        Modifier.fillMaxWidth().clickable(onClick = onToggle).padding(horizontal = 16.dp, vertical = 12.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically
    ) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(title, style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Bold)
            if (count > 0) Text("($count)", style = MaterialTheme.typography.labelMedium)
        }
        Icon(
            if (expanded) Icons.Default.KeyboardArrowUp else Icons.Default.KeyboardArrowDown,
            contentDescription = if (expanded) "Collapse" else "Expand"
        )
    }
    HorizontalDivider()
}

@Composable
private fun RecoRow(m: Mention, onClick: () -> Unit) {
    Card(Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 6.dp).clickable(onClick = onClick)) {
        Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text(m.rawMention ?: "—", fontWeight = FontWeight.SemiBold)
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) { ActionPill(m.action); ConvictionPill(m.conviction) }
            m.note?.let { Text(it, style = MaterialTheme.typography.bodySmall) }
            dateLine(m.video?.publishedAt)?.let { Text(it, style = MaterialTheme.typography.labelSmall) }
        }
    }
}

@Composable
private fun VideoRow(v: Video, onClick: () -> Unit) {
    Card(Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 6.dp).clickable(onClick = onClick)) {
        Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text(v.title ?: "—", fontWeight = FontWeight.SemiBold, maxLines = 2)
            dateLine(v.publishedAt)?.let { Text(it, style = MaterialTheme.typography.labelSmall) }
            v.summary?.takeIf { it.isNotBlank() && it != "no stock discussion" }
                ?.let { Text(it.lineSequence().first(), style = MaterialTheme.typography.bodySmall, maxLines = 2) }
        }
    }
}

/** Guaranteed date text: friendly label, else the raw yyyy-mm-dd, else null. */
private fun dateLine(iso: String?): String? {
    val r = relativeDay(iso)
    if (r.isNotBlank()) return r
    return iso?.take(10)?.takeIf { it.isNotBlank() }
}
