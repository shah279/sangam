package com.sangam.ui.screens

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.sangam.data.Repository
import com.sangam.model.Run
import com.sangam.ui.*
import com.sangam.ui.components.Pill
import com.sangam.ui.theme.SangamColors

@Composable
fun HealthScreen(nav: Navigator) {
    val listState = rememberLazyListState()
    val state by loadState { Repository.runs() }
    AsyncContent(state) { runs ->
        if (runs.isEmpty()) EmptyHint("No runs recorded yet.")
        else LazyColumn(Modifier.fillMaxSize(), state = listState, contentPadding = PaddingValues(vertical = 8.dp)) {
            item {
                val last = runs.first()
                Card(Modifier.fillMaxWidth().padding(12.dp)) {
                    Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        Text("Last run", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
                        StatusPill(last.status)
                        Text(last.finishedAt?.replace("T", "  ")?.take(19) ?: "—",
                            style = MaterialTheme.typography.bodyMedium)
                        Text("${last.newVideos} new · ${last.transcribed} transcribed · ${last.mentions} mentions",
                            style = MaterialTheme.typography.bodySmall)
                        last.error?.let { Text("Error: $it", style = MaterialTheme.typography.bodySmall, color = SangamColors.error) }
                    }
                }
            }
            items(runs) { r -> RunRow(r) }
        }
    }
}

@Composable
private fun StatusPill(status: String?) {
    val ok = status == "success"
    Pill(if (ok) "✓ success" else (status ?: "unknown"), if (ok) SangamColors.ok else SangamColors.error)
}

@Composable
private fun RunRow(r: Run) {
    ListItem(
        headlineContent = { Text(r.finishedAt?.replace("T", "  ")?.take(19) ?: "—") },
        supportingContent = {
            Column {
                Text("${r.newVideos} new · ${r.transcribed} transcribed · ${r.mentions} mentions",
                    style = MaterialTheme.typography.bodySmall)
                r.error?.let { Text("Error: $it", style = MaterialTheme.typography.labelSmall, color = SangamColors.error) }
            }
        },
        trailingContent = { StatusPill(r.status) },
    )
    HorizontalDivider()
}
