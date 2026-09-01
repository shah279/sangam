"""Stage 2 (MVP): pull captions via youtube-transcript-api (1.x instance API).

Mixed-language channels: we prefer configured Hindi/English tracks and then a
human-made track within that language. If the host IP gets blocked,
set SANGAM_PROXY_URL in .env — no code change needed."""
from __future__ import annotations
from youtube_transcript_api import (
    AgeRestricted,
    IpBlocked,
    InvalidVideoId,
    NoTranscriptFound,
    RequestBlocked,
    TranscriptsDisabled,
    VideoUnavailable,
    YouTubeTranscriptApi,
)
from youtube_transcript_api.proxies import GenericProxyConfig

from . import config, db
from .outcome import StageResult


class CaptionUnavailable(RuntimeError):
    """The video cannot provide captions through this adapter; do not retry it."""


class CaptionAccessBlocked(RuntimeError):
    """The current host/proxy is blocked, so the whole caption batch should pause."""


_PERMANENT = (
    AgeRestricted,
    InvalidVideoId,
    NoTranscriptFound,
    TranscriptsDisabled,
    VideoUnavailable,
)
_ACCESS_BLOCKED = (IpBlocked, RequestBlocked)


def _api() -> YouTubeTranscriptApi:
    if config.PROXY_URL:
        return YouTubeTranscriptApi(
            proxy_config=GenericProxyConfig(http_url=config.PROXY_URL, https_url=config.PROXY_URL)
        )
    return YouTubeTranscriptApi()


def _language_rank(code: str) -> int:
    code = (code or "").lower()
    for i, preferred in enumerate(config.CAPTION_LANGS):
        preferred = preferred.lower()
        if code == preferred or code.split("-")[0] == preferred.split("-")[0]:
            return i
    return len(config.CAPTION_LANGS)


def fetch_caption(api: YouTubeTranscriptApi, video_id: str) -> str:
    """Return the best transcript, raising for unavailable and retryable failures."""
    try:
        transcripts = list(api.list(video_id))
    except _ACCESS_BLOCKED as e:
        raise CaptionAccessBlocked(
            "YouTube blocked caption requests from this IP; wait for the retry window "
            "or configure SANGAM_PROXY_URL"
        ) from e
    except _PERMANENT as e:
        raise CaptionUnavailable(str(e)) from e
    if not transcripts:
        raise CaptionUnavailable("no transcript tracks")

    # Prefer the configured Hindi/English languages, then human-made over generated.
    chosen = min(transcripts, key=lambda t: (_language_rank(t.language_code), t.is_generated))
    try:
        raw = chosen.fetch().to_raw_data()   # list of {'text','start','duration'}
        text = " ".join(d["text"] for d in raw).strip()
    except _ACCESS_BLOCKED as e:
        raise CaptionAccessBlocked(
            "YouTube blocked caption requests from this IP; wait for the retry window "
            "or configure SANGAM_PROXY_URL"
        ) from e
    except _PERMANENT as e:
        raise CaptionUnavailable(str(e)) from e
    if not text:
        raise CaptionUnavailable("empty transcript")
    return text


def run() -> StageResult:
    api = _api()
    done = 0
    processed = 0
    errors: list[str] = []
    with db.connect() as conn:
        pending = db.videos_needing_captions(conn)

    for video_id, title, previous_attempts in pending:
        attempt = previous_attempts + 1
        try:
            text = fetch_caption(api, video_id)
            with db.connect() as conn:
                db.save_transcript(conn, video_id, text, "captions", "done", attempts=attempt)
            done += 1
            print(f"  captions: {title}  ({len(text)} chars)")
        except CaptionUnavailable as e:
            with db.connect() as conn:
                db.save_transcript(conn, video_id, None, None, "unavailable",
                                   attempts=attempt, error=str(e))
            print(f"  no captions: {title} ({e})")
        except CaptionAccessBlocked as e:
            next_retry = db.retry_at(attempt)
            message = f"caption access blocked while processing {title}: {e}"
            errors.append(message)
            try:
                with db.connect() as conn:
                    db.save_transcript(
                        conn,
                        video_id,
                        None,
                        None,
                        "retry",
                        attempts=attempt,
                        error=str(e),
                        next_retry_at=next_retry,
                    )
            except Exception as save_error:
                errors.append(f"could not persist caption failure for {title}: {save_error}")
            processed += 1
            print(f"  ! {message}; paused remaining caption work")
            break
        except Exception as e:
            terminal = attempt >= config.MAX_STAGE_ATTEMPTS
            status = "error" if terminal else "retry"
            next_retry = None if terminal else db.retry_at(attempt)
            message = f"caption failed for {title} (attempt {attempt}): {e}"
            errors.append(message)
            try:
                with db.connect() as conn:
                    db.save_transcript(conn, video_id, None, None, status, attempts=attempt,
                                       error=str(e), next_retry_at=next_retry)
            except Exception as save_error:
                errors.append(f"could not persist caption failure for {title}: {save_error}")
            print(f"  ! {message}; status={status}")
        processed += 1

    print(f"captions: {done}/{len(pending)} transcribed; {len(errors)} error(s)")
    return StageResult("captions", done, processed, errors)


if __name__ == "__main__":
    raise SystemExit(0 if run().ok else 1)
