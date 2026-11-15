# === 7i. VERRA CONSISTENCY CALCULATOR ===
# Screens the cleaned merge (area, reductions, period, buffer, leakage)
# and writes calc_results.csv, calc_results.json, and CALC_REPORT.md.
# This does not re-run Tiny Aya or touch the PDFs.
#
# Do not push the notebook with the Kaggle API: that dropped the
# HF_TOKEN secret last time. Paste this cell and run it from the UI.
# On Kaggle, upload verra_calc.py next to the notebook (or into the
# working directory) and point INPUT_DIR at the cleaned JSON folder.

from pathlib import Path
import importlib.util
import sys

# --- paths: TALLY_ROOT, the repo checkout, Kaggle, or the cwd. ---
import os
_here = Path(__file__).resolve().parent if "__file__" in globals() else Path.cwd()
_repo = Path(os.environ["TALLY_ROOT"]).expanduser() if os.environ.get("TALLY_ROOT") else (
    _here.parent if _here.name == "src" else _here
)
_kaggle = Path("/kaggle/working")

def _first(*cands):
    for c in cands:
        if c is not None and Path(c).exists():
            return Path(c)
    return Path(cands[-1])

CALC_PATH = _first(
    _here / "verra_calc.py",
    _repo / "src" / "verra_calc.py",
    Path("verra_calc.py"),
)
INPUT_DIR = _first(
    _repo / "results_clean",
    _repo / "results" / "extraction",
    Path("results_clean"),
    _kaggle / "results_clean",
)
OUTPUT_DIR = _first(_repo / "results", _kaggle if _kaggle.exists() else None, Path("."))

spec = importlib.util.spec_from_file_location("verra_calc", CALC_PATH)
calc = importlib.util.module_from_spec(spec)
sys.modules["verra_calc"] = calc
spec.loader.exec_module(calc)

rows = calc.run_calculator(INPUT_DIR, OUTPUT_DIR)

print(f"{'document':<52} {'area_ha':>12} {'reductions':>14} {'t/ha/yr':>8} {'verdict'}")
for r in rows:
    area = f"{r['area_ha']:,.2f}" if r["area_ha"] is not None else "—"
    red = f"{r['reductions_tco2e']:,.0f}" if r["reductions_tco2e"] is not None else "—"
    inten = f"{r['tco2e_ha_yr']:.2f}" if r["tco2e_ha_yr"] is not None else "—"
    print(f"{r['stem']:<52} {area:>12} {red:>14} {inten:>8} {r['verdict']}")

print(f"\nWrote {OUTPUT_DIR / 'calc_results.csv'}")
print(f"Wrote {OUTPUT_DIR / 'calc_results.json'}")
print(f"Wrote {OUTPUT_DIR / 'CALC_REPORT.md'}")
