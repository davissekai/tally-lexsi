# v5 answer key: calls for Renhuang to check

Key: `answer_key_v5.json` (13 PDs, drafted 13 Nov 2026, Africa/Accra). **Bold** = my default. Changing a default means editing `sft_v5/key_draft.py` and rerunning `build_key.py` then `build_v5.py` (takes about a minute).

1. **The PD gives only a pre-buffer total for estimated_reductions** (987, 1201, 1202, 1311, 673, 993). Default: **use the PD's stated net total**. Otherwise the chunks that contain it would teach the model to answer "not stated". Alternative: mark it not stated. Where the PD does give an after-buffer total, I used that: 1168 (6,312,632), 1215 (31'212'644), 1408, 1897, 1900, 2510 (4,102,366).
2. **The total covers only the first baseline period, not the full crediting period** (1201 2018–2028; 1311, 1897, 1900, 2510 roughly 10 years). Default: **use the stated total**, because that is all these PDs project.
3. **1202 has two estimated_reductions totals:** **5,673,506** (section 1.10) vs 5,670,301 (section 4.4 table). Both are before the buffer.
4. **Credited area vs total area.** 1202: **33,338 ha accounting area** vs 40,126 ha project area. 1408: **374,677.64 ha accounting area** vs 410,533.84 ha (all 7 land units). 1775: **943,676 ha initial project area** vs 823,942 ha of forest inside it.
5. **Area figures that disagree within one document.** 673: **6,213 ha** (p5) vs 6,212 ha (p14), inside a 10,000 ha boundary. 987: **3214 ha** of validated instances vs about 20,000 ha target (Table 2 sums to 3244,31 ha).
6. **2510 area: not stated.** The PD gives three separate project accounting areas and never a single total.
7. **1775 crediting period has a typo.** The PD says "May 1st, 2015 to April 30th, 2015 a total of 30 years". Default value: **May 1st, 2015 to April 30th, 2045**. The quote still shows "2015", so the value doesn't match its quote. Alternative: mark it not stated.
8. **The buffer percentage differs depending on where you read.** 1215: **13%** (VCS risk tool; it matches the 5'517'948 set-aside) vs 10% on p36. 673: **10% held** vs 8.5% from the risk tool. 2510: **10% applied minimum** vs 6.5% from the risk tool.
9. **Leakage given only as a percentage.** 1201 says "20% annual leakage". Default: **not stated**, because your rule is that leakage is tCO2e.
10. **Values that appear only in tables.** I used: 1900 buffer **19%** (column header quote), 1202 and 993 leakage **0 tCO2e** (column totals), and 1408 leakage **2,583,245 tCO2e** (printed as -2,583,245). I left 1168's buffer (a "10.00" column with no % sign) as **not stated**.
11. **673 oddities.** Baseline is **164.175 tonnes of CO2 e**, the same baseline stock every year. Crediting period is **1 January 2009, fixed 60 years**; the PD writes no end date.
12. **Left not stated because I found no clean statement.** Baseline: 1168, 1201, 1311, 1775, 1900. Leakage: 1168, 1311, 1775, 673. Buffer: 987, 1202, 1408, 1775, 993. Estimated reductions: 1775 (yearly rows, no total). If any of these is actually in the text, the chunk that contains it is currently labelled "not stated".
