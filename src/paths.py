"""Resolve the Tally repository root and common locations.

Scripts used to hard-code ``/workspace/tally``. They now go through this
helper, so a clone works without that working-tree path.

Override the root with the ``TALLY_ROOT`` environment variable when you
are running against a working tree that also holds labels, extracted
text, or tokenizer files that are not in git. Optional
``TALLY_TOKENIZER`` points at a Tiny Aya ``tokenizer.json``.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def repo_root() -> Path:
    env = os.environ.get("TALLY_ROOT")
    if env:
        return Path(env).expanduser().resolve()
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "data").is_dir() and (parent / "README.md").is_file():
            return parent
    return here.parents[1]


def prepend_import_paths() -> Path:
    """Put ``src/`` and the repo root on ``sys.path`` and return the root."""
    root = repo_root()
    src = root / "src"
    for path in (src, root):
        s = str(path)
        if s not in sys.path:
            sys.path.insert(0, s)
    return root


def first_existing(*candidates: Path) -> Path | None:
    for path in candidates:
        if path is not None and Path(path).exists():
            return Path(path)
    return None


def find_tokenizer() -> Path | None:
    env = os.environ.get("TALLY_TOKENIZER")
    if env:
        path = Path(env).expanduser()
        if path.is_file():
            return path
    root = repo_root()
    candidates = [
        root / "sft_out" / "tally-lora" / "tokenizer.json",
        root / "sft_out" / "v7" / "tally-lora" / "tokenizer.json",
        root / "artifacts" / "tokenizer.json",
    ]
    kaggle_input = Path("/kaggle/input")
    if kaggle_input.is_dir():
        candidates.extend(sorted(kaggle_input.rglob("tokenizer.json"))[:20])
    return first_existing(*candidates)


REPO_ROOT = repo_root()
DATA_DIR = REPO_ROOT / "data"
SRC_DIR = REPO_ROOT / "src"
RESULTS_DIR = REPO_ROOT / "results"
