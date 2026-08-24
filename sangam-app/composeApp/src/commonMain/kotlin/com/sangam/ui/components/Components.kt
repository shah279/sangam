package com.sangam.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.sangam.ui.theme.SangamColors

@Composable
fun Pill(text: String, color: Color, filled: Boolean = true) {
    val bg = if (filled) color.copy(alpha = 0.15f) else Color.Transparent
    Box(
        Modifier.background(bg, RoundedCornerShape(50)).padding(horizontal = 8.dp, vertical = 3.dp)
    ) {
        Text(text, color = color, fontSize = 11.sp, fontWeight = FontWeight.SemiBold)
    }
}

@Composable
fun ActionPill(action: String?) {
    if (action.isNullOrBlank()) return
    Pill(action.replace('_', ' '), SangamColors.forAction(action))
}

@Composable
fun ConvictionPill(conviction: Int?) {
    if (conviction == null) return
    val c = when { conviction >= 4 -> SangamColors.buy; conviction >= 3 -> SangamColors.hold; else -> SangamColors.neutral }
    Pill("conviction $conviction/5", c)
}

@Composable
fun SourceBadges(sourceType: String?, sebi: Boolean?, platform: String?) {
    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        platform?.takeIf { it.isNotBlank() }?.let {
            Pill(if (it == "instagram") "IG" else "YT", MaterialTheme.colorScheme.primary)
        }
        sourceType?.let { Pill(it, MaterialTheme.colorScheme.secondary) }
        if (sebi == true) Pill("SEBI RA", SangamColors.ok)
    }
}

/** Tiny horizontal action-breakdown bar for a stock (buy/sell/hold/…). */
@Composable
fun ActionBar(counts: Map<String, Int>) {
    val total = counts.values.sum().coerceAtLeast(1)
    Row(Modifier.fillMaxWidth().height(8.dp)) {
        counts.entries.sortedByDescending { it.value }.forEach { (action, n) ->
            Box(
                Modifier.weight(n.toFloat() / total)
                    .fillMaxHeight()
                    .background(SangamColors.forAction(action))
            )
        }
    }
}

@Composable
fun SectionCard(content: @Composable ColumnScope.() -> Unit) {
    Card(Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 6.dp)) {
        Column(Modifier.padding(14.dp), content = content)
    }
}

@Composable
fun DateFilterRow(selected: com.sangam.util.DateFilter, onSelect: (com.sangam.util.DateFilter) -> Unit) {
    Row(
        Modifier.fillMaxWidth()
            .horizontalScroll(androidx.compose.foundation.rememberScrollState())
            .padding(horizontal = 12.dp, vertical = 8.dp),
        horizontalArrangement = Arrangement.spacedBy(8.dp)
    ) {
        com.sangam.util.DateFilter.entries.forEach { f ->
            FilterChip(selected = selected == f, onClick = { onSelect(f) }, label = { Text(f.label) })
        }
    }
}
