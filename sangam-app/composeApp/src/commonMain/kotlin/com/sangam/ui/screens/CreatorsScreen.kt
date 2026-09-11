package com.sangam.ui.screens

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.sangam.data.Repository
import com.sangam.model.ScorecardEntry
import com.sangam.ui.*
import com.sangam.ui.components.*
import com.sangam.ui.theme.SangamColors
import com.sangam.util.relativeDay
import kotlin.math.round

@Composable
fun CreatorsScreen(nav: Navigator) {
    var tab by rememberSaveable { mutableStateOf(0) }
    Column(Modifier.fillMaxSize()) {
        TabRow(selectedTabIndex = tab) {
            Tab(selected = tab == 0, onClick = { tab = 0 }, text = { Text("By recency") })
            Tab(selected = tab == 1, onClick = { tab = 1 }, text = { Text("Scorecard") })
        }
        Box(Modifier.weight(1f)) {
            if (tab == 0) CreatorsByRecency(nav) else ScorecardList()
        }
    }
}

@Composable
private fun CreatorsByRecency(nav: Navigator) {
    val listState = rememberLazyListState()
    val state by loadState { Repository.creatorsByRecency() }
    AsyncContent(state) { creators ->
        if (creators.isEmpty()) EmptyHint("No creators yet.")
        else LazyColumn(Modifier.fillMaxSize(), state = listState, contentPadding = PaddingValues(vertical = 8.dp)) {
            items(creators) { (c, lastVideoAt) ->
                Card(Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 6.dp)
                    .clickable { nav.push(Screen.CreatorDetail(c.channelId, c.name)) }) {
                    Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                            Text(c.name, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
                            relativeDay(lastVideoAt).takeIf { it.isNotBlank() }
                                ?.let { Text(it, style = MaterialTheme.typography.labelSmall) }
                        }
                        SourceBadges(c.sourceType, c.isSebiRegistered, c.platform)
                    }
                }
            }
        }
    }
}

/**
 * Forward-return performance on bullish calls: entry = first cached close on
 * or after the call, current = latest cached close (see the creator_scorecard
 * view — computed server-side since it joins against years of price history).
 * Small sample sizes are shown, not hidden — a couple of calls proves little
 * either way, so the count is part of the read, not a footnote.
 */
@Composable
private fun ScorecardList() {
    val listState = rememberLazyListState()
    val state by loadState { Repository.creatorScorecard() }
    AsyncContent(state) { entries ->
        val ranked = remember(entries) { entries.sortedByDescending { it.avgReturnPct ?: Double.NEGATIVE_INFINITY } }
        if (ranked.isEmpty()) {
            EmptyHint("No priced bullish calls yet — needs resolved symbols with cached prices.")
        } else {
            LazyColumn(Modifier.fillMaxSize(), state = listState, contentPadding = PaddingValues(vertical = 8.dp)) {
                items(ranked, key = { it.channelId }) { entry -> ScorecardRow(entry) }
            }
        }
    }
}

@Composable
private fun ScorecardRow(entry: ScorecardEntry) {
    Card(Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 6.dp)) {
        Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Text(entry.creatorName, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
                entry.avgReturnPct?.let {
                    Text(
                        "${if (it >= 0) "+" else ""}${round(it * 100) / 100}%",
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold,
                        color = if (it >= 0) SangamColors.buy else SangamColors.sell,
                    )
                }
            }
            SourceBadges(entry.sourceType, entry.isSebiRegistered, null)
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                Pill("${entry.sampleSize} call${if (entry.sampleSize == 1) "" else "s"}", MaterialTheme.colorScheme.outline)
                entry.hitRatePct?.let { Pill("${round(it * 10) / 10}% hit rate", MaterialTheme.colorScheme.secondary) }
            }
            if (entry.sampleSize < 5) {
                Text(
                    "Small sample — treat with caution until more calls accumulate.",
                    style = MaterialTheme.typography.labelSmall,
                )
            }
        }
    }
}
