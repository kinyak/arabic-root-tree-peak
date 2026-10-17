"""watch_kaggle.py — poll a Kaggle kernel until it leaves running/queued, then save its log.

WHY A SEPARATE SCRIPT (measured, not tidiness)
    `kaggle_run.py --log` returns HTTP 200 with an EMPTY body while the kernel is still
    running — measured on v14: eight consecutive polls over ~8 minutes all came back
    `kernels/output(log): HTTP 200 OK` with 274 bytes (the banner alone). The log only
    becomes readable once the run stops. So a foreground poll loop can neither detect an
    early failure nor make progress; the useful thing is to wait for the state change and
    then pull both the log and the outputs in one go.

USAGE
    python tools/watch_kaggle.py [--interval 120] [--max-hours 3]
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import requests  # noqa: E402

import kaggle_run as K  # noqa: E402


def kernel_state() -> str:
    r = requests.get(f"{K.API}/kernels/status", headers=K.hdr(),
                     params={"userName": K.USER, "kernelSlug": K.KERNEL_SLUG.split("/")[1]},
                     timeout=120)
    if r.status_code != 200:
        return f"HTTP {r.status_code}"
    return r.json().get("status", "?")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Poll a Kaggle kernel until it leaves running/queued, then save its log."
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=120,
        help="Polling interval in seconds (default: 120)",
    )
    parser.add_argument(
        "--max-hours",
        type=float,
        default=3.0,
        help="Maximum polling duration in hours (default: 3.0)",
    )
    args = parser.parse_args()

    interval = args.interval
    max_hours = args.max_hours

    deadline = time.time() + max_hours * 3600
    last = None
    while time.time() < deadline:
        st = kernel_state()
        if st != last:
            print(f"[{time.strftime('%H:%M:%S')}] status -> {st}", flush=True)
            last = st
        if st not in ("running", "queued"):
            break
        time.sleep(interval)
    else:
        print("gave up: still not finished after %.1f h" % max_hours, flush=True)

    print("fetching log + outputs ...", flush=True)
    K.log()
    K.fetch()
    print("done", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
