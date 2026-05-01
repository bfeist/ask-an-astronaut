# Ask an Astronaut

Part of [issinrealtime.org](https://issinrealtime.org). A searchable database of questions and answers from NASA astronaut Q&A sessions and interviews. Ask a question in natural language, find the closest real question asked by a student or journalist, and jump straight to that moment in the video.

The frontend runs entirely client-side — no server required after the search index is built.

## How It Works

**Data pipeline** (Python, `scripts/`):

1. `1_scan_ia_metadata.py` — search Internet Archive for NASA JSC PAO videos; write `data/ia_video_metadata.jsonl`
2. `2_classify_candidates.py` — use a local LLM (Ollama) to filter out non-dialogue footage; write `data/classified_candidates.jsonl`
3. `3_download_lowres.py` — download low-res versions of relevant videos
4. `4_transcribe_videos.py` — transcribe with WhisperX (large-v3 + forced alignment + optional speaker diarization); write `data/transcripts/`
5. `5b_extract_qa_perseg.py` — use LLM to extract Q&A time boundaries per segment; write `data/qa/`
6. `5c_build_qa_text.py` — reconstruct verbatim Q&A text from transcript slices; write `data/qa_text/`
7. `6_build_search_index.py` — embed all questions and write a static binary index to `static_assets/data/search_index/`

**Web frontend** (React + Vite, `src/`):

- Loads the static index and runs semantic search in-browser via `@xenova/transformers`
- Displays matching questions and plays the answer segment in the source video

## Quick Start

```bash
uv sync
```

Run the harvest pipeline (steps 1–3):

```bash
uv run python scripts/run_pipeline.py --steps 1 2 3 --model gemma3:12b
```

Transcribe downloaded videos (step 4):

```bash
uv run python scripts/4_transcribe_videos.py
```

Extract Q&A and build the search index (steps 5–7):

```bash
uv run python scripts/5b_extract_qa_perseg.py
uv run python scripts/5c_build_qa_text.py
uv run python scripts/6_build_search_index.py
```

Start the frontend:

```bash
npm install
npm run dev
```

Verify frontend after changes:

```bash
npm run test:all
```

## Requirements

- Python 3.11+, `uv`
- [Ollama](https://ollama.com) running locally (for steps 2, 5b)
- CUDA GPU recommended for steps 4–7 (WhisperX transcription, Q&A extraction, and embedding generation)
- `HF_TOKEN` env var for speaker diarization (optional)

## Documentation

- [docs/architecture.md](docs/architecture.md)
- [docs/classification_strategy.md](docs/classification_strategy.md)
- [docs/operations.md](docs/operations.md)
- [docs/vision.md](docs/vision.md)
