package com.sangam.net

import com.sangam.Config
import io.ktor.client.HttpClient
import io.ktor.client.call.body
import io.ktor.client.plugins.contentnegotiation.ContentNegotiation
import io.ktor.client.request.get
import io.ktor.client.request.header
import io.ktor.serialization.kotlinx.json.json
import kotlinx.serialization.json.Json

/** Thin read-only client over Supabase PostgREST. */
object Supabase {
    private val json = Json {
        ignoreUnknownKeys = true
        isLenient = true
        explicitNulls = false
    }

    private val client = HttpClient(platformEngine()) {
        install(ContentNegotiation) { json(json) }
    }

    /**
     * GET {SUPABASE_URL}/rest/v1/{table}?{query} and decode a list of T.
     * `query` is raw PostgREST query params, e.g. "select=*&order=name".
     */
    suspend inline fun <reified T> select(table: String, query: String = ""): List<T> {
        val base = "${Config.SUPABASE_URL}/rest/v1/$table"
        val url = if (query.isBlank()) base else "$base?$query"
        return http().get(url) {
            header("apikey", Config.SUPABASE_ANON_KEY)
            header("Authorization", "Bearer ${Config.SUPABASE_ANON_KEY}")
        }.body()
    }

    fun http(): HttpClient = client
}
