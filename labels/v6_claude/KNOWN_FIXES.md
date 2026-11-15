# Partial hand-back: labeller pass only

- labels.jsonl: 490 of 809 chunks (index order 1-490), 328 stated fields. check_quotes.py: 0 issues.
- review.jsonl: empty. The reviewer pass (Prompt B) has not run yet.

## Labels known to be wrong (found during per-round spot review, not yet corrected in labels.jsonl)

| chunk_id | field | labelled | should be |
|---|---|---|---|
| 1202_PD::chunk-012 | estimated_reductions_pre_buffer | 5,670,301 | not_stated; 5,670,301 belongs in estimated_reductions (it is currently a conflict) |
| 1408_PD::chunk-000 | estimated_reductions | 37,765,494 | not_stated (gross avoided emissions, not net ERs) |
| 1408_PD::chunk-002 | estimated_reductions | 37,765,494 | not_stated (same reason) |
| 2510_PD::chunk-034 | estimated_reductions | 1,294,618 | not_stated (one monitoring period's NER, not the crediting-period total) |
| 1408_VR_2022::chunk-006 | leakage | -24,408 | -744,376 (-24,408 is the confidence deduction column; same quote) |
