"""Pipeline runner. Stages read/write the DB independently so they can be
scheduled at different times (systemd timers on the AWS box).

    python -m sangam.ingest            # discover + captions + extract
    python -m sangam.ingest discover
    python -m sangam.ingest captions
    python -m sangam.ingest extract
    python -m sangam.ingest init       # create/patch tables only
"""
from __future__ import annotations
import sys

from . import db, discover, captions, extract


def run_all():
    db.init_schema()
    discover.discover()
    captions.run()
    extract.run()


STAGES = {
    "all": run_all,
    "init": db.init_schema,
    "discover": lambda: (db.init_schema(), discover.discover()),
    "captions": captions.run,
    "extract": extract.run,
}


def main():
    stage = sys.argv[1] if len(sys.argv) > 1 else "all"
    fn = STAGES.get(stage)
    if not fn:
        print(f"unknown stage '{stage}'. options: {', '.join(STAGES)}")
        sys.exit(1)
    fn()


if __name__ == "__main__":
    main()
