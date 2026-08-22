"""Non-code rules that `make check` enforces, because a rule nobody checks is a preference.

1. Rule 0.6: no source file over ~250 lines.
2. Rule 0.11: the built frontend must not reference any external origin.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAX_LINES = 250
SOURCE_GLOBS = [
    "server/**/*.py",
    "scripts/**/*.py",
    "tests/**/*.py",
    "web/src/**/*.ts",
    "web/src/**/*.tsx",
    "web/src/**/*.frag",
    "web/src/**/*.vert",
]
EXEMPT = {"web/src/api/schema.gen.ts"}  # generated, and never read by a human

EXTERNAL_URL = re.compile(rb"https?://(?!127\.0\.0\.1|localhost)[a-z0-9.-]+", re.I)
# Documentation hosts that appear only inside library error strings ("see https://react.dev/...").
# They are never fetched. The list is deliberately short: anything new here needs a reason.
DOC_HOSTS = {
    b"http://www.w3.org",
    b"https://www.w3.org",
    b"https://react.dev",
    b"https://reactjs.org",
    b"https://github.com",
    b"https://docs.pmnd.rs",
    b"https://threejs.org",
}
# Telemetry surface. A doc URL is a string; these are the ways code actually calls home.
TELEMETRY_MARKERS = [
    b"sendBeacon",
    b"googletagmanager",
    b"google-analytics",
    b"gtag(",
    b"posthog",
    b"mixpanel",
    b"amplitude",
    b"sentry.io",
    b"segment.io",
    b"telemetry",
]


def check_file_lengths() -> list[str]:
    failures = []
    for pattern in SOURCE_GLOBS:
        for path in ROOT.glob(pattern):
            rel = path.relative_to(ROOT).as_posix()
            if rel in EXEMPT:
                continue
            count = len(path.read_text().splitlines())
            if count > MAX_LINES:
                failures.append(
                    f"{rel} is {count} lines (limit {MAX_LINES}); split by responsibility"
                )
    return failures


def check_no_phone_home() -> list[str]:
    dist = ROOT / "web" / "dist"
    if not dist.is_dir():
        return ["web/dist is missing: run `npm run build` so the bundle can be scanned"]
    failures = []
    for path in dist.rglob("*"):
        if not path.is_file() or path.suffix == ".map":
            continue
        blob = path.read_bytes()
        for match in sorted(set(EXTERNAL_URL.findall(blob))):
            if match in DOC_HOSTS:
                continue
            failures.append(f"{path.relative_to(ROOT)} references {match.decode()}")
        for marker in TELEMETRY_MARKERS:
            if marker in blob:
                failures.append(f"{path.relative_to(ROOT)} contains telemetry marker {marker!r}")

    # An external script or stylesheet in the HTML is a real load, not a string in an error path.
    index = dist / "index.html"
    if index.is_file():
        for match in re.findall(rb'(?:src|href)="(https?://[^"]+)"', index.read_bytes()):
            failures.append(f"index.html loads {match.decode()} from an external origin")
    return failures


def main() -> int:
    failures = check_file_lengths() + check_no_phone_home()
    for failure in failures:
        print(f"  {failure}", file=sys.stderr)
    if failures:
        print(f"\n{len(failures)} check(s) failed", file=sys.stderr)
        return 1
    print("file lengths and no-phone-home: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
