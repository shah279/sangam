package com.sangam.ui

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.State
import androidx.compose.runtime.produceState
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp

sealed interface Async<out T> {
    data object Loading : Async<Nothing>
    data class Error(val message: String) : Async<Nothing>
    data class Success<T>(val data: T) : Async<T>
}

@Composable
fun <T> loadState(vararg keys: Any?, loader: suspend () -> T): State<Async<T>> =
    produceState<Async<T>>(Async.Loading, *keys) {
        value = try { Async.Success(loader()) } catch (e: Throwable) {
            Async.Error(e.message ?: e.toString())
        }
    }

/** Renders loading / error, or calls [content] with loaded data. */
@Composable
fun <T> AsyncContent(state: Async<T>, content: @Composable (T) -> Unit) {
    when (state) {
        is Async.Loading -> Box(Modifier.fillMaxSize(), Alignment.Center) { CircularProgressIndicator() }
        is Async.Error -> Box(Modifier.fillMaxSize().padding(24.dp), Alignment.Center) {
            Text("Couldn't load: ${state.message}")
        }
        is Async.Success -> content(state.data)
    }
}
