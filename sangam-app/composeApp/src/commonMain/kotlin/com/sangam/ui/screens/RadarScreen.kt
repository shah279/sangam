package com.sangam.ui.screens

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Close
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.sangam.data.Repository
import com.sangam.model.WatchlistItem
import com.sangam.ui.*
import com.sangam.ui.theme.SangamColors
import com.sangam.util.relativeDay
import kotlinx.coroutines.launch
import kotlin.math.round

/** Picks added from a Stock screen: entry price captured at add-time vs. the
 * latest cached close, so you can review whether it went positive or negative. */
@Composable
fun RadarScreen(nav: Navigator) {
    var refreshKey by remember { mutableStateOf(0) }
    val scope = rememberCoroutineScope()
    val state by loadState(refreshKey) {
        val items = Repository.watchlist()
        items to Repository.latestPrices(items.map { it.symbol }.distinct())
    }

    AsyncContent(state) { (items, prices) ->
        if (items.isEmpty()) {
            EmptyHint("Add a pick from its Stock screen to track it here.")
        } else {
            LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(vertical = 8.dp)) {
                items(items, key = { it.id ?: it.symbol }) { item ->
                    RadarRow(item, prices[item.symbol]?.close) {
                        scope.launch {
                            item.id?.let { Repository.removeFromWatchlist(it) }
                            refreshKey++
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun RadarRow(item: WatchlistItem, currentPrice: Double?, onRemove: () -> Unit) {
    val entry = item.entryPrice
    val change = if (entry != null && entry != 0.0 && currentPrice != null) {
        (currentPrice - entry) / entry * 100
    } else null

    Card(Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 6.dp)) {
        Row(
            Modifier.padding(14.dp).fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
        ) {
            Column {
                Text(item.symbol, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
                Text(
                    "Added ${relativeDay(item.addedAt)}" + (entry?.let { " · entry ₹${round(it * 100) / 100}" } ?: ""),
                    style = MaterialTheme.typography.labelSmall,
                )
                item.note?.let { Text(it, style = MaterialTheme.typography.bodySmall) }
            }
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(horizontalAlignment = Alignment.End) {
                    Text(
                        currentPrice?.let { "₹${round(it * 100) / 100}" } ?: "no price yet",
                        style = MaterialTheme.typography.bodyMedium,
                    )
                    change?.let {
                        Text(
                            "${if (it >= 0) "+" else ""}${round(it * 100) / 100}%",
                            color = if (it >= 0) SangamColors.buy else SangamColors.sell,
                            fontWeight = FontWeight.SemiBold,
                        )
                    }
                }
                IconButton(onClick = onRemove) {
                    Icon(Icons.Default.Close, contentDescription = "Remove from radar")
                }
            }
        }
    }
}
