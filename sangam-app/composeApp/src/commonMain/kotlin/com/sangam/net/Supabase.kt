package com.sangam.net

import com.sangam.Config
import io.ktor.client.HttpClient
import io.ktor.client.call.body
import io.ktor.client.plugins.contentnegotiation.ContentNegotiation
import io.ktor.client.request.delete
import io.ktor.client.request.get
import io.ktor.client.request.header
import io.ktor.client.request.post
import io.ktor.client.request.setBody
import io.ktor.http.ContentType
import io.ktor.http.contentType
import io.ktor.serialization.kotlinx.json.json
import kotlinx.serialization.json.Json

/**
 * Thin client over Supabase PostgREST. Almost every table is read-only for
 * the anon key (RLS denies writes) — `watchlist` is the one deliberate
 * exception (see schema.sql), which is what [insert]/[delete] exist for.
 */
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

    /** POST a new row and return the inserted representation(s). */
    suspend inline fun <reified Body, reified Response> insert(table: String, body: Body): List<Response> {
        val url = "${Config.SUPABASE_URL}/rest/v1/$table"
        return http().post(url) {
            header("apikey", Config.SUPABASE_ANON_KEY)
            header("Authorization", "Bearer ${Config.SUPABASE_ANON_KEY}")
            header("Prefer", "return=representation")
            contentType(ContentType.Application.Json)
            setBody(body)
        }.body()
    }

    /** DELETE rows matching a raw PostgREST filter, e.g. "id=eq.42". */
    suspend fun delete(table: String, query: String) {
        val url = "${Config.SUPABASE_URL}/rest/v1/$table?$query"
        http().delete(url) {
            header("apikey", Config.SUPABASE_ANON_KEY)
            header("Authorization", "Bearer ${Config.SUPABASE_ANON_KEY}")
        }
    }

    fun http(): HttpClient = client
}
