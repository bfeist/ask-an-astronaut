# Agent Instructions

## Project

**Ask an Astronaut** — part of [issinrealtime.org](https://issinrealtime.org). A searchable database of questions and answers from NASA astronaut Q&A sessions and interviews. Users ask a question in natural language, find the closest real question asked by a student or journalist, and jump straight to that moment in the video.

Two major components:

- **Python data pipeline** (`scripts/`) — harvest, classify, transcribe, extract Q&A, build search index
- **React frontend** (`src/`) — client-side semantic search via `@xenova/transformers`, HTML5 video playback

Key paths:

- Local videos stored at `D:/ask_anything_ia_videos_raw` (dev only, served by Vite plugin)
- Static search index at `static_assets/data/search_index/` (served as build output)
- Pipeline data output at `data/` (gitignored)

## Verification — IMPORTANT

After any frontend code change, run: `npm run test:all`  
This runs: lint → tsc → build → vitest

For Python changes, run the relevant script directly; there is no automated Python test suite.

## Environment

- Default shell is GitBash (Windows).
- Do NOT start dev servers (`npm run dev`) — assume one is already running.
- For testing and exploration, use temporary scripts rather than modifying existing code.
- Python tooling uses `uv`. Run Python scripts with `uv run python scripts/<name>.py`.

## Pipeline Scripts (in order)

1. `1_scan_ia_metadata.py` — scan Internet Archive for NASA JSC PAO uploads
2. `2_classify_candidates.py` — LLM classification via Ollama (gemma3:12b)
3. `3_download_lowres.py` — download low-res video variants
4. `4_transcribe_videos.py` — WhisperX large-v3 + forced alignment + optional diarization
5. `5b_extract_qa_perseg.py` — extract Q&A time boundaries per segment
6. `5c_build_qa_text.py` — reconstruct verbatim Q&A text
7. `6_build_search_index.py` — embed questions and write binary index

`run_pipeline.py` orchestrates steps 1–3. Steps are resumable (skip already-processed items).

## Subagents

- Subagents are preferred for normal tasks. Use the main agent only for coordination and oversight in order to preserve its context window for high-level reasoning.
