# Original nine documents (extraction + v4 training/validation)

Downloaded 10 November 2026 (Africa/Accra) from public third-party mirrors. Every URL below returned HTTP 200 and a PDF at fetch time. These files are **not** in this repository (copyright). Re-fetch them with:

```bash
python scripts/download_docs.py --set original
```

Registry pages (public SPA, no login): `https://registry.verra.org/verra/public/program/VCS/projects/<ID>`

| Local file | Project | Role | Pages | Source URL |
|---|---|---|---:|---|
| `562_Kasigau-I-Rukinga_PDD_2011-01-31.pdf` | 562 Kasigau Corridor REDD Phase I (Rukinga), Kenya | PD (full, 31 Jan 2011) | 85 | https://redd.ffpri.go.jp/pub_db/course_materials/_img/2014_appliedb/2014_2_PROJ_DESC_562_31JAN2011.pdf |
| `562_Kasigau-I-Rukinga_PD_short_2011-01-25.pdf` | 562 | Short PD (25 Jan 2011) | 11 | https://redd.ffpri.go.jp/pub_db/course_materials/_img/2014_appliedb/2014_1_PROJ_DESC_562_25JAN2011.pdf |
| `612_Kasigau-II-Community-Ranches_PD_excerpt.pdf` | 612 Kasigau Corridor REDD Phase II (Community Ranches), Kenya | PD excerpt (not the full PD) | 11 | https://carbonmeld.com/docs/kasigau-corridor-6577f4/f56e8ca287b18301.pdf |
| `612_Kasigau-II-Community-Ranches_MR-M9_2022.pdf` | 612 | Monitoring report M9 (2022) | 208 | https://assets.zerocarbon.one/zerocarbon/941f5ccb-b8a8-4f14-b411-3d671a02a43e.pdf |
| `612_Kasigau-II-Community-Ranches_Verification_2024.pdf` | 612 | Verification report (AENOR, 2024) | 64 | https://carbonmeld.com/docs/kasigau-corridor-6577f4/b98172b17dc09814.pdf |
| `934_Mai-Ndombe_MR-M4_2021.pdf` | 934 Mai Ndombe REDD+, DRC | Monitoring report M4 (2021) | 174 | https://assets.zerocarbon.one/zerocarbon/eaa48b17-e0b6-43da-8336-93f03d208479.pdf |
| `1340_Bale-Mountains_MR_2020-2021.pdf` | 1340 Bale Mountains Eco-region REDD+, Ethiopia | Monitoring report (2020–2021) | 113 | https://assets.zerocarbon.one/zerocarbon/31292226-be17-4764-ada9-f93745edbe5a.pdf |
| `2410_Miro-Ghana_Verification_2020-2022.pdf` | 2410 Reforestation of Degraded Forest Reserve Areas, Ghana (Miro) | Verification report (2020–2022) | 90 | https://carbonmeld.com/docs/reforestation-of-degraded-forest-reserve-areas-in-ghana-west-5166a1/dcdc0fa585ae3d52.pdf |
| `2929_Bandai-Hills-Ghana_Validation_2024.pdf` | 2929 Bandai Hills bamboo reforestation, Ghana | Validation report (TÜV NORD, 2024) | 74 | https://carbonmeld.com/docs/bandai-hills-bamboo-reforestation-project-ghana-848b18/e4ef104a14342376.pdf |

SHA-256 checksums are in `MANIFEST.csv`. Miro (2410) and Bandai Hills (2929) are the **validation** projects and must stay out of training.

Mirrors used: FFPRI REDD course materials (Kasigau I), CarbonMeld, and ZeroCarbon. The official Verra registry SPA is public but rate-limits unattended downloads from this environment.
