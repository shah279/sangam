package com.sangam.ui.screens

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
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
import com.sangam.ui.components.Pill
import com.sangam.ui.theme.SangamColors
import com.sangam.util.relativeDay
import kotlinx.coroutines.launch
import kotlin.math.round

/** Picks added from a Stock screen (or typed in directly here): entry price
 * captured at add-time vs. the latest cached close, so you can review
 * whether it went positive or negative. */
@Composable
fun RadarScreen(nav: Navigator) {
    var refreshKey by remember { mutableStateOf(0) }
    var showAddDialog by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    val state by loadState(refreshKey) {
        val items = Repository.watchlist()
        items to Repository.latestPrices(items.map { it.symbol }.distinct())
    }

    Box(Modifier.fillMaxSize()) {
        AsyncContent(state) { (items, prices) ->
            if (items.isEmpty()) {
                EmptyHint("Add a pick from its Stock screen, or tap + to add a symbol directly.")
            } else {
                LazyColumn(
                    Modifier.fillMaxSize(),
                    contentPadding = PaddingValues(top = 8.dp, bottom = 88.dp),
                ) {
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
        FloatingActionButton(
            onClick = { showAddDialog = true },
            modifier = Modifier.align(Alignment.BottomEnd).padding(16.dp),
        ) { Icon(Icons.Default.Add, contentDescription = "Add symbol to radar") }
    }

    if (showAddDialog) {
        AddSymbolDialog(
            onDismiss = { showAddDialog = false },
            onAdd = { symbol ->
                scope.launch {
                    // May be null for a brand-new symbol never mentioned or added before —
                    // prices.py backfills it on its next run since watchlist symbols are
                    // now part of its pricing universe too.
                    val price = Repository.latestPrices(listOf(symbol))[symbol]?.close
                    Repository.addToWatchlist(symbol, price)
                    showAddDialog = false
                    refreshKey++
                }
            },
        )
    }
}

@Composable
private fun AddSymbolDialog(onDismiss: () -> Unit, onAdd: (String) -> Unit) {
    var symbol by remember { mutableStateOf("") }
    var exchange by remember { mutableStateOf("NSE") }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Add to radar") },
        text = {
            Column {
                Text(
                    "Enter the ticker symbol (e.g. RELIANCE, TCS) — not the company name.",
                    style = MaterialTheme.typography.bodySmall,
                )
                Spacer(Modifier.height(8.dp))
                OutlinedTextField(
                    value = symbol,
                    onValueChange = { symbol = it.uppercase() },
                    label = { Text("Symbol") },
                    singleLine = true,
                )
                Spacer(Modifier.height(8.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    FilterChip(selected = exchange == "NSE", onClick = { exchange = "NSE" }, label = { Text("NSE") })
                    FilterChip(selected = exchange == "BSE", onClick = { exchange = "BSE" }, label = { Text("BSE") })
                }
                Spacer(Modifier.height(4.dp))
                Text(
                    "Only pick BSE if this stock has no NSE listing.",
                    style = MaterialTheme.typography.labelSmall,
                )
            }
        },
        confirmButton = {
            TextButton(
                onClick = {
                    val trimmed = symbol.trim()
                    onAdd(if (exchange == "BSE") "BSE:$trimmed" else trimmed)
                },
                enabled = symbol.isNotBlank(),
            ) { Text("Add") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } },
    )
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
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text(displaySymbol(item.symbol), style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
                    if (item.symbol.startsWith("BSE:")) Pill("BSE", MaterialTheme.colorScheme.secondary)
                }
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

/** watchlist.symbol carries a "BSE:" prefix for BSE-only picks (see prices.py's
 * yahoo_ticker); strip it for display, showing a badge instead. */
private fun displaySymbol(symbol: String): String = symbol.removePrefix("BSE:")
