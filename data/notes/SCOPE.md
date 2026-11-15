# Tally data-expansion scope

**Date:** Friday 13 Nov 2026, ~8:55 AM Africa/Accra  
**Status:** Scoping only. Nothing was trained, pushed to Kaggle, or paid for. No Hugging Face credits were redeemed. No paid APIs were called.

**Context:** The rebalanced v4 QLoRA run overfit (62 train examples from 7 projects; train loss ~0.20 vs val loss ~0.98; fine-tune 0/13 vs base Tiny Aya 3/13 on the Miro + Bandai val set). Lexsi deadline is end of day Saturday 14 Nov 2026 (Africa/Accra). The goal is a bigger, quote-grounded training set, with Miro (2410), Bandai Hills (2929), and the held-out projects (5172 Akwaaba, 5432 Kwahu, 4329 CRCF) kept strictly out of training.

---

## 1. More public Verra documents

### What the box can and cannot fetch today

The registry moved to the S&P Global / Platts SPA in mid-2026. From this machine this morning:

| Endpoint | Result (13 Nov 2026) |
|---|---|
| `https://registry.verra.org/uiapi/resource/resourceSummary/{id}` (old public JSON) | HTTP 200, 2,598-byte **HTML SPA shell**, not JSON. Dead for automation. |
| `https://registry.verra.org/app/projectDetail/VCS/{id}` | HTTP 302 → `/verra/public/program/VCS/projects/{id}`. Curl gets the same SPA shell. A browser can render the public project page and Documents tab (this is how the held-out PDFs were downloaded on 12 Nov). |
| `https://registry.verra.org/config/environment.config.json` | Works. Publishes the live API base `https://prod-us.api.platts.com/ci-raas-prod` and the SPA's public default headers (including an `appkey`). |
| `…/ci-raas-prod/cms-resources/public/standardsByRegistry/VERRA` | **Works** (HTTP 200 JSON). Confirmed from the box with the SPA's public headers. This only lists programme/standard metadata, not project files. |
| `…/raas-project-api/project-manager/…` | HTTP 401 Unauthorized on every path tried. |
| `…/br-reg/rest/document-manager/public/…` | Bare path: 401. Guessed download/list paths: 404 “No static resource…”. The public document-manager base exists, but the exact method names were not recovered in this pass. |
| `…/raas-report-api/es/public/…` | Mostly HTTP 500 (“Please contact support team”). The route exists; the query shape is wrong or the public search is broken. |
| OpenAPI / Swagger | `swagger-ui` and `v3/api-docs/swagger-config` are reachable; group docs often 401, 500, or time out. Not usable as a map of download URLs today. |

**Bottom line:** curl from the box cannot yet list or download project PDFs from the official registry. The public SPA still can. That is a reliable path: it already produced the held-out files yesterday (`SOURCES.md` registry doc ids such as 110200000360262 for Akwaaba's PD).

Third-party mirrors still serve **already-used** PDFs (confirmed this morning, first bytes `%PDF-1.7`):

- `https://assets.zerocarbon.one/zerocarbon/941f5ccb-b8a8-4f14-b411-3d671a02a43e.pdf` — Kasigau II MR M9 (already in training)
- `https://carbonmeld.com/docs/kasigau-corridor-6577f4/f56e8ca287b18301.pdf` — Kasigau II PD excerpt (already in training)

Carbonmeld HTML listing pages are often Cloudflare-blocked (403). Carbon.Supply (`https://carbon.supply/p/verra/{id}/`) is reachable and lists **filenames** for some newer projects, but not download URLs.

### How many documents we can realistically get today

- **Via the public registry UI (browser, no login):** 20–40 public PDs, monitoring reports, or validation/verification reports is realistic in **2–4 hours**, at one primary document per project. This is the same method used for 5172 / 5432 / 4329 on 12 Nov.
- **Automated bulk from the box today:** not available. Do not plan on a curl scrape of the official files unless someone finishes the document-manager path work (out of scope for this note).
- **Mirrors:** useful as a backup for a handful of well-known projects, not as a complete library.
- **Pipeline VM0048 projects** (5177, 5396, 5655, 5679, 5732, 6029, 4838): Carbon.Supply still lists **no PD/MR filenames**. Treat them as “check the Documents tab, expect empty.”

The binding constraint is not “are there enough public forestry documents?” (there are thousands of AFOLU projects on Verra; even the African REDD+/ARR shortlist below is enough). The constraint is **labelling time** before Saturday evening.

Recommended download set: **about 20 primary documents from 20 distinct projects** (diversity of projects is what v4 lacked), not 40 files from a few large programmes. Prefer a PD; if no PD is posted, take the latest MR or the validation/verification report. Skip representations, KML, and comms agreements.

### Exclusions (do not download for training)

Already used in the current set:

- 562 Kasigau I (PDD + short PD)
- 612 Kasigau II (PD excerpt, MR M9, verification)
- 934 Mai-Ndombe (MR M4)
- 1340 Bale Mountains (MR)
- **Validation (keep out of training):** 2410 Miro, 2929 Bandai Hills

Held-out (keep out of training):

- 5172 Akwaaba
- 5432 Kwahu
- 4329 CRCF

### Candidate list (~32 forestry / AFOLU projects)

Legacy UI links redirect to the SPA URLs. Both are listed. Filenames come from Carbon.Supply as of this morning; they are **names only**, not download URLs.

#### A. First wave — registered or late-stage African forestry (highest chance of a public PD/MR)

| ID | Project | Type / methodology | Status | Country | Registry (SPA) | Carbon.Supply | Notes |
|---:|---|---|---|---|---|---|---|
| 673 | Kibale National Park rehabilitation | ARR / AR-ACM0001 | Registered | Uganda | https://registry.verra.org/verra/public/program/VCS/projects/673 | https://carbon.supply/p/verra/673/ | Strong ARR analogue; credits issued |
| 799 | Bukaleba Forest Project | ARR / AR-ACM0003 v2 | Registered | Uganda | https://registry.verra.org/verra/public/program/VCS/projects/799 | https://carbon.supply/p/verra/799/ | |
| 987 | Reforestation of Degraded Forest Reserves in Ghana | ARR / AR-ACM0003 v2 | Registered | Ghana | https://registry.verra.org/verra/public/program/VCS/projects/987 | https://carbon.supply/p/verra/987/ | Same meth family as Miro/Bandai, different project |
| 993 | TIST Program in Uganda, VCS 005 | ARR / AR-AMS0001 v6 | Registered | Uganda | https://registry.verra.org/verra/public/program/VCS/projects/993 | https://carbon.supply/p/verra/993/ | Grouped smallholder ARR |
| 1168 | Kulera Landscape REDD+ | REDD / VM0006 | Verification approval requested | Malawi | https://registry.verra.org/verra/public/program/VCS/projects/1168 | https://carbon.supply/p/verra/1168/ | |
| 1201 | Gola REDD | REDD / VM0007 v1.4 | Registered | Sierra Leone | https://registry.verra.org/verra/public/program/VCS/projects/1201 | https://carbon.supply/p/verra/1201/ | |
| 1202 | Lower Zambezi REDD+ | REDD / VM0009 v3 | Registered | Zambia | https://registry.verra.org/verra/public/program/VCS/projects/1202 | https://carbon.supply/p/verra/1202/ | |
| 1215 | Makira Forest Protected Area | REDD / VM0007 | Late to Verify | Madagascar | https://registry.verra.org/verra/public/program/VCS/projects/1215 | https://carbon.supply/p/verra/1215/ | |
| 1311 | CAZ Protected Area | REDD / VM0015 v1.1 | Late to Verify | Madagascar | https://registry.verra.org/verra/public/program/VCS/projects/1311 | https://carbon.supply/p/verra/1311/ | |
| 1408 | Chyulu Hills REDD+ | REDD / VM0009 | Registered | Kenya | https://registry.verra.org/verra/public/program/VCS/projects/1408 | https://carbon.supply/p/verra/1408/ | Same meth family as Kasigau, different landscape |
| 1775 | Luangwa Community Forests | REDD / VM0009 v3 | Verification approval requested | Zambia | https://registry.verra.org/verra/public/program/VCS/projects/1775 | https://carbon.supply/p/verra/1775/ | |
| 1897 | Ntakata Mountains REDD | REDD / VM0007 | Registered | Tanzania | https://registry.verra.org/verra/public/program/VCS/projects/1897 | https://carbon.supply/p/verra/1897/ | |
| 1900 | Makame Savannah REDD | REDD / VM0007 | Verification approval requested | Tanzania | https://registry.verra.org/verra/public/program/VCS/projects/1900 | https://carbon.supply/p/verra/1900/ | |
| 2510 | Chinko Conservation Area REDD+ | REDD / VM0009 | Verification approval requested | CAR | https://registry.verra.org/verra/public/program/VCS/projects/2510 | https://carbon.supply/p/verra/2510/ | |
| 3425 | Kwamisa / other reserves community forest | ARR / AR-ACM0003 v2 | Registered | Ghana | https://registry.verra.org/verra/public/program/VCS/projects/3425 | https://carbon.supply/p/verra/3425/ | Good Ghana ARR diversity |

Legacy project-detail URLs follow `https://registry.verra.org/app/projectDetail/VCS/{id}` and redirect to the SPA URLs above.

#### B. Ghana VM0047 / recent docs — filenames already known

| ID | Project | Status | Known public filenames (Carbon.Supply) | SPA |
|---:|---|---|---|---|
| 5404 | Atebubu and Wiase Forest Landscape Restoration | Under validation | PD: `CCB VCS PD 5404 30-DEC-2024.pdf`; draft MR: `CCB VCS MR 5404 DRAFT 01-JUN-2022 01-DEC-2023.pdf` | https://registry.verra.org/verra/public/program/VCS/projects/5404 |
| 5433 | Project Colobus | Registration requested | PD: `CCB_VCS_PD_UD_5433_20250131.pdf`; also `CCB_VCS_PD_5433_29092025.pdf` (listed as Other) | https://registry.verra.org/verra/public/program/VCS/projects/5433 |
| 4946 | Wli Agorviefe Afforestation | Pipeline listing approved | `VCS-Project-Description-Final 2025 new meth.pdf`; `VCS_PD_DRAFT_4946_17JUL2024.pdf` | https://registry.verra.org/verra/public/program/VCS/projects/4946 |

Use the latest PD, not listing-representation PDFs. These are the closest methodology neighbours to the held-out Ghana/Côte d'Ivoire VM0047 documents, without being those documents.

#### C. Optional / lower priority

| ID | Why optional |
|---:|---|
| 2928 North Bandai Bamboo (Ghana, ARR, registered) | Sister of **val** project 2929. Useful ARR text, but high risk of template / figure leakage into a “new document” test. Skip unless we are short. |
| 4890 Keta Lagoon (Ghana, ARR+WRC, VM0033) | Public PD + validation filenames known, but blue carbon / wetlands, previously deprioritised. Only if we want methodology diversity. Filenames: `VCS CCB PD 4890 6AUG2026 (clean).pdf`, `CCB VCS ValR Project ID 4890_20260816_Clean.pdf`. SPA: https://registry.verra.org/verra/public/program/VCS/projects/4890 |
| 4126 Community Restoration of Native Ecosystems (Ghana, ARR, registered) | Only 5 ha / 92 tCO2e per year — too atypical. Skip. |
| 5075 Liza Protect Forest (Congo, ARR+REDD, under validation) | Worth a Documents-tab check; Carbon.Supply has no filenames yet. https://registry.verra.org/verra/public/program/VCS/projects/5075 |
| 5563, 6331 (Ghana ARR pipeline) | May have no PD yet. Quick check only. |
| VM0048 pipeline: 4838, 5177, 5396, 5655, 5679, 5732, 6029 | No filenames found today. Check and skip if empty. |

Cookstoves and ODS projects seen on the Ghana list (983, 1752, 2389, 3801, 4161) and hydropower (1505) are **out of scope**.

Raw Carbon.Supply scrape for this pass: `candidates_carbon_supply.json` in this folder.

### Practical download recipe (when we leave scoping)

1. Open each SPA project URL in a browser (no Verra login needed for public documents).
2. Documents tab → download the latest PD, else latest MR, else validation/verification report.
3. Save as `{id}_{short-name}_{role}_{date}.pdf` under `/workspace/tally/data_expansion/pdfs/`.
4. `pdftotext -layout -enc UTF-8` as for the held-out set.
5. Do not commit full PDFs to a public repo (same copyright rule as `heldout/SOURCES.md`).

---

## 2. What CuratorKIT 0.1.27 can do

Installed in `/workspace/tally/.venv-curator`, version **0.1.27** (PyPI package `curatorkit`). Docs: https://lexsi-labs.github.io/CuratorKIT/latest/ and the generation guide at https://lexsi-labs.github.io/CuratorKIT/latest/guides/generation/. Source for this install is the site-package tree under that venv.

### Already used (no LLM, free)

Ingest, schema check, exact + MinHash dedup, text cleaning, trainer-ready export (Alpaca, ShareGPT, messages). This is what we ran on the 131-row set. Hygiene gates (PII, toxicity, secrets) exist but should stay off for this corpus (they would rewrite gold quotes or flag ordinary conservation language).

### Synthetic / augmentation half (needs an LLM)

Eight generation tasks, all corpus-aware when the input is a source chunk:

| Task | What it produces | Fit for Tally's 7-field extract? |
|---|---|---|
| `qa` | N grounded question–answer pairs per chunk | Poor as a default: free-form Q&A, not the seven-field JSON. A **custom `prompt_template`** could ask for the Tally schema. |
| `preference` / `grpo` / `multiturn` / `cot` / `evol` | DPO pairs, rollouts, dialogues, CoT, harder instructions | Not the SFT target we train. Out of scope for this weekend. |
| `adversarial_qa` / `adversarial_preference` | Controlled bad answers | Only useful later as hard negatives, after we have gold labels. |

`PDFReader` can chunk PDFs (via optional MinerU) and, if `output_mode` is `qa`/`preference`/etc., call an LLM per chunk. We already have a Tally-specific chunker and should keep using that, not MinerU's heading splitter, so windows stay comparable to inference.

**Grounding:** QA prompts require answers to come from the passage. After generation, `HallucinationGate` judges each answer against the exact source chunk (LLM-as-judge, not string match). Diagnostic probe / adaptive recovery can retry failures. This is useful, but it is **not** a substitute for our stricter rule: every numeric/value field must contain an **exact quote** that appears in the chunk (or stay `"not stated"`).

### LLM backends, and which are free

Backends live in `curatorkit.llm`. The default config model is `openai/gpt-4o-mini`.

- **LiteLLM** (`LiteLLMBackend`, extra `curatorkit[generation]`: `litellm`, `tenacity`, `nest-asyncio`). Talks to OpenAI, Anthropic, Gemini, Bedrock, Azure, Mistral, vLLM, Ollama, etc. **Not installed** in the current venv (core CuratorKIT only).
- **Ollama** (`OllamaBackend`): local HTTP, **no API key**. Default `http://localhost:11434`. Docs also mention `llm_model = "ollama/aya-expanse"`. **Ollama is not running on this box.**
- Local **vLLM / OpenAI-compatible** endpoint via `llm_api_base`.

There is **no built-in free cloud LLM**. Free options, if we later enable generation:

1. Ollama or vLLM on a machine we already have (Kaggle GPU or the box, if a small model fits) — free, but setup time and weaker than Claude for long PDD extraction.
2. Hugging Face Inference, **only if** the $20 credits are already on the account (see §3). Do not redeem the coupon for this.
3. A provider free tier Renhuang already has (Gemini, Groq, etc.). Do not open new paid accounts.

Calling Claude or GPT through CuratorKIT is a paid LiteLLM path and needs an explicit yes.

**Verdict:** CuratorKIT *can* generate training data from new PDD chunks, including with a custom Tally JSON prompt and a hallucination gate. It should not invent documents or numbers. The cheap, reliable use this weekend is still the **no-LLM hygiene/export** path, with labels drafted outside CuratorKIT and then ingested.

---

## 3. Labelling plan

Keep the existing rule: a field gets the gold value only if the gold quote (or the distinctive number plus a cue word for short figures like `10%`) appears in that chunk; otherwise `"not stated"`. Additionality will stay rare in MRs. Val (Miro, Bandai) and held-out (5172, 5432, 4329) stay out of the train file.

### Who drafts

**Recommended (free, fits the deadline):** Indi drafts the seven-field answer keys from `pdftotext` output, then the existing `build_and_curate.py` style quote-grounding builds chunk-level SFT rows. Renhuang only reviews ambiguous fields (conflicting area figures, crediting-period bounds, “is this leakage or a buffer?”). This is how the current key was made, scaled to ~20 new docs.

**Optional LLM assist (only with his yes if it costs money):** a model proposes `{value, quote}` per field from a chunk or from pre-filtered sections (area, buffer, crediting period, …). A deterministic checker then **drops any value whose quote is not an exact substring of the chunk**. Unchecked Claude output must not enter the train set. CuratorKIT QA + HallucinationGate can be this assistant, but only after `curatorkit[generation]` is installed and a backend is chosen.

A free HF or Ollama model is acceptable as a drafter if the quote check stays mandatory. It will be sloppier than Claude; the checker is what keeps the set honest.

Do **not** generate fully synthetic PDDs or invented numbers. That would teach the model the wrong habit we are trying to unlearn.

### Claude cost for ~30 documents (do not spend without a yes)

Official Anthropic list prices as of this morning (https://platform.claude.com/docs/en/about-claude/pricing):

- Claude Sonnet 4.5: **$3 / MTok input**, **$15 / MTok output** (deprecated, still billed at this rate; retires 30 Nov 2026).
- Claude Sonnet 5.5: **$2 / MTok input**, **$10 / MTok output**.
- Claude Haiku 4.5: **$1 / MTok input**, **$5 / MTok output**.
- Batch API is 50% off those rates.

Assumptions for **30 docs**, chunk-filtered (send only sections/chunks that might contain a field, not every page twice):

- ~15 chunks × ~4,000 input tokens × 30 docs ≈ **1.8 M input tokens**
- ~800 output tokens × 15 × 30 ≈ **0.36 M output tokens**

| Model | Approx. API cost |
|---|---|
| Sonnet 4.5 | ~$5.40 in + ~$5.40 out ≈ **$11** |
| Sonnet 5.5 | ~$3.60 in + ~$3.60 out ≈ **$7** |
| Haiku 4.5 | ~$1.80 in + ~$1.80 out ≈ **$3.60** |

If we naively send full 100–350 page PDDs (≈2–3 M input tokens) and need a retry pass, budget **$10–25** on Sonnet 4.5. Prompt caching would lower a second pass (cache reads are 10% of input price). These are API list prices, not Claude.ai subscription usage, and they assume we actually call the API — which we should not do unless he says so.

### Hugging Face $20 credits

He has **$20 of HF credits**. **Do not redeem them** for this work. This pass did not log in or check whether the coupon is already on the account. If the credits are already active, HF Inference could be a no-extra-cost drafter; if they are still an unredeemed coupon, leave them unused and draft without a paid model.

---

## 4. Recommended plan before 14 Nov EOD (Africa/Accra)

Now: Friday 13 Nov ~9:00 AM. Deadline: Saturday 14 Nov 23:59. About **39 hours**. GPT/Claude benchmarks, the GitHub/HF repo, the write-up, and submission stay **on hold** until he says go.

The v4 failure was too few **projects**, not too few overlapping chunks from the same seven. Target **~20 new projects, one primary document each**, merged with the existing 62 train examples, same val set.

Expected yield: 20 docs × ~8–15 labelled chunks ≈ **160–300 new train rows**, plus the current 62, so roughly **220–360 train examples** from ~24–27 projects. Still small by generic LoRA standards, but several times more project diversity. Keep 3 epochs or drop to 2 if val loss diverges early.

### Schedule

| When (Africa/Accra) | Work | Time | Money |
|---|---|---|---|
| Fri late morning | Browser-download ~20 first-wave + Ghana VM0047 docs from the registry SPA. Spot-check that each PDF opens and is a PD/MR/val report. | 2–3 h | None |
| Fri afternoon | `pdftotext`, chunk with the existing Tally windowing, start answer keys with quote-grounding. | 2–3 h setup + drafting into the evening | None |
| Fri night / Sat early | Finish keys; build chunk-level JSONL; run CuratorKIT **hygiene only** (no generator); merge with current train; **do not touch** val or held-out. | 3–5 h drafting, 30 min curation | None |
| Sat morning | Kaggle QLoRA rerun (same recipe as v4: r=16, α=32, 2–3 epochs, answer-span loss, token from `renhuang01/tally-hf-token`). ~30–60 min plus one fix-and-rerun if needed. | 1–2 h wall clock | Kaggle free quota only |
| Sat midday | Compare to base 3/13 on Miro+Bandai. If the fine-tune is better, keep it. If it still loses or only ties, **ship base Tiny Aya + calculator** and treat both fine-tunes as negative/partial results. | 1 h | None |
| Sat afternoon | Buffer for a short second train (e.g. 2 epochs, or drop 2928-like near-val docs) if the first run overfits again. Still no submit / write-up / external benchmark unless he unblocks those. | remaining | None |

If download-via-browser cannot start until he is free, Indi can still prepare scripts (chunking, quote checker, CuratorKIT config) and, once PDFs land, do the labelling. If only 10–12 clean docs are in hand by Friday night, train on that rather than waiting for 30.

### What not to do this weekend

- Paid Claude/GPT labelling or CuratorKIT generation without a yes.
- Redeeming HF credits.
- Training on Miro, Bandai, Akwaaba, Kwahu, or CRCF, or on synthetic numbers that are not in a source chunk.
- Expanding into cookstoves or other non-forestry sectoral scopes.
- Pushing a new Kaggle dataset or starting the train before the quote-grounded train file exists.

### Decision rule after the new run

Ship whichever system wins on the unchanged Miro+Bandai val set (and, if time, a sanity glance at held-out, without training on it). A small gain on 13 scored pairs is still only a direction, but a clear loss should not replace the base model.
