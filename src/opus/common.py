"""Shared bits for the Opus labelling batches (build_batches.py, ingest.py)."""
import json, re, sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
from paths import REPO_ROOT as ROOT

OB = Path(__import__("os").environ["OPUS_BATCHES"]).expanduser() if __import__("os").environ.get("OPUS_BATCHES") else (ROOT / "opus_batches")
REGISTRY = OB / "chunks_registry.jsonl"      # every chunk ever batched: id, doc, type, pages, text (original)
MANIFEST = OB / "manifest.json"              # batches -> chunk ids, token estimates
V5_LABELS = OB / "v5_chunk_labels.json"      # v5 per-chunk labels (recomputed from answer_key_v5 + build_v5 rules)

FIELDS = ["baseline", "additionality", "leakage", "permanence_buffer", "crediting_period", "area", "estimated_reductions"]
AUX_FIELDS = ["area_incl_leakage_belt", "estimated_reductions_pre_buffer"]
ALL_FIELDS = FIELDS + AUX_FIELDS
NOT_STATED = "not_stated"

# Validation (Miro 2410, Bandai 2929) and held-out (5172, 5432, 4329) projects never go to training.
EXCLUDED_PROJECTS = {"2410", "2929", "5172", "5432", "4329"}

def norm_ws(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()

def compact(text: str) -> str:
    """Token-saving layout for the batch file. Only whitespace changes, so a quote copied from the
    compacted text is still a literal substring of the original after norm_ws()."""
    lines = [re.sub(r"[ \t\u00a0]+", " ", ln).strip() for ln in text.split("\n")]
    out, blank = [], 0
    for ln in lines:
        if ln: out.append(ln); blank = 0
        else:
            blank += 1
            if blank == 1: out.append("")
    return "\n".join(out).strip()

def est_claude_tokens(s: str) -> int:
    # No Claude tokenizer offline. ~3.2 chars/token is a conservative figure for number-heavy English
    # PDF text (Anthropic's rule of thumb is ~3.5 for prose).
    return round(len(s) / 3.2)

def doc_type(stem: str) -> str:
    s = stem.upper()
    if re.search(r"(^|_)(MR|MONITORING)", s): return "MR"
    if re.search(r"VERIF|(^|_)VR", s): return "VR"
    if re.search(r"VALID", s): return "VAL"
    if re.search(r"(^|_)PDD?(_|$)|PROJECT.?DESC", s): return "PD"
    return "unknown"

def load_registry() -> dict:
    reg = {}
    if REGISTRY.exists():
        for ln in REGISTRY.read_text(encoding="utf-8").splitlines():
            if ln.strip():
                r = json.loads(ln); reg[r["chunk_id"]] = r
    return reg


# Near-template families: treat as one group so a later train/val split keeps them together
# and labelling batches do not over-represent near-copy documents from the same developer.
TEMPLATE_GROUPS = [
    ("977", "981"),
    ("959", "960", "961", "962"),
    ("737", "899", "993"),
    ("1847", "1855", "1865", "2070"),
]
_GROUP_OF = {p: "_".join(g) for g in TEMPLATE_GROUPS for p in g}

# Validation reports that CarbonDecode (and our filenames) labelled VR.
VAL_STEMS = {"1311_VR_2013", "2510_VR_2023"}

def project_group(project: str) -> str:
    return _GROUP_OF.get(str(project), str(project))

def doc_type_wide(stem: str) -> str:
    """Same as doc_type(), but marks the two known validation reports as VAL."""
    if stem in VAL_STEMS:
        return "VAL"
    return doc_type(stem)
