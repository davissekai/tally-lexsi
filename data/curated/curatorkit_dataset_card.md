# Dataset Card: tally_tinyaya_sft_curation

## Summary

- **Run timestamp**: 2026-11-13T09:14:23.684700Z
- **Wall clock time**: 21.6s
- **Pipeline config hash**: `98a71500bb3a03dc`

## Source Documents

  - Unknown

## Pipeline Stages

| Step | Input | Passed | Recovered | Rejected | Forward |
|------|-------|--------|-----------|----------|---------|
| JSONLReader | 417 | 417 | — | 0 | 417 |
| SchemaGate | 417 | 417 | 0 | 0 | 417 |
| ExactDeduplicator | 417 | 417 | — | — | 417 |
| MinHashDeduplicator | 417 | 417 | — | — | 417 |
| TextCleaner | 417 | 417 | — | — | 417 |
| AlpacaExporter | — | 417 | — | — | 417 |
| ShareGPTExporter | — | 417 | — | — | 417 |
| MessagesExporter | — | 417 | — | — | 417 |

## Gate Pass Rates and Rejection Breakdown

- **JSONLReader**: 417/0 passed (N/A), 0 rejected
- **SchemaGate**: 417/417 passed (100.0%), 0 rejected


**Rejection reasons:**
  - None

## Deduplication

  - near_duplicates_removed: 0
  - surviving_count: 417

## Known Limitations

- MinHash threshold used: **0.85** — this is a starting point, not a universal answer. Adjust per domain (legal, medical, and other domain-specific corpora may need a lower threshold to avoid losing structurally similar but semantically valid examples).
- Table extraction requires `extract_tables: true` on the PDF reader and MinerU with GPU support. Disabled by default.
- Token counting uses a whitespace tokenizer by default. For exact LLM context window
  enforcement, enable `use_tiktoken: true` in the SchemaGate config.
- Both within-run (MinHash/Diversity) and cross-run (EmbeddingDeduplicator) deduplication
  are available. Cross-run dedup persists an embedding index across runs; use
  `embedding_reset_index: true` to start fresh.

## Reproduction

```bash
pip install curatorkit
curatorkit run pipeline.yaml --output-dir ./out/
```

## Tool Versions

- **curatorkit**: 0.1.27
- **python**: 3.13.5
