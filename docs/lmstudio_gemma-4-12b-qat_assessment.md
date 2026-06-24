# LM Studio Model Assessment: google/gemma-4-12b-qat

**Test date:** 2026-06-24  
**Model ID (LM Studio):** `google/gemma-4-12b-qat`  
**Context window:** 32768 (upgraded from 8192 default before QA stage)  
**Test script:** `scripts/test_lmstudio_models.py`  
**Config:** `--runs 3 --stage all --improved-prompt --workers 4`  
**Prior assessment for context:** [lmstudio_gemma-4-26b-a4b_assessment.md](lmstudio_gemma-4-26b-a4b_assessment.md)

---

## TL;DR

| Stage                                      | Verdict            | Notes                                                                |
| ------------------------------------------ | ------------------ | -------------------------------------------------------------------- |
| Stage 2 — Classification (original prompt) | **Below baseline** | 85.7% GT accuracy — 4 errors vs 2 for gemma3:12b baseline            |
| Stage 2 — Classification (improved prompt) | **Good**           | 92.9% GT accuracy — matches gemma-4-26b and gemma3 baseline          |
| Stage 5b — QA Extraction                   | **Not viable**     | 0 pairs found; 400 crash on large FoxNews groups even at 32k context |

**Key takeaway:** The 12b QAT model requires the **improved prompt** to reach baseline accuracy. With the original prompt it is meaningfully worse than gemma3:12b and worse than the 26b sibling. With the improved prompt it matches both. QA extraction remains broken regardless of context window size.

---

## Stage 2 — Filename Classification

### Quantitative Results

| Run | Prompt   | vs gemma3         | vs GT (28 items)  | Avg latency |
| --- | -------- | ----------------- | ----------------- | ----------- |
| 1   | original | 27/30 = **90.0%** | 24/28 = **85.7%** | 17.9 s/call |
| 2   | original | 27/30 = **90.0%** | 24/28 = **85.7%** | 21.9 s/call |
| 3   | original | 27/30 = **90.0%** | 24/28 = **85.7%** | 19.9 s/call |
| 1   | improved | 29/30 = **96.7%** | 26/28 = **92.9%** | 18.7 s/call |
| 2   | improved | 29/30 = **96.7%** | 26/28 = **92.9%** | 19.2 s/call |
| 3   | improved | 29/30 = **96.7%** | 26/28 = **92.9%** | 19.1 s/call |

Results are perfectly consistent within each prompt variant (zero variance across all 3 runs).

### Original Prompt — 4 GT Errors (consistent across all 3 runs)

1. **`iss069m261141759_Expedition_69_U.S._Spacewalk_86_Preview_Briefing_230424.mp4`** — GT=keep, model=**reject**  
   The original prompt lists "Spacewalk / EVA coverage" in the reject rules without distinguishing pre/post-mission briefings from actual EVA footage. The 12b model applies this more aggressively than the 26b (which handled this correctly with the original prompt). Latency: 20–53s (high variance — the model deliberates before rejecting).

2. **`iss066m263451058_Expedition_66_ESA_In-Flight_Event_with_German_FederaL_President_211211..mp4`** — GT=keep, model=**reject**  
   The original prompt has no explicit VIP rule, yet the 12b still rejects this. The "German_FederaL_President" string is apparently enough to trigger rejection without any guidance. Both the 12b and 26b reject this with the original prompt... wait: reviewing — the 26b actually _kept_ the German President with the original prompt. The 12b consistently rejects it. This is a regression unique to the 12b.

3. **`iss065m261521519_Expedition_65_People_Magazine_210601.mxf`** — GT=keep, model=**reject**  
   Same failure as the 26b: the original prompt's `media_interview` type lists TV/radio outlets but not print magazines. Latency: 41–45s — the model produces long reasoning before incorrectly rejecting.

4. **`Commercial_Crew_Program_Crew_Assignment_Announcement_August_3_2018_686042.mxf`** — GT=keep, model=**reject**  
   Universal failure across both Gemma 4 sizes and both prompts. The title says "Announcement" and neither model can infer the Q&A content from the filename alone.

### Improved Prompt — 2 GT Errors (consistent across all 3 runs)

The improved prompt fixes errors 1 and 3 from above:

- **Preview Briefing** (item 1 above): correctly **kept** — the improved prompt explicitly adds "NOTE: A 'Preview Briefing' or 'Briefing' about a spacewalk is a PRESS CONFERENCE and should be KEPT."
- **People Magazine** (item 3 above): correctly **kept** — the improved prompt adds "print magazine" to `media_interview` definition.
- **German Federal President**: still incorrectly **rejected** — the improved prompt's narrowed VIP rule ("purely ceremonial diplomatic... with NO Q&A component") was intended to allow Q&A-containing VIP calls, but the 12b still rejects on "German_FederaL_President" alone.
- **Commercial Crew Announcement**: still **rejected** — unfixable by prompt alone.

### Prompt Comparison for gemma-4-12b-qat

| Error                        | Original   | Improved      |
| ---------------------------- | ---------- | ------------- |
| Preview Briefing (EVA)       | ✗ rejected | ✓ fixed       |
| German Federal President     | ✗ rejected | ✗ still wrong |
| People Magazine              | ✗ rejected | ✓ fixed       |
| Commercial Crew Announcement | ✗ rejected | ✗ still wrong |
| **Net GT accuracy**          | **85.7%**  | **92.9%**     |

**Recommendation: Always use the improved prompt with this model.**

### Comparison to gemma-4-26b-a4b-qat

| Metric             | 12b-qat (original) | 12b-qat (improved) | 26b-a4b-qat (original) | 26b-a4b-qat (improved) |
| ------------------ | ------------------ | ------------------ | ---------------------- | ---------------------- |
| vs gemma3 baseline | 90.0%              | 96.7%              | 96.7%                  | 96.7%                  |
| vs GT              | **85.7%**          | **92.9%**          | **92.9%**              | **92.9%**              |
| Avg latency        | ~20 s              | ~19 s              | ~15 s                  | ~16 s                  |

The 26b model reaches 92.9% GT with either prompt. The 12b needs the improved prompt to reach the same level. The 26b is also ~5s faster per call despite being a larger model (likely due to the QAT quantization tradeoffs at 12b).

### Notable Latency Issues

- Preview Briefing (item 4): **20–53 seconds** across runs — extremely high variance. The model produces long chain-of-thought before rejecting. This suggests it's uncertain.
- People Magazine (item 7): **17–45 seconds** — similarly variable. With the improved prompt, it decides faster (~18s, confident keep).
- German Federal President (item 6): **14–30 seconds** — consistent reject, relatively quick.
- McGovern Medical School (item 12): up to 36 seconds — occasional slowdown on educational events with long names.

---

## Stage 5b — QA Extraction

### Context Window Note

The initial 12b run crashed during **Stage 2 classification** (not QA) with HTTP 500 errors — this was an LM Studio model-loading instability at 8k context. The model was reloaded with **32768-token context** before the successful test run. Despite 32k context, QA extraction still crashed.

### Results

| Transcript                     | Segments | Groups    | Pairs found | Baseline | Latency             |
| ------------------------------ | -------- | --------- | ----------- | -------- | ------------------- |
| Students Acting on a HUNCH     | 11       | 2         | **0**       | 1        | 24.1 s total        |
| T-60 Seconds with Jessica Meir | 30       | 1 (large) | **0**       | 1        | 49.1 s              |
| Expedition 63 Fox News Radio   | 98       | 12        | **crashed** | 4        | crash on batch 4–12 |

### Problem 1 — Consistent Over-Rejection

Both small transcripts (HUNCH, Meir) returned 0 pairs despite gemma3:12b finding 1 pair in each. The HUNCH transcript's 2 groups processed in 9.4s and 14.7s each — fast responses that confidently said NONE. The Meir large group processed in 49.1s (faster than the 26b's 135.7s due to smaller model) and also returned NONE.

This confirms the over-rejection is a model behavior issue, not a performance issue. The gemma-4 family appears to apply the QA confirmation criteria more strictly than gemma3:12b, likely due to differences in instruction following and the interpretation of "GENUINE QUESTION criteria."

### Problem 2 — Context Overflow at 32k

FoxNews Radio transcript (98 segments, 12 groups) crashed during the first parallel batch (groups 2, 3 completed; a group in the same batch triggered 400). Groups at later timestamps (e.g. ~347s, ~325s) completed in 11–13s, but another group in the batch overflowed.

The QA confirmation prompt for a single group can exceed 4000–8000 tokens when the group anchor falls in a dense, multi-speaker section (20s pre-context + 90s post-context = up to 110s of 98-segment transcript). At 32k that should fit, but LM Studio may apply a different effective limit (input + output together, or a model-specific cap).

**Comparison to 26b:** The 26b crashed on group 8/12 (~684s timestamp) after spending 133.6s on it. The 12b crashes earlier in the parallel batch (within the first 4 groups processed concurrently). The 12b appears to have a lower effective limit than the 26b under LM Studio at the same 32k setting.

### QA Verdict

Neither gemma-4-12b-qat nor gemma-4-26b-a4b-qat is currently viable for Stage 5b QA extraction:

- Both models consistently return NONE on groups where gemma3:12b confirms valid pairs.
- Both crash with HTTP 400 on large FoxNews groups.
- 32k context at the model level does not resolve the crash — LM Studio may be enforcing a tighter effective token limit for these models.

---

## Comparison to Prior Assessments

| Model                           | Classify GT (original) | Classify GT (improved) | QA Viable                | Classify latency |
| ------------------------------- | ---------------------- | ---------------------- | ------------------------ | ---------------- |
| gemma3:12b (Ollama baseline)    | — (reference)          | —                      | Yes (4 pairs)            | ~3–5 s           |
| qwen3 6.35B MTP (LM Studio)     | see prior reports      | —                      | —                        | —                |
| gemma-4-26b-a4b-qat (LM Studio) | 92.9%                  | 92.9%                  | No (0 pairs + crash)     | ~15 s            |
| **gemma-4-12b-qat (LM Studio)** | **85.7%**              | **92.9%**              | **No (0 pairs + crash)** | **~20 s**        |

The 12b QAT model is the weakest of the tested models on classification when using the original prompt. With the improved prompt it matches the others. It is also the slowest at ~20s/call, which is counterintuitive given its smaller size — the QAT quantization at 12b may be less efficient on this hardware than the a4b MoE quantization of the 26b.

---

## Recommendations

### For Classification (Stage 2)

- **Use the improved prompt** — mandatory for this model. The original prompt misses 4 GT items; the improved prompt gets 2 of them back.
- The remaining 2 errors (German President, Commercial Crew Announcement) are shared with all tested models and are not fixable by prompt alone.
- Latency (~20s/call) is the highest of any tested model. Not recommended for large-scale production batch runs. gemma3:12b via Ollama remains the practical choice.

### For QA Extraction (Stage 5b)

- **Not recommended.** Both the 12b and 26b gemma-4 models fail QA extraction.
- The over-rejection behavior appears to be a characteristic of the gemma-4 model family's interpretation of the confirmation criteria — not a solvable problem by adjusting context window size.
- Consider testing `google/gemma-4-12b` (non-QAT variant) loaded in LM Studio to see if the QAT quantization is the source of the over-rejection, or whether this is a gemma-4 architecture issue.

---

## Raw Test Command

```bash
uv run python scripts/test_lmstudio_models.py \
  --model "google/gemma-4-12b-qat" \
  --runs 3 \
  --stage all \
  --improved-prompt \
  --workers 4
```

Exit code: 1 (crashed during QA Stage 5b, Run 1, transcript 3/3, within first parallel batch of groups)  
Context at crash: 32768 tokens (reloaded from 8192 before run)
