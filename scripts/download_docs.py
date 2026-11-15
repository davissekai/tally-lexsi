#!/usr/bin/env python3
"""Re-fetch the Verra / carbon-project PDFs listed in data/sources/MANIFEST.csv.

PDFs are not stored in git (copyright, size). This script downloads them from
the public mirror URLs recorded at collect time, checks the SHA-256, and
optionally runs pdftotext.

Examples:

    python scripts/download_docs.py --set original
    python scripts/download_docs.py --set expansion,wide --extract-text
    python scripts/download_docs.py --verify-only

Held-out evaluation documents (5172, 5432, 4329) are not in the manifest;
see data/sources/heldout.md. The official Verra registry SPA rate-limits
unattended downloads, so those files need a browser session.

Be polite: the default pause is 1.5 seconds between requests.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = REPO / "data" / "sources" / "MANIFEST.csv"
DEFAULT_DEST = REPO / "data"
USER_AGENT = "TallyDocDownloader/1.0 (research; +https://github.com/davissekai/tally)"
PAUSE_S = 1.5


def load_manifest(path: Path, sets: set[str] | None) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if sets:
        rows = [r for r in rows if r["set"] in sets]
    return rows


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def download(url: str, dest: Path, timeout: int = 300) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp, tmp.open("wb") as out:
        status = getattr(resp, "status", None) or resp.getcode()
        if status != 200:
            tmp.unlink(missing_ok=True)
            raise RuntimeError(f"HTTP {status}")
        while True:
            block = resp.read(1024 * 1024)
            if not block:
                break
            out.write(block)
    head = tmp.open("rb").read(5)
    if not head.startswith(b"%PDF"):
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"not a PDF (starts with {head!r})")
    tmp.replace(dest)


def extract_text(pdf: Path, txt: Path) -> None:
    txt.parent.mkdir(parents=True, exist_ok=True)
    raw = subprocess.run(
        ["pdftotext", "-layout", "-enc", "UTF-8", str(pdf), "-"],
        check=True,
        capture_output=True,
    )
    pages = raw.stdout.decode("utf-8", errors="replace").split("\f")
    if pages and pages[-1].strip() == "":
        pages = pages[:-1]
    with txt.open("w", encoding="utf-8") as f:
        for i, page in enumerate(pages, 1):
            f.write(f"--- page {i} ---\n{page}\n")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    p.add_argument("--dest", type=Path, default=DEFAULT_DEST, help="Root under which dest_dir from the manifest is created")
    p.add_argument("--set", dest="sets", default="all", help="Comma-separated: original, expansion, wide, or all")
    p.add_argument("--pause", type=float, default=PAUSE_S, help="Seconds between downloads")
    p.add_argument("--verify-only", action="store_true", help="Only check existing files against SHA-256")
    p.add_argument("--extract-text", action="store_true", help="Also write pdftotext output next to each PDF (needs poppler)")
    p.add_argument("--overwrite", action="store_true")
    args = p.parse_args()

    sets = None if args.sets.strip().lower() == "all" else {s.strip() for s in args.sets.split(",") if s.strip()}
    if not args.manifest.is_file():
        print(f"manifest not found: {args.manifest}", file=sys.stderr)
        return 2
    rows = load_manifest(args.manifest, sets)
    if not rows:
        print("no rows matched", file=sys.stderr)
        return 2

    ok = skipped = failed = 0
    for i, row in enumerate(rows, 1):
        dest = args.dest / row["dest_dir"] / row["local_file"]
        label = f"[{i}/{len(rows)}] {row['set']} {row['local_file']}"
        expected = row["sha256"].lower()
        if dest.is_file():
            digest = sha256(dest)
            if digest == expected:
                print(f"{label}: already present, hash ok")
                skipped += 1
                if args.extract_text:
                    txt = dest.with_suffix(".txt")
                    if not txt.is_file() or args.overwrite:
                        extract_text(dest, txt)
                continue
            if not args.overwrite and not args.verify_only:
                print(f"{label}: hash mismatch (got {digest}, expected {expected}); use --overwrite to replace")
                failed += 1
                continue
            if args.verify_only:
                print(f"{label}: HASH MISMATCH got {digest}")
                failed += 1
                continue
        elif args.verify_only:
            print(f"{label}: missing")
            failed += 1
            continue

        if args.verify_only:
            continue

        try:
            print(f"{label}: downloading {row['source_url']}")
            download(row["source_url"], dest)
            digest = sha256(dest)
            if digest != expected:
                print(f"{label}: downloaded but HASH MISMATCH got {digest}, expected {expected}", file=sys.stderr)
                failed += 1
            else:
                print(f"{label}: ok")
                ok += 1
            if args.extract_text:
                extract_text(dest, dest.with_suffix(".txt"))
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, RuntimeError, OSError, subprocess.CalledProcessError) as exc:
            print(f"{label}: FAILED {exc}", file=sys.stderr)
            failed += 1
        if i < len(rows) and args.pause > 0:
            time.sleep(args.pause)

    print(f"done: downloaded={ok} already_ok={skipped} failed={failed} total={len(rows)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
