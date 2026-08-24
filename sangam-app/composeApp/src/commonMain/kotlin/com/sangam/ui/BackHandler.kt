package com.sangam.ui

import androidx.compose.runtime.Composable

/** Handle the OS back gesture/button (Android). No-op where the OS handles it (iOS). */
@Composable
expect fun SystemBackHandler(enabled: Boolean, onBack: () -> Unit)
