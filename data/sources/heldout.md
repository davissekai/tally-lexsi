# Held-out evaluation documents

These projects are reserved for a later generalisation test. Their **gold answers are not in this repository** and must not be used for training, validation, or Opus labelling.

Download them from the public Verra registry Documents tab (browser; the registry SPA is not reliably scriptable from this environment). They are not in `MANIFEST.csv` because no stable third-party mirror URL was recorded.

| Project ID | Name | Public registry page | Files kept for the test (not in git) | Registry document id (if known) | SHA-256 (for later verification) |
|---|---|---|---|---|---|
| 5172 | Project Akwaaba / Forest Ecosystem Restoration in Ghana | https://registry.verra.org/app/projectDetail/VCS/5172 | `5172_Akwaaba_PD_2026-01-30.pdf` (gold PD; official name `CCB_VCS_PD_5172_260130_Clean.pdf`) | 110200000360262 | e06adb0a5b056f79cb294f215fe940e4731fa9f0b6dd95583705ef34808b1382 |
| 5172 | (supporting, not a gold-key document) | same | `5172_Akwaaba_Validation_2026-01-29.pdf` (`CCB VCS ValR 5172_29012026_Clean.pdf`) | — | dcd95ec21a9d353383251f37d4be361886e26681a2e874fd06b88e1b3cba8b7a |
| 5172 | (supporting NPR) | same | `5172_Akwaaba_NPR_2023-09-01_2123-08-31.pdf` | — | 3beddbb3a3bc2f4385b844c1bd84a2ab80f724c222a9ee9bc5f35f1a239e02ae |
| 5432 | Kwahu Plateau / Kwahu Landscape Restoration Project, Ghana | https://registry.verra.org/app/projectDetail/VCS/5432 | `5432_Kwahu_PD_2025-05-22.pdf` (gold PD; official name `CCB-VCS-PD-ID5432-22-05-2025.pdf`) | 110200000312653 | a99a3e41b6b1fc57a71cc176a14023e92880c13630887ff9471b65ef4a294e6e |
| 4329 | Conservation and Restoration of Classified Forests in Côte d'Ivoire (CRCF) | https://registry.verra.org/app/projectDetail/VCS/4329 | `4329_CRCF_PD_2024-08-29.pdf` (gold PD; official name `CRCF_Project_Document_CCB_VCS_29_08_2024_.pdf`) | 110200000357422 | bcd7efbd78e30c2a5753d311f5c2eb28457117ad7b603bc8a597a15d1d9d5fa4 |

Also keep **2928 North Bandai** out of training (neighbour of validation project 2929). No local file was collected for 2928.

The held-out test was run once on **15 Nov 2026** (Africa/Accra, UTC+0) against 5172, 5432 and 4329 (126 chunks). Project 2928 was not scored: no document text or gold key was available. Aggregate scores, with gold values omitted, are in [`results/heldout_scores.json`](../../results/heldout_scores.json). The gold answer key remains outside this repository and must not be committed.

**Do not** add the held-out answer key to this tree, even after publication.
