# Chunking

Chunking is an **ingestion-time** concern: documents are never re-chunked per query. Multiple
chunk representations ("profiles") can be indexed side by side in one collection; retrieval selects
representations through the `chunk_profile` payload filter.

## Legal structure first

`app/rag/documents/structure.py` turns cleaned text into `LegalUnit`s — Sections (incl. bare-act
style `420. Heading.—Text`), Articles, Schedules, numbered judgment paragraphs, preamble/body — with
Part/Chapter context, and inside each unit `LegalBlock`s: sub-sections `(1)`, clauses `(a)`,
Explanations, Exceptions, Illustrations, Provisos, definitions. Every strategy splits **within a
unit**, so a chunk never crosses a section boundary, and every chunk carries a context header
(`Indian Penal Code, 1860 › Chapter XVII › Section 420 — Cheating…`) used for embedding and display.

## Strategies (`app/rag/chunking/`)

All implement `ChunkingStrategy.chunk(StructuredDocument) -> list[Chunk]` and share `ChunkMetadata`.

| Strategy | Behaviour |
|---|---|
| `fixed` | token windows with overlap (baseline); `respect_structure: false` gives the naive whole-document baseline |
| `sentence` | packs whole sentences (legal-abbreviation-aware splitter: `s.`, `v.`, `I.P.C.`, initials) |
| `recursive` | blocks → paragraphs → lines → sentences → clauses → tokens, then packs |
| `semantic` | embedding-distance breakpoints between sentences (percentile or absolute threshold) |
| `sliding_window` | windows of N sentences, stride S, token ceiling enforced by trimming whole sentences |
| `hierarchical` | parent per unit (or block group) at level 0 + recursive children linked by `parent_chunk_id` |
| `ai` | LLM proposes boundaries over numbered sentences; validated; recursive fallback; call budget |

Profiles live in `config/chunking_profiles.json` (default `hierarchical-400`, within the 120–512
token band agreed in the 2026-01-09 meeting). Sizes are approximate tokens (`count_tokens`: word +
punctuation units; sub-word tokenizers produce ~1.2–1.4× more).

## Metadata

`chunk_id` (UUIDv5 of document/version/profile/index/content-hash — deterministic), `document_id`,
`document_version` (content-hash based), `source`, `title`, `document_type`, `jurisdiction`, `act`,
`section`, `unit_kind`, `section_heading`, `subsection`, `paragraph`, `page_number`, case fields
(`case_name`, `case_citation`, `court`, `decision_date`), `parent_chunk_id`, `hierarchy_level`,
`block_types`, `chunking_strategy`, `chunk_profile`, `chunk_size`, `overlap`, `token_count`,
`chunk_index`, `char_start`/`char_end` (exact offsets), `semantic_boundary`, `content_hash`,
`created_at`, `effective_date`, `is_latest`, `embedding_model`, `embedding_version`.

## Ingestion

```bash
python scripts/ingest.py --source data/legal_docs                       # default profile
python scripts/ingest.py --source data/legal_docs --profile semantic-p90-400
python scripts/ingest.py --source data/legal_docs --strategy recursive --chunk-size 400 --overlap 50
python scripts/ingest.py --source data/legal_docs --all-profiles         # index every representation
python scripts/ingest.py --source data/legal_docs --dry-run              # parse + chunk only
python scripts/ingest.py --source data/legal_docs --validate             # compare with index, no writes
```

Formats: `.txt`, `.md`, `.pdf` (per-page text with page numbers; scanned PDFs are rejected with a
clear error — OCR is not implemented), `.docx`. Optional `<file>.meta.json` sidecars set
`document_id`, `title`, `document_type`, `act`, `jurisdiction`, dates and case fields.

Versioning: unchanged (document, version, profile) is skipped; a changed document is indexed as a new
version, then older versions are flagged `is_latest=false` (kept for audit, excluded from search).
Each run validates the written point count.
