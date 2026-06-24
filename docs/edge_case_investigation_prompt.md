# Edge-Case Video Investigation — Session Prompt

## Context

This project (`f:\_repos\ask-an-astronaut`) has a test script
`scripts/test_lmstudio_models.py` that evaluates LLM classifiers against a
30-item ground-truth set (`GROUND_TRUTH` dict in the file).

Two entries in GROUND_TRUTH need human-verified decisions based on the actual
video content. Your job is to:

1. Read the existing transcript for the German Federal President video.
2. Download and transcribe the Crew Assignment Announcement video.
3. Determine from the transcripts whether each video contains genuine Q&A
   (press, students, or public asking an astronaut questions).
4. Update `GROUND_TRUTH`, `GT_DISAGREEMENT_NOTES`, and
   `_CLASSIFY_PROMPT_IMPROVED` in `scripts/test_lmstudio_models.py` to reflect
   your verified decisions.

---

## Video 1 — German Federal President VIP Call

**Current GROUND_TRUTH entry:**

```python
"iss066m263451058_Expedition_66_ESA_In-Flight_Event_with_German_FederaL_President_211211..mp4": "reject",
# Diplomatic/ceremonial VIP call with head of state; not a structured Q&A event
```

**gemma3 baseline decision:** keep  
**Improved test prompt decision:** reject

**Transcript already exists:**

```
data/transcripts/iss066m263451058_Expedition_66_ESA_In-Flight_Event_with_German_FederaL_President_211211._lowres.json
```

(220 segments, ~75s processing time)

**Your task:** Read the transcript. Look for:

- Are there questions from press, students, or members of the public?
- Or is it only ceremonial/diplomatic exchange between the President and the
  crew (greetings, congratulations, prepared statements)?
- Does the President actually ask substantive questions that the crew answers
  (interview-style), or just exchange pleasantries?

**Decision guide:**

- If there are genuine Q&A exchanges from press/public → change GT to "keep"
  and **also remove** the "Diplomatic/VIP ceremonial in-flight calls" reject
  rule from `_CLASSIFY_PROMPT_IMPROVED` (or narrow it).
- If it's purely ceremonial/diplomatic with no Q&A value → keep GT as
  "reject" and keep the rule.

---

## Video 2 — Crew Assignment Announcement

**Current GROUND_TRUTH entry:**

```python
"Commercial_Crew_Program_Crew_Assignment_Announcement_August_3_2018_686042.mxf": "reject",
# Announcement event; one-directional, no interactive Q&A format
```

**gemma3 baseline decision:** reject  
**Both original and improved test prompts:** keep (the prompts think it's a
press conference because crew assignment events often include Q&A)

**No transcript exists yet.** The video is ~46 minutes long (2757 seconds).

**IA metadata entry** (`data/ia_video_metadata.jsonl`):

```json
{
  "identifier": "Commercial_Crew_Program_Crew_Assignment_Announcement_August_3_2018_686042.mp4",
  "title": "Commercial Crew Program Crew Assignment Announcement August 3 2018 686042",
  "IA_file_metadata": { "format": "MPEG4", "size": "4127830814", "length": "2757.15" }
}
```

**Steps to download and transcribe:**

1. First check if the video was already downloaded to the video storage
   directory. Run:

   ```bash
   ls D:/ask_anything_ia_videos_raw/ | grep -i "686042\|Crew_Assignment" 2>&1
   ```

   or check `data/download_log.csv`:

   ```bash
   grep -i "686042\|Crew_Assignment" data/download_log.csv | head -5
   ```

2. If not downloaded, find the correct IA item identifier. The field
   `identifier` in `ia_video_metadata.jsonl` includes the file extension
   (`.mp4`/`.mxf`) — the actual IA item identifier is likely the base name
   without extension. Check `scripts/3_download_lowres.py` to understand how
   it resolves IA identifiers, then try:

   ```bash
   uv run python scripts/3_download_lowres.py --identifier "Commercial_Crew_Program_Crew_Assignment_Announcement_August_3_2018_686042"
   ```

   If that fails, look the item up on Internet Archive:
   `https://archive.org/details/Commercial_Crew_Program_Crew_Assignment_Announcement_August_3_2018_686042`

3. Once downloaded, transcribe:

   ```bash
   uv run python scripts/4_transcribe_videos.py --file "D:/ask_anything_ia_videos_raw/Commercial_Crew_Program_Crew_Assignment_Announcement_August_3_2018_686042_lowres.mp4"
   ```

4. Read the transcript. Look for:
   - Is there a press Q&A portion after the announcement?
   - Are reporters asking questions? Do they say "question" or is it a free
     Q&A format?
   - Or is it purely one-directional: NASA officials make statements, no
     questions taken?

**Decision guide:**

- If it has a press Q&A portion → change GT to "keep" and add a
  `GT_DISAGREEMENT_NOTES` entry explaining gemma3 under-kept it.
- If it truly has no Q&A → keep GT as "reject" and add a rule or example to
  `_CLASSIFY_PROMPT_IMPROVED` to reinforce rejecting pure "Announcement"
  events (so the test prompt stops incorrectly keeping it).

---

## What to update in `scripts/test_lmstudio_models.py`

### `GROUND_TRUTH` dict (lines ~96–148)

Update the two entries based on your verified decisions:

```python
"iss066m263451058_Expedition_66_ESA_In-Flight_Event_with_German_FederaL_President_211211..mp4": "keep_or_reject",
"Commercial_Crew_Program_Crew_Assignment_Announcement_August_3_2018_686042.mxf": "keep_or_reject",
```

### `GT_DISAGREEMENT_NOTES` dict (lines ~150–165)

Add/update entries for whichever video now disagrees with a model:

```python
"iss066m263451058_...": "explanation of why GT=X while model=Y",
"Commercial_Crew_Program_...": "explanation",
```

### `_CLASSIFY_PROMPT_IMPROVED` string (lines ~172–260)

- **German President:** If you keep GT=reject (no Q&A), the current
  "Diplomatic/VIP ceremonial" reject rule is correct → no change needed.
  If you change GT=keep, remove or narrow that rule so it only rejects
  _purely_ ceremonial calls (no questions), not diplomatic calls that happen
  to include Q&A.

- **Crew Assignment:** If you change GT=keep, no change needed (the prompt
  already correctly keeps it). If GT stays "reject", add an explicit note
  that "Announcement" events without a press conference component should be
  rejected, e.g.:
  ```
  - Pure announcement events with no Q&A portion (e.g. "Crew Assignment
    Announcement" that is only a statement, no press questions)
  ```

---

## Notes on the pipeline

- Python env: `uv`
- Project root: `f:\_repos\ask-an-astronaut`
- Video storage: `D:/ask_anything_ia_videos_raw/`
- Transcripts: `data/transcripts/`
- The German President transcript exists and was produced by WhisperX
  `large-v3` with diarization — speaker labels are available. Use them to
  distinguish who is asking questions vs. answering.
- If the Crew Assignment download fails or takes too long, skip it and
  document that GT=reject is unverified (provisionally correct based on event
  title).
- After your changes, run the classify test to verify the new GT accuracy:
  ```bash
  uv run python scripts/test_lmstudio_models.py --base-url http://localhost:11434 --model gemma3:12b --stage classify --runs 1
  ```
  The expected baseline (before your changes) was 89.3% vs GT. After
  correcting GT, this number should go up if gemma3 was right about these
  two videos.
