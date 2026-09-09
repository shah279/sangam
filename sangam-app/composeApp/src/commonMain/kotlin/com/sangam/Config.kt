package com.sangam

/**
 * Fill these in. Use the Supabase ANON key, NOT the service_role key. RLS makes
 * every table read-only for this key except `watchlist`, which the app is
 * allowed to INSERT/DELETE into directly (see schema.sql) since there's no
 * login system to scope a write to a user.
 */
object Config {
    const val SUPABASE_URL = "https://rngxzrpjglhjiirsiato.supabase.co"
    const val SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InJuZ3h6cnBqZ2xoamlpcnNpYXRvIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODU4MzQ1NjUsImV4cCI6MjEwMTQxMDU2NX0.K0Y2XsyyjjvZv7umSIYaQnA3BNj35CTvsUYjuB40ECI"
}