package com.sangam.net

import io.ktor.client.engine.HttpClientEngine

/** Each platform supplies its Ktor engine (OkHttp on Android, Darwin on iOS). */
expect fun platformEngine(): HttpClientEngine
