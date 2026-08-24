package com.sangam.ui.screens

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.sangam.data.Repository
import com.sangam.model.Mention
import com.sangam.model.Video
import com.sangam.ui.*
import com.sangam.ui.components.*
import com.sangam.util.relativeDay

@Composable
fun VideoDetailScreen(nav: Navigator, videoId: String, title: String) {
    val state by loadState(videoId) { Repository.video(videoId) to Repository.mentionsForVideo(videoId) }
    val uri = LocalUriHandler.current
    val listState = rememberLazyListState()
    AsyncContent(state) { (video, mentions) ->
        LazyColumn(Modifier.fillMaxSize(), state = listState, contentPadding = PaddingValues(vertical = 8.dp)) {
            item {
                Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(video?.title ?: title, style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
                    Text(relativeDay(video?.publishedAt), style = MaterialTheme.typography.labelMedium)
                    (video?.url)?.let { url ->
                        Button(onClick = { uri.openUri(url) }) { Text("Watch on YouTube") }
                    }
                    video?.summary?.let {
                        Text("Summary", style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Bold)
                        Text(it, style = MaterialTheme.typography.bodyMedium)
                    }
                }
            }
            if (mentions.isNotEmpty()) item {
                Text("Mentions", Modifier.padding(start = 16.dp, top = 8.dp),
                    style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Bold)
            }
            items(mentions) { m -> MentionDetailRow(m) }
        }
    }
}

/** Detail view: shows the LONG note (full detail), unlike list rows. */
@Composable
private fun MentionDetailRow(m: Mention) {
    Card(Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 6.dp)) {
        Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text(m.rawMention ?: "—", fontWeight = FontWeight.SemiBold)
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                m.instrumentType?.let { Pill(it, MaterialTheme.colorScheme.secondary) }
                ActionPill(m.action); ConvictionPill(m.conviction)
            }
            Text(m.longNote ?: m.note ?: "", style = MaterialTheme.typography.bodyMedium)
            m.evidence?.takeIf { it.isNotBlank() }?.let {
                Text("“$it”", style = MaterialTheme.typography.labelSmall)
            }
        }
    }
}
