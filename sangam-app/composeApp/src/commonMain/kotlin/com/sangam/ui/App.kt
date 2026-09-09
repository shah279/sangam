package com.sangam.ui

import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.BarChart
import androidx.compose.material.icons.filled.Category
import androidx.compose.material.icons.filled.HealthAndSafety
import androidx.compose.material.icons.filled.People
import androidx.compose.material.icons.filled.Star
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveableStateHolder
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import com.sangam.ui.screens.*
import com.sangam.ui.theme.SangamTheme

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun App() {
    SangamTheme {
        val nav = remember { Navigator(Screen.Consensus) }
        val stateHolder = rememberSaveableStateHolder()
        val current = nav.current
        // OS back / swipe: pop the in-app stack instead of leaving the app.
        SystemBackHandler(enabled = nav.canGoBack) { nav.pop() }

        Scaffold(
            topBar = {
                TopAppBar(
                    title = { Text(titleFor(current)) },
                    navigationIcon = {
                        if (nav.canGoBack) IconButton(onClick = { nav.pop() }) {
                            Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Back")
                        }
                    }
                )
            },
            bottomBar = {
                NavigationBar {
                    tab(nav, current, Screen.Consensus, "Stocks", Icons.Default.BarChart)
                    tab(nav, current, Screen.Sectors, "Sectors", Icons.Default.Category)
                    tab(nav, current, Screen.BestPicks, "Best picks", Icons.Default.Star)
                    tab(nav, current, Screen.Creators, "Creators", Icons.Default.People)
                    tab(nav, current, Screen.Health, "Health", Icons.Default.HealthAndSafety)
                }
            }
        ) { padding ->
            androidx.compose.foundation.layout.Box(Modifier.padding(padding)) {
                // Preserve each screen's scroll + filter/sort state across navigation.
                stateHolder.SaveableStateProvider(keyFor(current)) {
                    when (val s = current) {
                        Screen.Consensus -> StocksScreen(nav)
                        Screen.Sectors -> SectorsScreen(nav)
                        Screen.BestPicks -> BestPicksScreen(nav)
                        Screen.Creators -> CreatorsScreen(nav)
                        Screen.Health -> HealthScreen(nav)
                        is Screen.StockDetail -> StockDetailScreen(nav, s.name, s.instrumentType)
                        is Screen.CreatorDetail -> CreatorDetailScreen(nav, s.channelId, s.name)
                        is Screen.VideoDetail -> VideoDetailScreen(nav, s.videoId, s.title)
                    }
                }
            }
        }
    }
}

@Composable
private fun RowScope.tab(nav: Navigator, current: Screen, tab: Screen, label: String, icon: ImageVector) {
    NavigationBarItem(
        selected = current == tab,
        onClick = { nav.selectTab(tab) },
        icon = { Icon(icon, contentDescription = label) },
        label = { Text(label) }
    )
}

private fun titleFor(s: Screen): String = when (s) {
    Screen.Consensus -> "Sangam · Stocks"
    Screen.Sectors -> "Sectors"
    Screen.BestPicks -> "Best picks"
    Screen.Creators -> "Creators"
    Screen.Health -> "Fetch health"
    is Screen.StockDetail -> s.name
    is Screen.CreatorDetail -> s.name
    is Screen.VideoDetail -> "Video"
}

private fun keyFor(s: Screen): String = when (s) {
    Screen.Consensus -> "stocks"
    Screen.Sectors -> "sectors"
    Screen.BestPicks -> "best_picks"
    Screen.Creators -> "creators"
    Screen.Health -> "health"
    is Screen.StockDetail -> "stock:${s.name}"
    is Screen.CreatorDetail -> "creator:${s.channelId}"
    is Screen.VideoDetail -> "video:${s.videoId}"
}
