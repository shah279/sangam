package com.sangam.ui.screens

import androidx.compose.foundation.clickable
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
import com.sangam.ui.*
import com.sangam.ui.components.*
import com.sangam.util.relativeDay

@Composable
fun CreatorsScreen(nav: Navigator) {
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
