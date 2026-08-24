package com.sangam.util

import kotlinx.datetime.Clock
import kotlinx.datetime.Instant
import kotlinx.datetime.TimeZone
import kotlinx.datetime.toLocalDateTime

private val tz get() = TimeZone.currentSystemDefault()

fun parseInstant(iso: String?): Instant? =
    iso?.let { runCatching { Instant.parse(it) }.getOrNull() }

/** "13 Aug 2026" */
fun shortDate(iso: String?): String {
    val inst = parseInstant(iso) ?: return iso?.take(10) ?: ""
    val d = inst.toLocalDateTime(tz).date
    val month = d.month.name.lowercase().replaceFirstChar { it.uppercase() }.take(3)
    return "${d.dayOfMonth} $month ${d.year}"
}

/** "Today" / "Yesterday" / "3 days ago" / "13 Aug 2026" */
fun relativeDay(iso: String?): String {
    val inst = parseInstant(iso) ?: return iso?.take(10) ?: ""
    val today = Clock.System.now().toLocalDateTime(tz).date
    val d = inst.toLocalDateTime(tz).date
    val diff = today.toEpochDays() - d.toEpochDays()
    return when {
        diff == 0 -> "Today"
        diff == 1 -> "Yesterday"
        diff in 2..6 -> "$diff days ago"
        else -> shortDate(iso)
    }
}

enum class DateFilter(val label: String) {
    ALL("All"), TODAY("Today"), YESTERDAY("Yesterday"), WEEK("7 days");

    fun matches(iso: String?): Boolean {
        if (this == ALL) return true
        val inst = parseInstant(iso) ?: return false
        val today = Clock.System.now().toLocalDateTime(tz).date
        val d = inst.toLocalDateTime(tz).date
        val diff = today.toEpochDays() - d.toEpochDays()
        return when (this) {
            ALL -> true
            TODAY -> diff == 0
            YESTERDAY -> diff == 1
            WEEK -> diff in 0..6
        }
    }
}
