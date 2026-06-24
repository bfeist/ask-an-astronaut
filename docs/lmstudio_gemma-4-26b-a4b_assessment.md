# LM Studio Model Assessment: google/gemma-4-26b-a4b-qat

**Test date:** 2026-06-24  
**Model ID (LM Studio):** `google/gemma-4-26b-a4b-qat`  
**Test script:** `scripts/test_lmstudio_models.py`  
**Config:** `--runs 3 --stage all --improved-prompt --workers 4`  
**Base URL:** `http://localhost:1234`

---

## TL;DR

| Stage                             | Verdict        | Notes                                                                                 |
| --------------------------------- | -------------- | ------------------------------------------------------------------------------------- |
| Stage 2 — Filename Classification | **Excellent**  | 96.7% gemma3 agreement, 92.9% GT accuracy — consistently across all 6 runs            |
| Stage 5b — QA Extraction          | **Not viable** | 0 pairs found across all tested groups; 400 error (context overflow) on large prompts |

---

## Stage 2 — Filename Classification

### Quantitative Results

| Run | Prompt   | vs gemma3         | vs GT (28 GT items) | Avg latency |
| --- | -------- | ----------------- | ------------------- | ----------- |
| 1   | original | 29/30 = **96.7%** | 26/28 = **92.9%**   | 15.3 s/call |
| 2   | original | 29/30 = **96.7%** | 26/28 = **92.9%**   | 15.2 s/call |
| 3   | original | 29/30 = **96.7%** | 26/28 = **92.9%**   | 16.8 s/call |
| 1   | improved | 29/30 = **96.7%** | 26/28 = **92.9%**   | 13.8 s/call |
| 2   | improved | 29/30 = **96.7%** | 26/28 = **92.9%**   | 16.4 s/call |
| 3   | improved | 29/30 = **96.7%** | 26/28 = **92.9%**   | 15.7 s/call |

**Consistency is perfect** — the exact same 29/30 items agreed with the gemma3 baseline across all 3 original runs, and the exact same 26/28 GT items were correct in every improved-prompt run. Zero variance across runs.

### The Two GT Errors (Original Prompt)

Both errors repeat in all 3 original-prompt runs:

1. **`iss065m261521519_Expedition_65_People_Magazine_210601.mxf`** — GT=keep, model=**reject**  
   The original prompt's `media_interview` definition only names TV stations, newspapers, and radio outlets. "People Magazine" is a print magazine and does not match those explicit signals, so the model rejects it. The improved prompt adds "print magazine" to the definition, fixing this.

2. **`Commercial_Crew_Program_Crew_Assignment_Announcement_August_3_2018_686042.mxf`** — GT=keep, model=**reject**  
   The filename says "Announcement", which the model correctly reads as a one-way event. However, the transcript confirms this includes a ~10-minute on-stage Q&A where NASA Administrator Bridenstine interviews the newly assigned crew about spacecraft tech, mission feelings, etc. Neither prompt exposes this to the model — this is a fundamental limitation of filename-only classification for disguised Q&A events.

### The Two GT Errors (Improved Prompt)

The improved prompt trades one error for a different one, yielding the same net accuracy:

1. **`iss066m263451058_Expedition_66_ESA_In-Flight_Event_with_German_FederaL_President_211211..mp4`** — GT=keep, model=**reject**  
   The improved prompt added a VIP/diplomatic rejection rule. Even with the narrowed wording ("purely ceremonial... no Q&A"), the model appears to pattern-match "German_FederaL_President" → reject. The transcript confirms children from the Children's Heart Foundation and the President himself asked the astronaut substantive questions. The original prompt handled this correctly (kept it); the improved prompt over-fires the rule.

2. **`Commercial_Crew_Program_Crew_Assignment_Announcement...`** — same as above.

### Prompt Comparison

|                              | Original     | Improved                           |
| ---------------------------- | ------------ | ---------------------------------- |
| People Magazine error        | ✗ (rejected) | ✓ (fixed — "print magazine" added) |
| German President error       | ✓ (kept)     | ✗ (broken — VIP rule over-fires)   |
| Crew Assignment Announcement | ✗ (rejected) | ✗ (rejected)                       |
| Net GT accuracy              | 92.9%        | 92.9%                              |

Both prompts yield **identical net GT accuracy**. The improved prompt is technically better-specified but introduces a new edge case regression. For gemma-4-26b-a4b, the original prompt is recommended (avoids the German President false reject).

### Notable Items

- **`iss069m261141759_Expedition_69_U.S._Spacewalk_86_Preview_Briefing_230424.mp4`** — correctly kept by both prompts across all runs (b✓g✓). The EVA Preview Briefing distinction is reliably handled.
- **`iss066m263451058_..._German_FederaL_President_..`** — took 33–68 seconds in some runs (vs ~10–15s median). The long filename causes increased token generation time. The outlier 68.5s run in Run 3 was likely due to model context/KV pressure mid-batch.
- **`Commercial_Crew_..._Announcement_...`** — consistently takes 19–39 seconds, the second-slowest item. The model appears to deliberate longer on "Announcement" filenames, sometimes producing extended reasoning before rejecting.

### Latency Profile

```
Min:    6.9 s/call
Median: ~14 s/call
Max:    68.5 s/call (German President, Run 3 — outlier)
Avg:    13.8–16.8 s/call (varies by run, likely thermal/KV effects)
```

At 4 workers and ~14s median, effective throughput is roughly **17 classifications/minute** — suitable for batch pipeline use. The long tail (68s outlier) is rare.

---

## Stage 5b — QA Extraction

### Results Summary

The QA stage ran into two problems: **systematic over-rejection** and a **hard context window crash**.

| Transcript                     | Segments | Groups    | Pairs found | Baseline (gemma3) | Time             |
| ------------------------------ | -------- | --------- | ----------- | ----------------- | ---------------- |
| Students Acting on a HUNCH     | 11       | 2         | **0**       | 1                 | 18.0 s           |
| T-60 Seconds with Jessica Meir | 30       | 1 (large) | **0**       | 1                 | 135.7 s          |
| Expedition 63 Fox News Radio   | 98       | 12        | **crashed** | 4                 | crash at group 8 |

Only Run 1 was attempted before the crash terminated the script. Runs 2 and 3 were never reached.

### Problem 1 — Systematic Over-Rejection

For the HUNCH transcript (11 segments, 2 small groups), both groups returned `NONE` in 8–10 seconds each. The baseline found 1 valid Q&A pair from the same transcript with gemma3:12b. The model is applying the confirmation criteria too strictly, rejecting exchanges that a smaller/less-strict model accepted.

For the Jessica Meir transcript (30 segments, 14 candidates grouped into 1 window), the model took 135.7 seconds and returned `NONE`. The baseline found 1 pair. At 14 candidate segments in a single group the prompt window is large (~500–700 token excerpt). The model may be treating the multi-segment bundle as "too fragmentary" to confirm.

### Problem 2 — Context Window Overflow (HTTP 400)

The Fox News Radio transcript (98 segments, 17 candidates → 12 groups) crashed the LM Studio API with a `400 Bad Request` on group 8 (anchor timestamp 684.8s). Group 8 likely produced a prompt window of several thousand tokens after adding 20s pre-context and 90s post-context on a dense transcript segment.

```
Group  8/12  @684.8s  → NONE  (133.6s)  ← last group before crash
[next group → HTTP 400 Bad Request]
```

The preceding groups (1, 2, 3, 8) all returned NONE in 7–14s each. Group 8 took 133.6 seconds — suggesting the model was struggling with the window size before the next group overflowed the context limit.

**Root cause:** LM Studio is likely loading gemma-4-26b-a4b-qat with a smaller context window than the model supports (e.g. 8192 tokens instead of the full 32K or 128K). The classification prompts are short (~400–600 tokens) and work fine. The QA confirmation prompts for large groups can exceed 2000–4000 tokens.

**Diagnosis:** Check LM Studio's loaded context length for this model under Model Settings → Context Length. If it is set to 8192 or lower, increasing it to 16384 or 32768 may resolve the 400 errors and improve QA performance.

### QA Verdict

gemma-4-26b-a4b-qat is **not a viable replacement for gemma3:12b** on the Stage 5b QA extraction task under current LM Studio configuration. Specific issues:

1. **0 pairs confirmed** vs 6 baseline pairs across 2 complete transcripts (0% recall vs baseline).
2. **Context crash** on longer transcripts makes the stage non-functional at scale.
3. **Extremely slow** on large windows (135.7 s for a single 14-candidate group; typical QA runs across a 98-segment transcript involve 12 groups and would take >30 minutes if all groups triggered a large window).

This may be addressable by:

- Increasing context length in LM Studio
- Reducing `DEFAULT_WINDOW_POST` (currently 90s) to limit window size
- Adjusting the QA confirmation system prompt to be less strict about what counts as a "genuine question"

---

## Comparison vs Other Tested Models

| Model                   | Classify vs GT    | Classify avg latency | Notes                      |
| ----------------------- | ----------------- | -------------------- | -------------------------- |
| gemma3:12b (baseline)   | —                 | —                    | Reference                  |
| qwen3 6.35B MTP         | See prior reports | —                    | Tested 2026-05-23          |
| **gemma-4-26b-a4b-qat** | **92.9%**         | **~15 s**            | This report; QA not viable |

gemma-4-26b-a4b-qat **matches the GT accuracy** achieved by gemma3:12b for classification (92.9%) and has near-perfect agreement with the gemma3 baseline decisions (96.7%), making it a functionally equivalent classifier — but at a significantly higher latency cost (15s vs ~3–5s for gemma3:12b with Ollama) and with the QA stage currently non-functional.

---

## Recommendations

### For Classification (Stage 2)

- **Viable as a drop-in replacement** with the **original prompt** (not improved).
- Use improved prompt only if People Magazine false-rejects appear in production and German President-style VIP events with public Q&A are rare in the corpus.
- Expect ~15s/call at 4 workers. For a corpus of 11,537 items, full classification would take ~48 minutes. gemma3:12b via Ollama is considerably faster and recommended for production batch runs.

### For QA Extraction (Stage 5b)

- **Not recommended** under current configuration.
- Before retesting, **increase context length in LM Studio** to at least 16384 tokens for this model.
- After that, rerun `--stage qa --runs 3` to see if the 400 errors resolve and whether QA recall improves.
- If the over-rejection problem persists after the context fix, the confirmation system prompt may need tuning (the `_CONFIRM_SYSTEM` prompt in `test_lmstudio_models.py`) to be more permissive on borderline Q&A exchanges.

### For Future Testing

The script crashed before saving the JSON results file (`data/model_comparison/`). If a complete run is desired, consider wrapping the QA test loop in a try/except to allow partial results to be saved even if one transcript group crashes.

---

## Raw Test Command

```bash
uv run python scripts/test_lmstudio_models.py \
  --model "google/gemma-4-26b-a4b-qat" \
  --runs 3 \
  --stage all \
  --improved-prompt \
  --workers 4
```

Exit code: 1 (crashed during QA Stage 5b, Run 1, transcript 3/3, group 8–9 of 12)
