# Hand-back: labeller pass complete, reviewer pass in progress

- labels.jsonl: all 809 of 809 chunks (index order), 799 stated fields. check_quotes.py: 0 issues.
- review.jsonl: the reviewer pass (Prompt B, fresh Sonnet subagents) has just started; this zip's copy may be empty or partial.
  The final zip will carry the complete review.jsonl; its fix/reject verdicts supersede this table.

## Labels known to be wrong (found during per-round spot review, not yet corrected in labels.jsonl)

| chunk_id | field | labelled | should be |
|---|---|---|---|
| 1202_PD::chunk-012 | estimated_reductions_pre_buffer | 5,670,301 | not_stated; 5,670,301 belongs in estimated_reductions (it is currently a conflict) |
| 1408_PD::chunk-000 | estimated_reductions | 37,765,494 | not_stated (gross avoided emissions, not net ERs) |
| 1408_PD::chunk-002 | estimated_reductions | 37,765,494 | not_stated (same reason) |
| 2510_PD::chunk-034 | estimated_reductions | 1,294,618 | not_stated (one monitoring period's NER, not the crediting-period total) |
| 1408_VR_2022::chunk-006 | leakage | -24,408 | -744,376 (-24,408 is the confidence deduction column; same quote) |
| 832_PD_n::chunk-000 | estimated_reductions_pre_buffer | 9,432,299 | not_stated; no buffer mentioned in chunk, so 9,432,299 belongs in estimated_reductions (10-year ex-ante total, as in 832_PD_n::chunk-012) |
