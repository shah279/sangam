package com.sangam.ui

import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf

/** Destinations. Root tabs + pushable detail screens. */
sealed interface Screen {
    data object Consensus : Screen
    data object Sectors : Screen
    data object BestPicks : Screen
    data object Creators : Screen
    data object Health : Screen
    data class StockDetail(val name: String, val instrumentType: String?) : Screen
    data class CreatorDetail(val channelId: String, val name: String) : Screen
    data class VideoDetail(val videoId: String, val title: String) : Screen
}

class Navigator(start: Screen = Screen.Consensus) {
    private val stack = mutableStateListOf(start)
    val current get() = stack.last()
    val canGoBack get() = stack.size > 1

    fun push(screen: Screen) { stack.add(screen) }
    fun pop() { if (canGoBack) stack.removeAt(stack.lastIndex) }

    /** Switch root tab: reset the stack to that tab. */
    fun selectTab(tab: Screen) {
        stack.clear(); stack.add(tab)
    }
}
