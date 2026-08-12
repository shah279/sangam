# Sangam — Instagram (Phase 3)

Reference note. Instagram is **phase 3**, after: YouTube automation (done, runs on
the phone via cron), normalization + consensus report, and daily-video generation.
Nothing here is built yet — this is the plan when we get to it.

## Why add it
Widen coverage beyond the 12 YouTube channels, catching creators who are
Instagram-first. Feeds the same consensus and the same daily-video/Shorts output.

## Target accounts
Provided so far (appear distinct from the YouTube set):
- @bullishview
- @stocks2wealth
- @anupamtripathifinanceofficial
- @financewithpapa

Scope intended to grow to ~15 accounts. Most are Business/Creator accounts (relevant
because that's what the free Meta Graph API requires).

## What reuses as-is
The back half of the pipeline is platform-agnostic. Once we have the text, these are
identical to YouTube:
- Extraction (Gemini) → mentions + note/long_note/conviction
- Normalization (NSE/AMFI)
- Consensus + report
- Supabase storage — just add a `platform` column ('youtube' | 'instagram')

Design as a pluggable **source adapter**: YouTube and Instagram both feed one shared
core. Do NOT reimplement the pipeline in Kotlin — the Kotlin app stays a read-only
*viewer* over Supabase.

## What's genuinely harder (the front half)

### 1. Discovery — no free RSS
Options:
- **Apify scraper (leaning toward this).** Works for any public account, no Meta app
  review. ~$1.50 per 1,000 posts on the main actor; free ~$5/month credit (~3,300
  posts) likely covers ~15 accounts polled daily. Cheaper actors ~$0.30–0.50/1,000.
- **Meta Graph API.** Free, but Business/Creator accounts only, ~200 calls/hour, and
  requires Meta app review. Compliant but gated.
- Raw scraping (instaloader etc.) — fragile, blocked often. Avoid.

### 2. Transcription — no free-caption shortcut
Reels have no `youtube-transcript-api` equivalent, so download audio → STT:
- **Sarvam** (India-tuned, Hinglish-native) — ~₹30/hour of audio. Slots in as an httpx
  call, no compiling — fits the phone/pure-HTTP setup. Also the fix for caption garbles.
- or self-hosted Whisper (free compute, needs a real box, not the phone).
- **OCR** for image/carousel posts (a lot of finance IG is text-on-image): Tesseract
  (free) or a cloud vision API (pennies). Plus the post caption text.

### 3. Extraction / storage
Same Gemini + Supabase. Negligible cost.

## Rough monthly cost (at ~15 accounts) — RE-VERIFY before building
Prices drift, so treat these as planning estimates:
- Discovery (Apify): ~$0–5 (mostly inside the free credit)
- STT (Sarvam): ~₹270 / ~$3, or $0 self-hosted
- OCR: ~$0 (self-host)
- LLM + storage: negligible (same as now)
Total: roughly **$0–10/month**. The real cost is engineering + maintenance (scrapers
break when Instagram changes), not dollars.

## Legal / compliance notes (not legal advice)
- Scraping public, logged-out Instagram data was ruled not a CFAA violation
  (Meta v. Bright Data, 2024) — but it still runs against Instagram's terms. Use
  judiciously.
- For the published-video product: present as *reporting* ("here's what these
  commentators said"), attribute clearly, carry a visible "not investment advice"
  disclaimer, and keep it transformative (your own summary, not re-uploaded clips).

## First check when we start
Confirm the target accounts are public Business/Creator accounts — that decides
whether the free Graph API is even an option vs. going straight to the Apify scraper.
