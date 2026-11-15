# Wide data-expansion sources (13 Nov 2026, Africa/Accra)

All 80 files are hosted copies from CarbonDecode (`carbondecode.com/project/VCS{id}` → `carbondecode.s3.amazonaws.com/docs/VCS{id}/…`). Signed query strings stripped from `source_url`. No Verra registry SPA, no sign-in, no payment. ~1.5 s between requests.
Every file starts with `%PDF`; text via `pdftotext -layout -enc UTF-8`, split on form feed into `--- page N ---` markers in `../text_wide/`. All ≥1,100 chars/page (no scans). Cover page / first pages checked against the expected project name.

Exclusions honoured: 2410, 2929, 2928, 5172, 5432, 4329, 562, 612, 934, 1340; SHA-256 checked against `pdds/`, `heldout/pdfs/`, `data_expansion/pdfs/` (no duplicates).

## Rejected (mislabelled on CarbonDecode, moved to `wide_work/rejected/`)
- `920_PD_2012` listed under VCS920 EDS Green Carbon, but the document is the 'Weyerhaeuser Uruguay' PD (= VCS960 Lumin/Eucapine's predecessor).
- `1543_PD_2008` listed under VCS1543 Bosques del Uruguay, but the document is the CDM-AR-PDD for 'Guanaré' (VCS959).

## Notes for labelling
- Near-template families (dedupe / group-split before training): 977 & 981 (Portel-Pará, same developer & text); 959/960/961/962 (Carbosur Uruguay); 737/899 (TIST Kenya) ~ 993 (TIST Uganda); 1847/1855/1865/2070 (Shanghai Libra China afforestation).
- 737_PD is the CCBA (CCB-002) PD for TIST Kenya, not a pure VCS PD.
- Joint PD+MR documents: 1566, 1740, 2532, 2551, 3350.
- 1311_VR is the 2013 validation report; 2510_VR is the v10 validation report (20 Nov 2023). Others are verification reports.
- 1201 Gola: CarbonDecode hosts no MR/VR, so none added.
- `date` = latest year found in the filename/title (`n` if none).

| file | project | country | pages | title |
|---|---|---|---:|---|
| 673_MR_2023.pdf | Natural High Forest Rehabilitation Project on degraded  | Uganda | 84 | VCS_Monitoring_Report_Kibale_2020-2023_v1.9 (1).pdf |
| 987_MR_2023.pdf | Reforestation of Degraded Forest Reserves in Ghana | Ghana | 72 | 23_04 VCS Final MR 987 01-August-2021 to 31-July-2023clear.pdf |
| 993_MR_n.pdf | TIST Program in Uganda, VCS 005 | Uganda | 25 | TIST UG PD-VCS-005k App10 Verif 02 Monitoring Rpt 171017.pdf |
| 1168_MR_n.pdf | Kulera Landscape REDD+ Program for Co-Managed Protected | Malawi | 191 | Kulera-CCB-VCS-Monitoring-Report- ... |
| 1202_MR_2025.pdf | LOWER ZAMBEZI REDD+ PROJECT | Zambia | 158 | 20250120_VCS_MR_1202_01012024-31122024_v1.3_Clean.pdf |
| 1215_MR_2013.pdf | The Makira Forest Protected Area in Madagascar | Madagascar | 82 | MONIT_REP_1215_01JAN2010_31DEC2013.pdf |
| 1311_MR_2011.pdf | Carbon Emissions Reduction Project in the Corridor Anke | Madagascar | 40 | MONIT_REP_1311_31DEC2007_31DEC2011.pdf |
| 1408_MR_2022.pdf | Chyulu Hills REDD+ Project | Kenya | 207 | 221026_ChyuluHills_MR_VCS_CCB_Findings_8_VERRA_ (1) (1).pdf |
| 1775_MR_2024.pdf | Luangwa Community Forests Project | Zambia | 165 | 20240801_LCFP_VCS_MR_M5_v1.6_Clean.pdf |
| 1897_MR_2026.pdf | Ntakata Mountains REDD | Tanzania | 176 | CCB_VCS_2024_MR_1897_19052023-18052024_20260330.pdf |
| 1900_MR_2026.pdf | Makame Savannah REDD | Tanzania | 188 | V5_CCB_VCS_2024_MR 1900 27042023-26042024_20260326.pdf |
| 2510_MR_2023.pdf | CHINKO CONSERVATION AREA REDD+ PROJECT, CENTRAL AFRICAN | Central African Republic | 192 | 231115_MR_Chinko_REDD_CAR_2R.pdf |
| 673_VR_2023.pdf | Natural High Forest Rehabilitation Project on degraded  | Uganda | 80 | CCB VCS VR 673 01MAR2020-28FEB2023.pdf |
| 987_VR_2024.pdf | Reforestation of Degraded Forest Reserves in Ghana | Ghana | 89 | VCS VERIFICATION REPORT OF THE REFORESTATION OF DEGRADED FOREST RESERV |
| 993_VR_n.pdf | TIST Program in Uganda, VCS 005 | Uganda | 39 | TIST UG VCS-005k EPIC Verification Report V3 200309.pdf |
| 1168_VR_2013.pdf | Kulera Landscape REDD+ Program for Co-Managed Protected | Malawi | 56 | VERIF_REP_1168_01OCT2009_30SEP2013.pdf |
| 1202_VR_2024.pdf | LOWER ZAMBEZI REDD+ PROJECT | Zambia | 154 | VCS VerR 1202 01012024-31122024 v1.3 Clean.pdf |
| 1215_VR_2013.pdf | The Makira Forest Protected Area in Madagascar | Madagascar | 81 | VERIF_REP_1215_01JAN2010_31DEC2013.pdf |
| 1311_VR_2013.pdf | Carbon Emissions Reduction Project in the Corridor Anke | Madagascar | 91 | VALID_REP_1311_23OCT2013.pdf |
| 1408_VR_2022.pdf | Chyulu Hills REDD+ Project | Kenya | 172 | 21059.00_ChyuluHills_CCB_VCS_Verif_Report_V2.1_20221026.pdf |
| 1775_VR_2023.pdf | Luangwa Community Forests Project | Zambia | 231 | VCS VerR 1775 01January2023-31December2023.pdf |
| 1897_VR_2024.pdf | Ntakata Mountains REDD | Tanzania | 177 | CCB_VCS_VerR_1897_19052023-18052024.pdf |
| 1900_VR_2024.pdf | Makame Savannah REDD | Tanzania | 161 | CCB VCS VerR 1900 27042023-26042024.pdf |
| 2510_VR_2023.pdf | CHINKO CONSERVATION AREA REDD+ PROJECT, CENTRAL AFRICAN | Central African Republic | 134 | VCS CCB_Chinko_Validation Report_v10_20112023_clean.pdf |
| 142_PD_2009.pdf | Reforestation of degraded grasslands in Uchindile & Map | Tanzania | 163 | Reforestation in grassland areas of Uchindile, Kilombero, Tanzania & M |
| 607_PD_2019.pdf | Darkwoods Forest Carbon Project | Canada | 51 | SDV_PROJ_DESC_ENG_DRAFT_05AUG2019.pdf |
| 674_PD_2011.pdf | Rimba Raya Biodiversity Reserve Project | Indonesia | 148 | PROJ_DESC_674_15MAY2011.pdf |
| 737_PD_2011.pdf | TIST Program in Kenya, VCS 005 | Kenya | 64 | CCBA Project Description for TIST Program in Kenya CCB-002 (correspond |
| 832_PD_n.pdf | Cikel Brazilian Amazon REDD APD Project   Avoiding Plan | Brazil | 110 | PDD APD CKBV.pdf |
| 844_PD_2012.pdf | Madre de Dios Amazon REDD+ Project | Peru | 457 | Madre de Dios Amazon REDD Project — Project Description v3.0 (VCS Vers |
| 868_PD_2014.pdf | Proyecto REDD+ Castañeros | Peru | 279 | REDD Project in Brazil Nut Concessions in Madre de Dios – CCB Project  |
| 875_PD_2025.pdf | FLORESTAL SANTA MARIA PROJECT | Brazil | 212 | VCS PD 875 updated_24FEB2025.pdf |
| 899_PD_n.pdf | TIST Program in Kenya, VCS 006 | Kenya | 99 | TIST KE PD-VCS-006a PD Text CCB Re-Val 210312v3.pdf |
| 902_PD_2013.pdf | KARIBA REDD+ PROJECT | Zimbabwe | 105 | PROJ_DESC_902_16AUG2013.pdf |
| 944_PD_2015.pdf | Alto Mayo Conservation Initiative | Peru | 168 | PROJ_DESC_944_07AUG2015.pdf |
| 959_PD_2021.pdf | 'Guanaré' Forest Plantations on degraded grasslands und | Uruguay | 122 | 20210317 PD-V8 Feb 2021-FINAL DRAFT2 - GUANARE CCB_Project_Description |
| 960_PD_2023.pdf | Lumin/Eucapine Uruguay Forest Plantations on degraded g | Uruguay | 136 | V10_PD Lumin_Weyerhauser_20230919.pdf |
| 961_PD_2012.pdf | 'El Arriero ' Afforestation on degraded grasslands unde | Uruguay | 75 | PROJ_DESC_961_11SEP2012.pdf |
| 962_PD_2022.pdf | Forteko afforestation on degraded grasslands under exte | Uruguay | 131 | 'Forteko' Afforestation on Degraded Grasslands Under Extensive Grazing |
| 977_PD_2014.pdf | RMDLT Portel - Para REDD Project | Brazil | 201 | RMDLT VCS PD_FINAL_VCS UPDATE_Aug 2014.pdf |
| 981_PD_2013.pdf | Pacajai REDD+ Project | Brazil | 201 | PROJ_DESC_981_17JAN2013.pdf |
| 985_PD_2012.pdf | Cordillera Azul National Park REDD Project | Peru | 198 | PROJ_DESC_985_20DEC2012.pdf |
| 1055_PD_2013.pdf | Reforesting Degraded Lands in Chile through the use of  | Chile | 65 | PROJ_DESC_1055_19APR2013.pdf |
| 1067_PD_2012.pdf | Reduction of deforestation and degradation in Tambopata | Peru | 173 | PROJ_DESC_1067_24MAY2012.pdf |
| 1141_PD_2014.pdf | Fresh Breeze Afforestation Project | Mexico | 68 | PROJ_DESC_1141_30JUN2014.pdf |
| 1382_PD_2015.pdf | The Envira Amazonia Project - A Tropical Forest Conserv | Brazil | 142 | PROJ_DESC_1382_04APR2015.pdf |
| 1463_PD_2015.pdf | India Sundarbans Mangrove Restoration | India | 83 | 2015-06-10 Project Description NEWS.pdf |
| 1477_PD_2016.pdf | Katingan Peatland Restoration and Conservation Project | Indonesia | 291 | 2016-May-11 Final PDD_RMU.pdf |
| 1566_PD_2017.pdf | REDD+ Project Resguardo Indigena Unificado Selva de Mat | Colombia | 398 | PROJ_DESC_1566_30MAY2017.pdf |
| 1622_PD_2017.pdf | REDD+ Project for Caribbean Guatemala: The Conservation | Guatemala | 353 | PROJ_DESC_1622_27MAR2017.pdf |
| 1650_PD_2014.pdf | Reduced Emissions from Deforestation and Degradation in | Cambodia | 304 | PROJ_DESC_1650_29DEC2014.pdf |
| 1740_PD_n.pdf | Reforestation with Teak  CO2e TEAKMEX | Mexico | 118 | PD_TeakMexCO2.pdf |
| 1748_PD_2018.pdf | Southern Cardamom REDD+ Project | Cambodia | 229 | DRAFT_PROJ_DESC_PL1748_08MAR2018.pdf |
| 1847_PD_2019.pdf | Qianxinan Afforestation Project in Guizhou Province | China | 70 | PROJ_DESC_1847_12MAR2019.pdf |
| 1855_PD_2019.pdf | Hechu Afforestation Project in Anhui Province | China | 63 | PROJ_DESC_1855_08APR2019.pdf |
| 1865_PD_2019.pdf | Xiguan Afforestation Project in Guizhou Province | China | 90 | PROJ_DESC_1865_30OCT2019.pdf |
| 1899_PD_2019.pdf | Sumatra Merang Peatland Project (SMPP) | Indonesia | 235 | PROJ_DESC_1899_25NOV2019.pdf |
| 2070_PD_2019.pdf | Guinan Afforestation Project | China | 71 | DRAFT_PROJ_DESC_PL2070_27NOV2019.pdf |
| 2250_PD_n.pdf | Delta Blue Carbon – 1 | Pakistan | 362 | Indus Delta DBC1 ARR PD v4.pdf |
| 2252_PD_2021.pdf | Rio Anapu-Pacaja REDD Project | Brazil | 267 | Rio_PD final 12082021.pdf |
| 2278_PD_2021.pdf | The Jaguar Amazon REDD+ Project | Peru | 234 | PD The Jaguar Amazon REDD Project 24th Feb 2021.pdf |
| 2297_PD_2024.pdf | REDD+ Project Pueblos indígenas resguardando la selva | Colombia | 411 | 20240607_VCS-Joint-Project-Description-Monitoring-Report_Predio-Putuma |
| 2404_PD_2022.pdf | Reforestation of degraded land by MTPL in India | India | 98 | MTPL- 2404-Reforestation degraded lands VCS PD_Clean Version_February  |
| 2502_PD_n.pdf | TAHUAMANU AMAZON REDD PROJECT | Peru | 211 | Tahuamanu Amazon REDD Project_VCS_CCB_v6.pdf |
| 2532_PD_2022.pdf | Cumare carbon project | Colombia | 144 | PROJ_DESC_2532_09082022.pdf |
| 2551_PD_2022.pdf | BRAZILIAN AMAZON APD GROUPED PROJECT | Brazil | 222 | BRC_VCS_PD_MR_REDD_APD_GPD_v1.8_22Mar2022.pdf |
| 2609_PD_2023.pdf | KUAMUT RAINFOREST CONSERVATION PROJECT | Malaysia | 225 | Kuamut Rainforest Conservation Project — CCB & VCS Project Description |
| 3350_PD_2022.pdf | THE ARR HORIZONTE CARBON PROJECT | Brazil | 124 | 20220808 - DRAFT PD+MR_ARR Horizonte Carbon Project.pdf |
| 142_MR_2008.pdf | Reforestation of degraded grasslands in Uchindile & Map | Tanzania | 105 | MONIT_REP_142_01JAN2002_30NOV2008.pdf |
| 607_MR_2023.pdf | Darkwoods Forest Carbon Project | Canada | 182 | CCB VCS MR 607_01Jan2022-31Dec2023_Round1_Clean.pdf |
| 674_MR_2019.pdf | Rimba Raya Biodiversity Reserve Project | Indonesia | 251 | CCB_VCS_Monitoring_Report_2017_2019_MP5_v1.16.pdf |
| 737_MR_2016.pdf | TIST Program in Kenya, VCS 005 | Kenya | 25 | MONIT_REP_737_09JUN2011_08NOV2016.pdf |
| 832_MR_2023.pdf | Cikel Brazilian Amazon REDD APD Project   Avoiding Plan | Brazil | 199 | 2023.07.18_VCS_MR2_Cikel_VERRA.pdf |
| 844_MR_2019.pdf | Madre de Dios Amazon REDD+ Project | Peru | 79 | VCS-Monitoring-Report-Template-v4.0 (2019) 15th December VERRA.pdf |
| 868_MR_2023.pdf | Proyecto REDD+ Castañeros | Peru | 117 | CCB VCS MR_868_REDDBrazil nut concessions_2021_2022_2023.pdf |
| 875_MR_2022.pdf | FLORESTAL SANTA MARIA PROJECT | Brazil | 103 | VCS MR 875 13APR2019-12APR2022.pdf |
| 899_MR_n.pdf | TIST Program in Kenya, VCS 006 | Kenya | 72 | TIST KE PD-VCS-006n App13 Verif 03 Monitoring Rpt 210312v4x.pdf |
| 902_MR_2022.pdf | KARIBA REDD+ PROJECT | Zimbabwe | 168 | 220908_CCB_VCS_Kariba_REDD_MR5_v4_clean.pdf |
| 944_MR_2020.pdf | Alto Mayo Conservation Initiative | Peru | 87 | MONIT_REP_944_15JUN2018_14JUN2020.pdf |
| 985_MR_2022.pdf | Cordillera Azul National Park REDD Project | Peru | 183 | 6.1. CIMA-PNCAZ- 2020-MR_CCBv2.0_VCSv3.4_V3.1_31.10.2022 (1) - Edited  |
