package com.sangam.ui.screens

import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.sangam.data.Repository
import com.sangam.data.buildConsensus
import com.sangam.model.ConsensusItem
import com.sangam.ui.*
import com.sangam.ui.components.*
import com.sangam.util.DateFilter
import com.sangam.util.parseInstant
import kotlin.math.round

enum class SortMode(val label: String) {
    LATEST("Latest"), CHANNELS("Channels"), AVG("Avg conviction"), MENTIONS("Mentions")
}

@Composable fun StocksScreen(nav: Navigator) =
    ConsensusScreenBody(nav, { it != "sector" }, "No stocks in this range yet.", SortMode.LATEST)

@Composable fun SectorsScreen(nav: Navigator) =
    ConsensusScreenBody(nav, { it == "sector" }, "No sectors in this range yet.", SortMode.LATEST)

@Composable
private fun ConsensusScreenBody(
    nav: Navigator,
    typeAllowed: (String?) -> Boolean,
    emptyText: String,
    defaultSort: SortMode,
) {
    // rememberSaveable so filter/sort survive navigating into a detail and back.
    var filterName by rememberSaveable { mutableStateOf(DateFilter.ALL.name) }
    var sortName by rememberSaveable { mutableStateOf(defaultSort.name) }
    val filter = DateFilter.valueOf(filterName)
    val sort = SortMode.valueOf(sortName)
    val listState = rememberLazyListState()   // persisted scroll position
    val state by loadState { Repository.recentMentions() }

    Column(Modifier.fillMaxSize()) {
        DateFilterRow(filter) { filterName = it.name }
        SortRow(sort) { sortName = it.name }
        AsyncContent(state) { mentions ->
            val items = remember(mentions, filter, sort) {
                buildConsensus(
                    mentions.filter { typeAllowed(it.instrumentType) && filter.matches(it.video?.publishedAt) }
                ).let { list ->
                    when (sort) {
                        SortMode.CHANNELS -> list
                        SortMode.AVG -> list.sortedByDescending { it.avgConviction }
                        SortMode.MENTIONS -> list.sortedByDescending { it.mentions }
                        SortMode.LATEST -> list.sortedByDescending {
                            parseInstant(it.latestAt)?.toEpochMilliseconds() ?: 0L
                        }
                    }
                }
            }
            if (items.isEmpty()) EmptyHint(emptyText)
            else LazyColumn(Modifier.fillMaxSize(), state = listState, contentPadding = PaddingValues(vertical = 8.dp)) {
                items(items) { item -> ConsensusRow(item) { nav.push(Screen.StockDetail(item.name, item.instrumentType)) } }
            }
        }
    }
}

@Composable
private fun SortRow(selected: SortMode, onSelect: (SortMode) -> Unit) {
    Row(
        Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()).padding(horizontal = 12.dp),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Text("Sort:", style = MaterialTheme.typography.labelMedium)
        SortMode.entries.forEach { m ->
            FilterChip(selected = selected == m, onClick = { onSelect(m) }, label = { Text(m.label) })
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun ConsensusRow(item: ConsensusItem, onClick: () -> Unit) {
    Card(Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 6.dp).clickable(onClick = onClick)) {
        Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Text(item.name, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
                Text("${item.channels} channels", style = MaterialTheme.typography.labelMedium)
            }
            FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                item.instrumentType?.let { Pill(it, MaterialTheme.colorScheme.secondary) }
                Pill("avg ${round(item.avgConviction * 10) / 10}/5", MaterialTheme.colorScheme.primary)
                Pill("${item.mentions} mentions", MaterialTheme.colorScheme.outline)
                com.sangam.util.relativeDay(item.latestAt).takeIf { it.isNotBlank() }
                    ?.let { Pill(it, MaterialTheme.colorScheme.outline, filled = false) }
            }
            if (item.actionCounts.isNotEmpty()) ActionBar(item.actionCounts)
            item.sampleNote?.let { Text(it, style = MaterialTheme.typography.bodySmall, maxLines = 2) }
        }
    }
}

@Composable
fun EmptyHint(text: String) {
    Box(Modifier.fillMaxSize().padding(24.dp), contentAlignment = Alignment.Center) {
        Text(text, style = MaterialTheme.typography.bodyMedium)
    }
}
