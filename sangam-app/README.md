# Sangam — viewer app (KMM + Compose Multiplatform)

Read-only app over your Supabase data: consensus by stock, creators (with their
stock recommendations), video digests, and a fetch-health screen. Android + iOS.

## Fastest, most reliable way to build (recommended)

The one fragile part of any KMM project is the Gradle/version matrix. So instead of
trusting these build files blindly, generate a known-good base and drop the app in:

1. Create a **Compose Multiplatform** app from the wizard: https://kmp.jetbrains.com
   (or Android Studio's KMP plugin). Module name `composeApp`, package `com.sangam`,
   targets Android + iOS.
2. Delete the wizard's sample code under `composeApp/src/*/kotlin`.
3. Copy this repo's `composeApp/src/commonMain`, `androidMain`, `iosMain` over it.
4. Add these dependencies to `composeApp/build.gradle.kts` commonMain: Ktor
   (`client-core`, `client-content-negotiation`, `serialization-kotlinx-json`),
   `kotlinx-serialization-json`, `kotlinx-coroutines-core`, and
   `compose.materialIconsExtended`; androidMain: `ktor-client-okhttp`; iosMain:
   `ktor-client-darwin`. Apply the `kotlin-serialization` plugin.
   (The included `composeApp/build.gradle.kts` + `gradle/libs.versions.toml` show
   exactly this — use them as reference, or as-is if versions line up.)
5. Put your Supabase URL + **anon** key in `commonMain/.../com/sangam/Config.kt`.
6. Run on Android; the iOS entry point is `MainViewController()`.

## Prerequisite (backend)
Run the RLS read-policies + `runs` table SQL from the pipeline repo so the anon key
can read. The app uses the ANON key only (never service_role).

## Structure
- `model/Models.kt` — serializable rows (Channel, Video, Mention, Run) + ConsensusItem
- `net/Supabase.kt` — Ktor PostgREST client (+ per-platform engine)
- `data/Repository.kt` — one suspend fn per screen; consensus grouped client-side
- `ui/` — theme, components (pills, action bar, badges), Navigator, 6 screens
- `Config.kt` — URL + anon key (fill these)

## Screens
Stocks (consensus) → Stock detail (take per creator) · Creators → Creator detail
(their recommendations + recent videos) → Video detail (full digest + long notes) ·
Health (last run, counts, failures, reason, and live backlog). Instagram-ready: creators carry a
`platform` badge and no screen hardcodes YouTube.
