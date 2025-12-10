# Chunking Improvement Plan: Adopt Chonkie Experimental CodeChunker

## Goals
- Improve code search relevance by using AST-aware chunking from Chonkie’s experimental `CodeChunker`.
- Keep safe fallback to existing token-based chunking while we evaluate.
- Support index/schema and ingestion changes needed for new chunk metadata.

## Scope
- Chunking pipeline: `backend/src/services/search/chunk_embed.py`
- Ingestion pipeline: `backend/src/services/ingestion/embed.py`, `index_writer.py`
- Index configuration: `backend/src/services/search/index_client.py`
- Configuration/flags: `backend/src/config/*`, feature flags if needed
- Dependencies: `chonkie[code]` (tree-sitter, Magika)

## Design Overview
1. **Chunker selection**
   - Default to existing `TokenChunker`.
   - Add experimental path using `from chonkie.experimental import CodeChunker`.
   - Modes (config-driven):
     - `token` (current behavior)
     - `code_auto` (CodeChunker with `language="auto"`, warns about perf)
     - `code_lang_<lang>` (explicit language, e.g., `code_lang_python`, `code_lang_typescript`).
   - Keep `CHUNK_SIZE_TOKENS` as target size; overlap unused for CodeChunker but retained for token mode.

2. **Chunk metadata & mapping**
   - CodeChunker returns `text`, `start_index`, `end_index`, `token_count`.
   - Convert to existing `ChunkResult` with line numbers by mapping start/end character offsets back to the original file text.
   - Preserve `max_chunks` guard and logging; on failure, fall back to token chunker.

3. **Language hints**
   - Derive language from file extension (reuse `FileInfo.extension` mapping). Pass into chunker when mode is language-specific; otherwise allow `auto`.
   - Store `language` in index documents (already present); ensure it’s set in ingestion results when known.

4. **Index/schema**
   - Current fields mostly sufficient. Consider adding optional fields if we want richer context:
     - `start_index`, `end_index` (character offsets) for precise navigation.
     - `chunking_mode` for observability.
   - If added, update `bootstrap_indexes` displayed/sortable attributes accordingly and reindex.

5. **Configuration additions**
   - New setting: `CHUNKER_MODE` (string, default `token`).
   - Optional: `CODE_CHUNKER_TOKENIZER` (default `character`), `CODE_CHUNKER_ADD_SPLIT_CONTEXT` (bool), `CODE_CHUNKER_CHUNK_SIZE` (fallback to `CHUNK_SIZE_TOKENS`).
   - Feature flag to toggle experimental CodeChunker on/off for safe rollback.

6. **Ingestion changes**
   - `EmbedService.process_file`:
     - Pass language hint into chunker when available.
     - Use CodeChunker’s start/end offsets to compute line ranges (replace sequential line counting for better accuracy).
     - Keep `max_chunks` truncation and chunk_id/content_hash logic.
   - Embedding generation remains unchanged.

7. **Chunking service changes (`chunk_embed.py`)**
   - Initialize chunker based on config.
   - Implement CodeChunker path with try/except; on exception, log warning and fallback to TokenChunker.
   - Reuse existing `Chunk`/`ChunkResult` classes; no interface change to callers.

8. **Dependencies**
   - Add/install `chonkie[code]` (brings tree-sitter, Magika). Note: performance impact with `language="auto"`; prefer explicit when possible.

9. **Migration & rollout**
   - If schema fields change or chunking mode switches, reindex repositories (per-branch) to refresh chunk boundaries and metadata.
   - Provide feature flag to disable experimental mode quickly.
   - Maintain backward compatibility in index documents by keeping existing fields; new fields should be optional.

10. **Validation & testing**
    - Unit tests: chunker selection logic, fallback behavior, line-number mapping from start/end offsets, language hint derivation.
    - Integration test: ingest a sample code file, verify chunk count, boundaries, and stored line ranges in produced documents (without hitting Meilisearch, if possible).
    - Smoke test: run ingestion on a small repo and ensure search results show correct line spans.

## Implementation Steps
1. Add config entries/env wiring for `CHUNKER_MODE` and optional CodeChunker settings; expose feature flag to toggle experimental.
2. Update `chunk_embed.py` to instantiate CodeChunker when configured, map chunk offsets to line numbers, and retain token chunker fallback.
3. Update `embed.py` to pass language hints, use new line-mapping logic, and preserve chunk limits and IDs.
4. (Optional) Extend `index_client.bootstrap_indexes` to include `start_index`, `end_index`, `chunking_mode` in displayed/filterable/sortable attributes if we store them.
5. Ensure dependencies include `chonkie[code]` (update `pyproject`/`uv.lock` via dependency add when executing).
6. Add tests for selection/fallback and line mapping; add an integration-style test for ingesting a small code sample.
7. Plan and run reindex after deployment to refresh chunk boundaries.

## Open Questions / Decisions
- Do we store `start_index`/`end_index` and `chunking_mode` in the index, or keep minimal surface? (Impacts reindex.)
- Should `language="auto"` be allowed in production, or require explicit language for performance?
- Do we want to expose per-language chunk_size overrides or just a global value?
- Rollout strategy: staged per-repo/branch vs. global flip?
