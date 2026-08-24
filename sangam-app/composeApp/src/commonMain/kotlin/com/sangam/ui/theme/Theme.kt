package com.sangam.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

private val Indigo = Color(0xFF4F46E5)
private val Teal = Color(0xFF0EA5A4)

private val Light = lightColorScheme(primary = Indigo, secondary = Teal)
private val Dark = darkColorScheme(primary = Color(0xFF8B8CF0), secondary = Color(0xFF5EEAD4))

// Semantic colours for actions/status (used by chips).
object SangamColors {
    val buy = Color(0xFF16A34A)
    val sell = Color(0xFFDC2626)
    val hold = Color(0xFFCA8A04)
    val waitForDip = Color(0xFF2563EB)
    val radar = Color(0xFF7C3AED)
    val future = Color(0xFF0891B2)
    val neutral = Color(0xFF6B7280)
    val ok = Color(0xFF16A34A)
    val error = Color(0xFFDC2626)

    fun forAction(a: String?): Color = when (a) {
        "buy" -> buy; "sell" -> sell; "hold" -> hold
        "wait_for_dip" -> waitForDip; "radar" -> radar
        "future_opportunity" -> future; else -> neutral
    }
}

@Composable
fun SangamTheme(content: @Composable () -> Unit) {
    MaterialTheme(colorScheme = if (isSystemInDarkTheme()) Dark else Light, content = content)
}
