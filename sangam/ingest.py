"""Pipeline runner. Stages read/write the DB independently so they can be
scheduled at different times (systemd timers on the AWS box).

    python -m sangam.ingest            # discover + captions + extract
    python -m sangam.ingest discover
    python -m sangam.ingest captions
    python -m sangam.ingest extract
    python -m sangam.ingest normalize  # backfill canonical instrument symbols
    python -m sangam.ingest prices     # fetch EOD closes for resolved symbols
    python -m sangam.ingest retry      # requeue terminal/legacy failures
    python -m sangam.ingest init       # verify the deployed schema only
"""
from __future__ import annotations
import sys

from . import db, discover, captions, extract, normalize, prices
from .outcome import StageResult


def run_all() -> StageResult:
    db.init_schema()
    run_id = db.start_run()
    results: list[StageResult] = []
    try:
        results.append(discover.discover())
        results.append(captions.run())
        results.append(extract.run())
        errors = [message for result in results for message in result.errors]
        status = "success" if not errors else "partial"
        db.finish_run(
            run_id,
            status,
            new_videos=results[0].count,
            transcribed=results[1].count,
            mentions=results[2].count,
            error="\n".join(errors[:20]) or None,
        )
        return StageResult(
            "all",
            count=sum(result.count for result in results),
            processed=sum(result.processed for result in results),
            errors=errors,
        )
    except Exception as e:
        try:
            counts = {result.stage: result.count for result in results}
            db.finish_run(
                run_id,
                "failed",
                new_videos=counts.get("discover", 0),
                transcribed=counts.get("captions", 0),
                mentions=counts.get("extract", 0),
                error=str(e),
            )
        except Exception as finish_error:
            print(f"could not record failed run: {finish_error}")
        raise


def run_discover() -> StageResult:
    return discover.discover()


def run_captions() -> StageResult:
    return captions.run()


def run_extract() -> StageResult:
    return extract.run()


def run_normalize() -> StageResult:
    return normalize.run()


def run_prices() -> StageResult:
    return prices.run()


def retry_failed() -> StageResult:
    caption_count, extract_count = db.requeue_failed()
    print(f"requeued: {caption_count} caption item(s), {extract_count} extraction item(s)")
    return StageResult("retry", caption_count + extract_count, caption_count + extract_count)


STAGES = {
    "all": run_all,
    "init": db.init_schema,
    "discover": run_discover,
    "captions": run_captions,
    "extract": run_extract,
    "normalize": run_normalize,
    "prices": run_prices,
    "retry": retry_failed,
}


def main():
    stage = sys.argv[1] if len(sys.argv) > 1 else "all"
    fn = STAGES.get(stage)
    if not fn:
        print(f"unknown stage '{stage}'. options: {', '.join(STAGES)}")
        sys.exit(1)
    try:
        result = fn()
    except Exception as e:
        print(f"pipeline failed: {e}")
        sys.exit(1)
    if isinstance(result, StageResult) and not result.ok:
        print(f"pipeline completed with {len(result.errors)} error(s)")
        sys.exit(1)


if __name__ == "__main__":
    main()
