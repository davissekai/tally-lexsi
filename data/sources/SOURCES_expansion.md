# Data-expansion document sources

Downloaded 13 November 2026 (Africa/Accra) **without** using the Verra registry SPA (it is rate-limiting with HTTP 429). Each file was checked to start with `%PDF`, then converted with `pdftotext -layout -enc UTF-8` and split on form-feed into `--- page N ---` markers under `data_expansion/text/`.

Do not commit the full PDFs to a public repo (copyright). These are working files for Tally labelling, not a Kaggle upload.

**Preference:** one primary document per project, PD first. Validation set and held-out projects were not downloaded: Miro (2410), Bandai (2929), North Bandai (2928), Akwaaba (5172), Kwahu (5432), CRCF (4329). Already-used training docs (562, 612, 934, 1340) were also skipped.

## Saved (13 projects, all PDs)

Matching texts: `data_expansion/text/<same stem>.txt`.

| Local file | Official filename | Role | Pages | Cover version / date | Source |
|---|---|---|---:|---|---|
| `1201_PD.pdf` | `VCS_Project-Description_1201_10Jan2021_submitted.pdf` | **PD** (Gola REDD, Sierra Leone) | 137 | v4.0, 10 January 2021 (second baseline renewal) | Developer site: [golarainforest.org/gola-redd-project](https://golarainforest.org/gola-redd-project) → [direct PDF](https://golarainforest.org/s/VCS_Project-Description_1201_10Jan2021_submitted.pdf) |
| `1202_PD.pdf` | `20200708_LZRP_PD_V1.1.pdf` | **PD** (Lower Zambezi REDD+, Zambia) | 136 | v1.1, 8 July 2020 | Hosted copy on [CarbonDecode VCS1202](https://carbondecode.com/project/VCS1202) (`carbondecode.s3.amazonaws.com/docs/VCS1202/f4d941872faa087b.pdf`) |
| `1215_PD.pdf` | `PROJ_DESC_1215_28SEP2012.pdf` | **PD** (Makira Forest Protected Area, Madagascar) | 262 | 28 September 2012 (PDF title: Makira VCS Project Description v9) | Hosted copy on [CarbonDecode VCS1215](https://carbondecode.com/project/VCS1215) (`…/docs/VCS1215/4e1577fa0d9e5082.pdf`) |
| `1408_PD.pdf` | `PROJ_DESC_1408_23JUN2015.pdf` | **PD** (Chyulu Hills REDD+, Kenya) | 258 | 23 June 2015 | Hosted copy on [CarbonDecode VCS1408](https://carbondecode.com/project/VCS1408) (`…/docs/VCS1408/020e2f4cdcce25d3.pdf`) |
| `1897_PD.pdf` | `CCB_VCS_Project_Description_Ntakata_validated_UpdatedJuly2023.pdf` | **PD** (Ntakata Mountains REDD, Tanzania) | 155 | Cover: v3.0, 5 June 2020; filename notes a July 2023 update | Hosted copy on [CarbonDecode VCS1897](https://carbondecode.com/project/VCS1897) (`…/docs/VCS1897/ab856b6378e531d7.pdf`) |
| `1900_PD.pdf` | `PROJ_DESC_PL1900_29AUG2017.pdf` | **PD** (Makame Savannah REDD, Tanzania) | 221 | v1.0, 29 August 2017 (only PD hosted) | Hosted copy on [CarbonDecode VCS1900](https://carbondecode.com/project/VCS1900) (`…/docs/VCS1900/1df7cd827204484f.pdf`) |
| `2510_PD.pdf` | `231115_PDD_Chinko_REDD_CAR_2R.pdf` | **PD** (Chinko Conservation Area REDD+, CAR) | 331 | v10, 15 November 2023 | Hosted copy on [CarbonDecode VCS2510](https://carbondecode.com/project/VCS2510) (`…/docs/VCS2510/e3009b3bc72b979a.pdf`) |
| `987_PD.pdf` | `PROJ_DESC_987_06APR2018.pdf` | **PD** (Reforestation of Degraded Forest Reserves, Ghana) | 67 | v2.0, 6 April 2018 | Hosted copy on [CarbonDecode VCS987](https://carbondecode.com/project/VCS987) (`…/docs/VCS987/431c4f9c7569cf2f.pdf`) |
| `673_PD.pdf` | `PROJ_DESC_673_05SEP2011.pdf` | **PD** (Kibale National Park rehabilitation, Uganda) | 77 | v1.2, 5 September 2011 | Hosted copy on [CarbonDecode VCS673](https://carbondecode.com/project/VCS673) (`…/docs/VCS673/13c0102c693c25ad.pdf`) |
| `993_PD.pdf` | `TIST UG PD-VCS-005a PD Text 130304.pdf` | **PD** (TIST Program in Uganda, VCS 005) | 61 | v01, 4 March 2013 (PD text only, not appendices) | Hosted copy on [CarbonDecode VCS993](https://carbondecode.com/project/VCS993) (`…/docs/VCS993/0c4ba5f11ddffc14.pdf`) |
| `1168_PD.pdf` | `PROJ_DESC_1168_03JUL2014.pdf` | **PD** (Kulera Landscape REDD+, Malawi) | 138 | v14-0, 3 July 2014 | Hosted copy on [CarbonDecode VCS1168](https://carbondecode.com/project/VCS1168) (`…/docs/VCS1168/1e0729585a452e0c.pdf`) |
| `1311_PD.pdf` | `PROJ_DESC_1311_31JAN2013.pdf` | **PD** (CAZ Protected Area, Madagascar) | 165 | v03, 31 January 2013 | Hosted copy on [CarbonDecode VCS1311](https://carbondecode.com/project/VCS1311) (`…/docs/VCS1311/7ead01e189a4efc7.pdf`) |
| `1775_PD.pdf` | `20190715_LCFP_PD (4).pdf` | **PD** (Luangwa Community Forests, Zambia) | 228 | v2, 15 July 2019 | Hosted copy on [CarbonDecode VCS1775](https://carbondecode.com/project/VCS1775) (`…/docs/VCS1775/ad0e1f783eebbbdd.pdf`) |

CarbonDecode pages also list monitoring and validation/verification reports for most of the above (and CCBA / Terra Global Capital copies for some). Only the preferred PD was saved in this pass. Signed S3 query strings from CarbonDecode were used to fetch the files and are **not** recorded here.

Each extracted text was spot-checked on page 1: project title and proponent match the target ID. A CarbonDecode listing for VCS1202 that pointed at a **Kariba** PDD was ignored.

## Not saved (5 of the 18 requested)

These were searched on CarbonDecode, Carbon.Supply, CarbonMeld, developer sites, and web search. No public PD/MR/validation PDF was reachable without the Verra SPA.

| ID | Project | What was found |
|---|---|---|
| 799 | Bukaleba Forest Project (Uganda, Green Resources / Busoga Forestry) | CarbonDecode project page has no hosted documents. CarbonMeld has a profile but no PDF. Green Resources publishes plantation maps and a management-plan summary, not a VCS PD. |
| 3425 | Kwamisa / other reserves community forest (Ghana) | CarbonDecode and Carbon.Supply pages have no downloadable PD. |
| 5404 | Atebubu and Wiase Forest Landscape Restoration (Ghana) | Carbon.Supply lists filename `CCB VCS PD 5404 30-DEC-2024.pdf` (and a draft MR) but no download URL. Almost certainly only on the Verra Documents tab. |
| 5433 | Project Colobus (Ghana) | Carbon.Supply lists `CCB_VCS_PD_UD_5433_20250131.pdf` and `CCB_VCS_PD_5433_29092025.pdf`. No download URL. |
| 4946 | Wli Agorviefe Afforestation (Ghana) | Carbon.Supply lists `VCS-Project-Description-Final 2025 new meth.pdf` and `VCS_PD_DRAFT_4946_17JUL2024.pdf`. No download URL. |

The three Ghana VM0047-neighbour projects (5404, 5433, 4946) are the ones most likely to need a later registry-SPA (or user-browser) download.

## Other sources checked, not used as the saved file

- **CCBA** (`climate-standards.org`) lists Gola, Lower Zambezi, Makira, Chyulu, Kulera, and TIST documents, but the site returned HTTP 202 (challenge) to curl. Some historic `s3.amazonaws.com/CCBA/Projects/…` object URLs still exist (e.g. a Kulera CCB PDD and a Makira CCB validation report); a VCS PD from CarbonDecode or the developer was preferred.
- **Terra Global Capital** still hosts Kulera PD and MR copies under `terraglobalcapital.com/wp-content/uploads/2024/04/`. We used the official `PROJ_DESC_1168_03JUL2014.pdf` hosted copy instead.
- **Carbon Tanzania** project pages host 2023 impact / marketing PDFs for Ntakata and Makame, not the official VCS PDs.
- **BioCarbon Partners** (`bcp.earth`) hosts brochures and impact reports for Lower Zambezi and Luangwa, not the PDs.
- **Carbon.Supply** lists filenames for some newer projects but not download URLs.
- The Verra registry SPA and its document-manager API were **not** used.
