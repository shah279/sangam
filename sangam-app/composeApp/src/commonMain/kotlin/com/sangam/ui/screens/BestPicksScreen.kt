package com.sangam.ui.screens

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.material3.Tab
import androidx.compose.material3.TabRow
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.sangam.data.Repository
import com.sangam.data.bestPicks
import com.sangam.data.buildConsensus
import com.sangam.ui.*
import com.sangam.ui.components.DateFilterRow
import com.sangam.util.DateFilter

/**
 * Picks & Radar tab: ranked net-bullish multi-creator picks for a timeframe,
 * plus the personal watchlist those picks get added to for later review.
 * Grouped under one tab rather than two more bottom-nav items.
 */
@Composable
fun BestPicksScreen(nav: Navigator) {
    var tab by rememberSaveable { mutableStateOf(0) }
    Column(Modifier.fillMaxSize()) {
        TabRow(selectedTabIndex = tab) {
            Tab(selected = tab == 0, onClick = { tab = 0 }, text = { Text("Best picks") })
            Tab(selected = tab == 1, onClick = { tab = 1 }, text = { Text("My radar") })
        }
        Box(Modifier.weight(1f)) {
            if (tab == 0) BestPicksList(nav) else RadarScreen(nav)
        }
    }
}

@Composable
private fun BestPicksList(nav: Navigator) {
    var filterName by rememberSaveable { mutableStateOf(DateFilter.WEEK.name) }
    val filter = DateFilter.valueOf(filterName)
    val listState = rememberLazyListState()
    val state by loadState { Repository.recentMentions() }

    Column(Modifier.fillMaxSize()) {
        DateFilterRow(filter) { filterName = it.name }
        AsyncContent(state) { mentions ->
            val items = remember(mentions, filter) {
                bestPicks(
                    buildConsensus(
                        mentions.filter { it.instrumentType != "sector" && filter.matches(it.video?.publishedAt) }
                    )
                )
            }
            if (items.isEmpty()) EmptyHint("No net-bullish, multi-creator picks in this range yet.")
            else LazyColumn(Modifier.fillMaxSize(), state = listState, contentPadding = PaddingValues(vertical = 8.dp)) {
                items(items) { item -> ConsensusRow(item) { nav.push(Screen.StockDetail(item.name, item.instrumentType)) } }
            }
        }
    }
}
