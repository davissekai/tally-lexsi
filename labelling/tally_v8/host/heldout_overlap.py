"""Box-side: 12-word shingle overlap between package sources and held-out / eval documents."""
import sys, re, json, glob
from pathlib import Path
sys.path.insert(0, "/workspace/tally/antigravity_v8/package/tally_v8/tools"); import v8lib as L
def sh(t, n=12):
    w = re.findall(r"\w+", t.lower()); return {hash(" ".join(w[i:i+n])) for i in range(0, max(0, len(w)-n+1))}
def run(pkg_sources):
    banned = sorted(glob.glob("/workspace/tally/heldout/text/*.txt")) + [
        "/workspace/tally/run_output/tally/text/2410_Miro-Ghana_Verification_2020-2022.txt",
        "/workspace/tally/run_output/tally/text/2929_Bandai-Hills-Ghana_Validation_2024.txt"]
    B = set()
    for p in banned: B |= sh(L.read_text(p))
    worst = []
    for p in sorted(Path(pkg_sources).glob("*.txt")):
        S = sh(L.read_text(p)); ov = len(S & B) / max(1, len(S)); worst.append((round(ov, 4), p.name))
    worst.sort(reverse=True); return worst
if __name__ == "__main__":
    w = run(sys.argv[1]); print(w[:8]); print("max overlap", w[0][0])
