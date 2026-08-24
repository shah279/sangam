package com.sangam.ui

import androidx.compose.runtime.Composable

@Composable
actual fun SystemBackHandler(enabled: Boolean, onBack: () -> Unit) { /* no-op on iOS */ }
