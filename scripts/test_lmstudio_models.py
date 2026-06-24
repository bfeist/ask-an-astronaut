#!/usr/bin/env python3
"""Model comparison test: LM Studio models vs gemma3:12b baseline.

Tests both pipeline stages that use LLMs:
  Stage 2 — filename classification (classify_filename_with_ollama)
  Stage 5b — Q&A extraction (call_ollama / confirm_candidate)

Scoring uses two independent references:
  - gemma3:12b baseline — what the existing pipeline decided
  - Ground Truth (GT)   — manually assessed by Claude Sonnet 4.6; used as the
                          authoritative reference when the two models disagree

Usage:
  # Test the currently-loaded LM Studio model vs gemma3 baseline + GT:
  uv run python scripts/test_lmstudio_models.py

  # Also compare original prompt vs improved prompt for classification:
  uv run python scripts/test_lmstudio_models.py --improved-prompt

  # Specify a different model ID:
  uv run python scripts/test_lmstudio_models.py --model qwen3.6-27b-pure

  # More runs for better statistics:
  uv run python scripts/test_lmstudio_models.py --runs 5

  # Only test one stage:
  uv run python scripts/test_lmstudio_models.py --stage classify
  uv run python scripts/test_lmstudio_models.py --stage qa

  # List available LM Studio models:
  uv run python scripts/test_lmstudio_models.py --list-models

Results are saved to: data/model_comparison/<model_id>_<timestamp>.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from astro_ia_harvest.config import (  # noqa: E402
    CLASSIFIED_JSONL,
    QA_DIR,
    TRANSCRIPTS_DIR,
)
from astro_ia_harvest.jsonl_utils import load_jsonl  # noqa: E402
from astro_ia_harvest.qa_utils import parse_pipe_qa, _validate_qa_pairs  # noqa: E402
from astro_ia_harvest.transcript_utils import load_transcript  # noqa: E402

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

LMSTUDIO_BASE_URL = "http://localhost:1234"
LMSTUDIO_CHAT_URL = f"{LMSTUDIO_BASE_URL}/v1/chat/completions"
LMSTUDIO_MODELS_URL = f"{LMSTUDIO_BASE_URL}/v1/models"

# ---------------------------------------------------------------------------
# Ground truth — manually assessed by Claude Sonnet 4.6
#
# These 30 filenames are the deterministic sample produced by build_classify_sample()
# (evenly-spaced from gemma3:12b keeps / rejects in classified_candidates.jsonl).
# Decisions are independent of either model being tested.
#
# Key divergences from gemma3:12b baseline:
#   reject  iss066m...German_Federal_President  — diplomatic VIP call, ceremonial, not Q&A
# Key divergences from 35B MTP baseline (run 1):
#   keep    iss069m...Spacewalk_86_Preview_Briefing  — press BRIEFING about EVA, not EVA footage
#   keep    iss065m...People_Magazine              — named magazine = media_interview
# ---------------------------------------------------------------------------

GROUND_TRUTH: dict[str, str] = {
    # --- keeps ---
    "iss074m260301600-Crew12_Mission_Overview_News_Conference_260130_2304442.ia.mp4": "keep",
    # "Mission_Overview_News_Conference" — explicit press_conference
    'iss073m262461622_NASA_Astronauts_Discuss_Life_In_Space_With_Fox_News_"America\'s_Headquarters_And_Bill_Hemmer".mxf': "keep",
    # "Discuss_Life_In_Space_With_Fox_News" — explicit media_interview
    "iss070m260861703_Expedition_70_Astronaut_Mike_Barratt_Talks_with_KGW-TV_Portla.mp4": "keep",
    # "Talks_with_KGW-TV" — explicit media_interview
    "iss069m261141759_Expedition_69_U.S._Spacewalk_86_Preview_Briefing_230424.mp4": "keep",
    # "Preview_Briefing" = press briefing ABOUT the EVA, not EVA footage; has Q&A
    "jsc2022m000079-Crew-4_Interview_for_Media_Kjell_Lindgren.mxf": "keep",
    # "Interview_for_Media" — explicit
    "iss065m261521519_Expedition_65_People_Magazine_210601.mxf": "keep",
    # Named national magazine = media_interview; astronaut interviews with People Mag are Q&A
    "iss064m260151634_Expedition_64_CNBC_210115.mp4": "keep",
    # CNBC = named media outlet
    "iss063m261681528_Expedition_63_Inflight_CBS_News_Fox_Business_CNN_Business_200616.mp4": "keep",
    # Multiple named outlets, inflight format
    "iss061m263471629_Expedition_61_Inflight_Second_Baptist_School_2019_1213.mxf": "keep",
    # "Inflight_Second_Baptist_School" — student_qa
    "iss059m261161604_Expedition_59_CSA_PAO_Inflight_with_Stonepark_Intermediate_20.mxf": "keep",
    # "Inflight_with_Stonepark_Intermediate" — student_qa
    "Expedition_56_Interview_with_McGovern_Medical_School_2018_0927_707489.mp4": "keep",
    # "Interview_with_McGovern_Medical_School" — education interview
    "Expedition_55_Education_In-Flight_Queens_University_Kingston_637022.mxf": "keep",
    # "Education_In-Flight" with named university — student_qa
    "Inflight-Event_Santa-Monica-High-School_2017_303_1545_579457.mxf": "keep",
    # "Inflight-Event" with named school — student_qa
    "Press-Conference_One-Year-Crew-Briefing_2016_064_1855_354991.mxf": "keep",
    # "Press-Conference" — explicit
    # --- rejects ---
    "iss066m263451058_Expedition_66_ESA_In-Flight_Event_with_German_FederaL_President_211211..mp4": "keep",
    # Transcript-verified: children from Children's Heart Foundation + Federal President ask astronaut Matthias Maurer substantive Qs; hybrid VIP + student_qa event; filename is misleading
    "jsc2026m000039_NASA's_Space-X_Crew-12_Arrival_&_Welcoming_Remarks_Part-1_260214.ia.mp4": "reject",
    # "Arrival_&_Welcoming_Remarks" = ceremony, not Q&A
    "L002109_FR-D037.mpg": "reject",
    # Opaque archival code; no event-type signal
    "Expedition_67_Crew-3_Return_Part5_220505_1630616.mp4": "reject",
    # "Crew-3_Return_Part5" = return coverage footage
    "CRS-22_Unpacking_HD-DL-2_2021_156_1858_25333_1483929.mxf": "reject",
    # Cargo unpacking footage
    "iss063m262621459_SpaceCast_Weekly_200918.mxf": "reject",
    # "SpaceCast_Weekly" = narrated weekly recap
    "EXP_61_Spacewalk_58_part4_2019_1018_1261642.mp4": "reject",
    # "Spacewalk_58_part4" = actual EVA footage
    "ISS-Downlink-Video_VIEW-OF-CREW-DRAGON_DL-6_2019_062_1258_763591.mp4": "reject",
    # Raw camera feed
    "Commercial_Crew_Program_Crew_Assignment_Announcement_August_3_2018_686042.mxf": "keep",
    # Transcript-verified: NASA Administrator Bridenstine conducts on-stage Q&A with all newly assigned astronauts (~600s); substantive Qs about spacecraft tech, mission readiness, feelings
    "ISS-Downlink-Video_Bresnik-Acaba-EMU-return-SPX-13-unpack-OA-8_DL-5_2017_346_1310_594227.mxf": "reject",
    # Suit/cargo unpacking footage
    "DL-2_2017_041_0207_476924.mxf": "reject",
    # Generic downlink number; no event-type signal
    "ISS-Downlink-Video_DL-1_2016_266_1133_424669.mxf": "reject",
    # Generic downlink
    "VWR 2016-00054_803837_STS-125 139 IMAX HST Release.mxf": "reject",
    # IMAX film release footage
    "Space-Station-Live_2015_1014_1456_307970.mxf": "reject",
    # "Space-Station-Live" = narrated live show
    "Soyuz_Undocking_June-11-2015_268492.mxf": "reject",
    # Undocking coverage
    "jcs2024m000039_Space to Ground_539_240920.mp4": "reject",
    # "Space to Ground" = weekly recap series
}

# Human-readable notes on why ground truth differs from a given model
GT_DISAGREEMENT_NOTES: dict[str, str] = {
    # differs from improved prompt (improved=reject, GT=keep); gemma3 was correct
    "iss066m263451058_Expedition_66_ESA_In-Flight_Event_with_German_FederaL_President_211211..mp4":
        "Transcript-verified keep: children from Children's Heart Foundation ask astronaut Maurer substantive Qs; Federal President also asks. gemma3 correctly kept. Improved prompt over-rejects on 'diplomatic/VIP' rule. GT corrected reject→keep.",
    # differs from gemma3 (gemma3=reject, GT=keep); both prompts were correct
    "Commercial_Crew_Program_Crew_Assignment_Announcement_August_3_2018_686042.mxf":
        "Transcript-verified keep: NASA Admin Bridenstine interviews newly assigned crew on stage (~1480–2071s) with substantive Qs about spacecraft, tech differences, mission feelings. gemma3 over-rejected on 'Announcement' title. GT corrected reject→keep.",
    # differs from 35B (35B=reject, GT=keep)
    "iss069m261141759_Expedition_69_U.S._Spacewalk_86_Preview_Briefing_230424.mp4":
        "'Preview_Briefing' is a press conference ABOUT the EVA, not EVA coverage itself. 35B over-applied spacewalk rule.",
    "iss065m261521519_Expedition_65_People_Magazine_210601.mxf":
        "People Magazine is a named national publication; astronaut interviews with named outlets are media_interview. 35B too strict.",
}


# ---------------------------------------------------------------------------
# Improved classification prompt
#
# Addresses two confirmed error patterns vs ground truth:
#   1. "Spacewalk/EVA coverage" clarified to mean actual EVA footage, NOT
#      pre/post-mission briefings or press conferences about the EVA.
#   2. media_interview explicitly includes print magazines and publications.
#   3. Diplomatic VIP rule narrowed: only purely ceremonial calls (no Q&A) are rejected;
#      calls with heads of state that include Q&A from public/children are kept.
# ---------------------------------------------------------------------------

_CLASSIFY_PROMPT_IMPROVED = """\
You are classifying NASA video files to find interactive Q&A events worth transcribing.

CRITICAL: The **filename** is the most reliable indicator of what a video contains. \
The title, description, and subject fields often describe the parent *collection* \
(e.g. "Crew-11 Content", "Resource Reel") rather than the individual video. \
Always prioritize the filename over title/description/subject. If the filename \
clearly indicates a news conference, interview, or education event, KEEP it \
regardless of what the other fields say.

The downstream pipeline only processes these event types:
  1. student_qa — School downlinks, ARISS contacts, education inflight events where students ask an astronaut questions. Key signals in filename: "Education Inflight", "Inflight with [school/org]", "EDU_Inflight", "ARISS", "school", "student", "ham radio", any organization or media outlet name after "Inflight" (e.g. "Inflight_HCHSA", "Inflight_NOGGIN", "Inflight_CNBC").
  2. press_conference — News conferences, pre-launch/post-flight/post-mission press briefings, flight readiness reviews with Q&A. Includes pre-EVA/spacewalk preview briefings (these are press events about the EVA, not EVA footage). Key signals in filename: "News_Conference", "News Conference", "Press_Conference", "Postflight", "Post-Flight", "Post_Flight", "Pre-Launch", "Flight_Readiness", "Mission_Overview_News", "Preview_Briefing", "Briefing".
  3. media_interview — An astronaut discussing life in space with a specific media outlet: TV station, radio station, newspaper, or **print magazine** (e.g. People Magazine, TIME, Scientific American). Key signals in filename: "Discusses_Life_In_Space", "Talks_with", "Discuss", "Interview_with", any named media outlet (e.g. WTKR-TV, NPR, CNBC, KHQ-TV, People_Magazine, Fox_News, CBS_News).
  4. panel — Panel discussions or roundtables with multiple speakers.

KEEP files whose **filename** clearly matches one of the four types above.

REJECT everything else, including:
  - Space to Ground weekly recap segments (narrated, no Q&A)
  - Launch, splashdown, landing, docking, undocking coverage
  - Spacewalk / EVA footage — the actual EVA operations themselves (e.g. "Spacewalk_58_part4"). NOTE: A "Preview Briefing" or "Briefing" about a spacewalk is a PRESS CONFERENCE and should be KEPT, not treated as EVA footage.
  - Highlights packages or montages
  - B-roll collections (but NOT if the filename says News Conference, Interview, etc.)
  - Change of command ceremonies, arrival/welcoming remarks, change of shift
  - Purely ceremonial diplomatic or VIP calls with NO Q&A component (e.g. congratulatory calls or formal greetings where a head of state delivers a message and no questions are asked; NOT events where members of the public, students, or press also ask the astronaut questions)
  - Raw camera feeds, Earth views, flyovers
  - Animations, simulations
  - Training footage
  - Film magazine scans (Apollo, Gemini, etc.)
  - General "On-Orbit" content without a named event partner
  - Diary camera / GoPro footage
  - "Meet the astronaut" profile videos, "Science in Orbit" montages
  - Cargo unpacking, equipment stowage, logistics footage
  - Anything else without clear Q&A or interview structure in the filename

When in doubt, REJECT — it is much cheaper to miss a borderline file than to download and process thousands of irrelevant ones.

Respond in strict JSON with keys:
- decision: "keep" or "reject"
- confidence: number from 0.0 to 1.0
- reason: short string

filename: {filename}
title: {title}
description: {description}
subject: {subject}
"""

# Transcripts that have both a transcript file and a known QA baseline
QA_TEST_TRANSCRIPTS = [
    # Short (~11 segments) - fast test
    "jsc2017m000309_Students_Acting_on_a_HUNCH_MXF__jsc2017m000309_Students_Acting_on_a_HUNCH_MP4_lowres",
    # Medium (~30 segments)
    "jsc2019m000512_T_60_Seconds_with_Jessica_Meir__jsc2019m000512_T_60_Seconds_with_Jessica_Meir_MXF_1_lowres",
    # Longer (~98 segments) - richer comparison
    "20200908-0915-NASA-ISSExpedition63In-FlightInterviewwithFoxNewsRadio__Expedition_63_InFlight_FoxNewsRadio_Cassidy_200908_1374403_lowres",
]

# How many classification samples to test
CLASSIFY_SAMPLE_SIZE = 30

# Context window for QA extraction (same as pipeline defaults)
DEFAULT_WINDOW_PRE = 20.0
DEFAULT_WINDOW_POST = 90.0
DEFAULT_GROUP_GAP = 10.0


# ---------------------------------------------------------------------------
# LM Studio client
# ---------------------------------------------------------------------------

# Fraction of the output that must be a repeated chunk for it to count as
# a repetition loop.  E.g. 0.4 means the last 40 % of the text is a repeat.
_REPETITION_RATIO_THRESHOLD = 0.40
# Minimum repeated-chunk character length to bother checking
_REPETITION_MIN_CHUNK = 60


def _truncate_repetition(text: str) -> tuple[str, bool]:
    """Detect and remove trailing repetition loops in LLM output.

    Scans for the longest substring in the *first* half of `text` that
    appears verbatim later, and truncates at the point where the repeated
    section starts if the repeated portion exceeds the threshold.

    Returns (possibly_truncated_text, was_truncated).
    """
    if len(text) < _REPETITION_MIN_CHUNK * 2:
        return text, False

    half = len(text) // 2
    # Try chunks of decreasing size from the first half
    for chunk_len in range(min(half, 400), _REPETITION_MIN_CHUNK - 1, -20):
        chunk = text[:chunk_len]
        second_occurrence = text.find(chunk, chunk_len)
        if second_occurrence == -1:
            continue
        # How much of the tail is this repeated block?
        tail_len = len(text) - second_occurrence
        if tail_len / len(text) >= _REPETITION_RATIO_THRESHOLD:
            return text[:second_occurrence].rstrip(), True
        break  # Found one occurrence but tail is short — not a loop

    return text, False


def call_lmstudio(
    model: str,
    user_prompt: str,
    *,
    system: str = "",
    temperature: float = 0.1,
    max_tokens: int = 16384,
    timeout: int = 600,
) -> str:
    """Call LM Studio's OpenAI-compatible /v1/chat/completions endpoint.

    Handles thinking models (Qwen3 MTP etc.) where LM Studio separates
    chain-of-thought into ``reasoning_content`` and the final answer into
    ``content``.  When ``content`` is empty the model hasn't finished
    thinking yet (hit token limit); we fall back to extracting the portion
    after </think> in reasoning_content.

    max_tokens defaults to 16384 so thinking models have enough room to
    finish their chain-of-thought and still produce output.

    Repetition is handled by LM Studio's own repeat_penalty sampler setting
    (1.1 by default).  _truncate_repetition() is a post-processing safety
    net for anything that slips through at the text level.
    """
    messages: list[dict] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": user_prompt})

    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }
    resp = requests.post(LMSTUDIO_CHAT_URL, json=payload, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    choice = data["choices"][0]
    msg = choice["message"]
    finish_reason = choice.get("finish_reason", "")
    content = msg.get("content") or ""

    # Thinking models (Qwen3 MTP/etc.) separate reasoning into
    # reasoning_content; content holds only the final answer.
    # If content is empty the model ran out of tokens mid-think.
    if not content.strip():
        reasoning = msg.get("reasoning_content") or ""
        after_think = re.split(r"</think>", reasoning, maxsplit=1)
        if len(after_think) > 1:
            content = after_think[1].strip()
        elif reasoning:
            # Strip think tags if they happen to be inline
            content = re.sub(r"<think>.*?</think>", "", reasoning, flags=re.DOTALL).strip()

    # Strip any stray <think>...</think> blocks
    content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()

    # Detect and truncate repetition loops that slipped past frequency_penalty
    content, was_truncated = _truncate_repetition(content)
    if was_truncated:
        print(f"    ⚠ repetition loop detected and truncated "
              f"(finish={finish_reason}, tokens={data.get('usage',{}).get('completion_tokens','?')})")

    return content


def list_lmstudio_models() -> list[str]:
    """Return IDs of all models currently loaded in LM Studio."""
    resp = requests.get(LMSTUDIO_MODELS_URL, timeout=10)
    resp.raise_for_status()
    return [m["id"] for m in resp.json().get("data", [])]


# ---------------------------------------------------------------------------
# Stage 2: classification
# ---------------------------------------------------------------------------

_CLASSIFY_PROMPT_TEMPLATE = """\
You are classifying NASA video files to find interactive Q&A events worth transcribing.

CRITICAL: The **filename** is the most reliable indicator of what a video contains. \
The title, description, and subject fields often describe the parent *collection* \
(e.g. "Crew-11 Content", "Resource Reel") rather than the individual video. \
Always prioritize the filename over title/description/subject. If the filename \
clearly indicates a news conference, interview, or education event, KEEP it \
regardless of what the other fields say.

The downstream pipeline only processes these event types:
  1. student_qa — School downlinks, ARISS contacts, education inflight events where students ask an astronaut questions. Key signals in filename: "Education Inflight", "Inflight with [school/org]", "EDU_Inflight", "ARISS", "school", "student", "ham radio", any organization or media outlet name after "Inflight" (e.g. "Inflight_HCHSA", "Inflight_NOGGIN", "Inflight_CNBC").
  2. press_conference — News conferences, pre-launch/post-flight/post-mission press briefings, flight readiness reviews with Q&A. Key signals in filename: "News_Conference", "News Conference", "Press_Conference", "Postflight", "Post-Flight", "Post_Flight", "Pre-Launch", "Flight_Readiness", "Mission_Overview_News".
  3. media_interview — An astronaut discussing life in space with a specific TV station, newspaper, or radio outlet. Key signals in filename: "Discusses_Life_In_Space", "Talks_with", "Discuss", name of a TV/radio station (e.g. WTKR-TV, NPR, CNBC, KHQ-TV).
  4. panel — Panel discussions or roundtables with multiple speakers.

KEEP files whose **filename** clearly matches one of the four types above.

REJECT everything else, including:
  - Space to Ground weekly recap segments (narrated, no Q&A)
  - Launch, splashdown, landing, docking, undocking coverage
  - Spacewalk / EVA coverage
  - Highlights packages or montages
  - B-roll collections (but NOT if the filename says News Conference, Interview, etc.)
  - Change of command ceremonies, welcome events, arrival events
  - Raw camera feeds, Earth views, flyovers
  - Animations, simulations
  - Training footage
  - Film magazine scans (Apollo, Gemini, etc.)
  - General "On-Orbit" content without a named event partner
  - Diary camera / GoPro footage
  - "Meet the astronaut" profile videos, "Science in Orbit" montages
  - Anything else without clear Q&A or interview structure in the filename

When in doubt, REJECT — it is much cheaper to miss a borderline file than to download and process thousands of irrelevant ones.

Respond in strict JSON with keys:
- decision: "keep" or "reject"
- confidence: number from 0.0 to 1.0
- reason: short string

filename: {filename}
title: {title}
description: {description}
subject: {subject}
"""


def _extract_json_decision(text: str) -> dict | None:
    """Extract JSON decision object from LLM response text."""
    text = text.strip()
    # Strip markdown fences
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    text = text.strip()

    if text.startswith("{") and text.endswith("}"):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

    match = re.search(r"\{.*?\}", text, flags=re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    return None


def classify_with_lmstudio(
    model: str,
    filename: str,
    title: str,
    description: str,
    subject: str,
    *,
    prompt_template: str = _CLASSIFY_PROMPT_TEMPLATE,
) -> tuple[str, float, str, float]:
    """Run one classification via LM Studio.

    Returns (decision, confidence, reason, elapsed_seconds).
    """
    prompt = prompt_template.format(
        filename=filename, title=title, description=description, subject=subject
    )
    t0 = time.time()
    raw = call_lmstudio(model, prompt, temperature=0.1)
    elapsed = time.time() - t0

    parsed = _extract_json_decision(raw)
    if not parsed:
        decision = "reject" if "reject" in raw.lower() else "keep"
        return decision, 0.5, "fallback_parse", elapsed

    decision = str(parsed.get("decision", "reject")).strip().lower()
    if decision not in {"keep", "reject"}:
        decision = "reject"
    try:
        confidence = max(0.0, min(1.0, float(parsed.get("confidence", 0.5))))
    except (TypeError, ValueError):
        confidence = 0.5
    reason = str(parsed.get("reason", "")).strip() or "no_reason"
    return decision, confidence, reason, elapsed


def build_classify_sample() -> list[dict]:
    """Load a diverse sample from the baseline classified_candidates.jsonl.

    Selects up to CLASSIFY_SAMPLE_SIZE records with a mix of keep/reject
    decisions that were processed by gemma3:12b.  Uses every 5th record to
    get variety across the full dataset.
    """
    all_records = load_jsonl(CLASSIFIED_JSONL)
    # Filter to gemma3:12b records only (the baseline)
    baseline = [r for r in all_records if r.get("model") == "gemma3:12b"]

    # Separate keep/reject to guarantee both classes
    keeps = [r for r in baseline if r.get("decision") == "keep"]
    rejects = [r for r in baseline if r.get("decision") == "reject"]

    # Take evenly spaced samples from each class
    def _sample(lst: list, n: int) -> list:
        if len(lst) <= n:
            return lst
        step = len(lst) / n
        return [lst[int(i * step)] for i in range(n)]

    n_keep = min(CLASSIFY_SAMPLE_SIZE // 2, len(keeps))
    n_reject = min(CLASSIFY_SAMPLE_SIZE - n_keep, len(rejects))

    sample = _sample(keeps, n_keep) + _sample(rejects, n_reject)
    print(f"  Classification sample: {len(sample)} records "
          f"({n_keep} keep, {n_reject} reject) from {len(baseline)} gemma3 baseline")
    return sample


def run_classify_test(
    model: str,
    sample: list[dict],
    run_num: int,
    *,
    prompt_template: str = _CLASSIFY_PROMPT_TEMPLATE,
    prompt_label: str = "original",
    workers: int = 1,
) -> dict:
    """Run classification test for all sample records.

    Scores against both the gemma3:12b baseline and the GROUND_TRUTH dict.
    Returns a result dict with per-record decisions and aggregate metrics.
    """
    print(f"\n  [Run {run_num}] Stage 2 classification — {len(sample)} records  "
          f"[prompt={prompt_label}]  [workers={workers}]")
    agreement_count = 0
    gt_correct_count = 0
    total_elapsed = 0.0
    print_lock = threading.Lock()
    results_by_idx: dict[int, dict] = {}

    def _classify_one(args: tuple[int, dict]) -> None:
        i, rec = args
        filename = rec.get("filename", "")
        title = rec.get("title", "")
        baseline_decision = rec.get("decision", "")
        gt_decision = GROUND_TRUTH.get(filename)

        decision, confidence, reason, elapsed = classify_with_lmstudio(
            model=model,
            filename=filename,
            title=title,
            description="",
            subject="",
            prompt_template=prompt_template,
        )
        agrees = decision == baseline_decision
        gt_correct = (decision == gt_decision) if gt_decision is not None else None
        b_mark = "✓" if agrees else "✗"
        g_mark = ("✓" if gt_correct else "✗") if gt_decision is not None else "?"
        note = GT_DISAGREEMENT_NOTES.get(filename, "")
        flag = "  ← " + note[:60] if note else ""
        with print_lock:
            print(f"    [{i:2d}/{len(sample)}] b{b_mark}g{g_mark} {decision:6s} "
                  f"(base={baseline_decision:6s} gt={gt_decision or '?':6s}) "
                  f"{elapsed:.1f}s  {filename[:50]}{flag}")
            results_by_idx[i] = {
                "filename": filename,
                "title": title,
                "baseline_decision": baseline_decision,
                "baseline_confidence": rec.get("confidence"),
                "gt_decision": gt_decision,
                "new_decision": decision,
                "new_confidence": confidence,
                "new_reason": reason,
                "agrees_baseline": agrees,
                "agrees_gt": gt_correct,
                "elapsed": round(elapsed, 2),
            }

    with ThreadPoolExecutor(max_workers=workers) as executor:
        list(executor.map(_classify_one, enumerate(sample, 1)))

    results = [results_by_idx[i] for i in sorted(results_by_idx)]
    for r in results:
        if r["agrees_baseline"]:
            agreement_count += 1
        if r["agrees_gt"]:
            gt_correct_count += 1
        total_elapsed += r["elapsed"]

    n = len(sample)
    n_gt = sum(1 for r in results if r["gt_decision"] is not None)
    agreement_rate = agreement_count / n if n else 0.0
    gt_accuracy = gt_correct_count / n_gt if n_gt else 0.0
    print(f"  → vs gemma3: {agreement_count}/{n} = {agreement_rate:.1%}  "
          f"| vs GT: {gt_correct_count}/{n_gt} = {gt_accuracy:.1%}  "
          f"avg={total_elapsed/n:.1f}s/call")

    return {
        "run": run_num,
        "model": model,
        "prompt_label": prompt_label,
        "stage": "classify",
        "n": n,
        "n_gt": n_gt,
        "agreement_count": agreement_count,
        "agreement_rate": round(agreement_rate, 4),
        "gt_correct_count": gt_correct_count,
        "gt_accuracy": round(gt_accuracy, 4),
        "total_elapsed": round(total_elapsed, 2),
        "avg_elapsed": round(total_elapsed / n, 2) if n else 0,
        "records": results,
    }


# ---------------------------------------------------------------------------
# Stage 5b: Q&A extraction
# ---------------------------------------------------------------------------

_CONFIRM_SYSTEM = """\
You are analysing a short excerpt from a NASA video transcript.

A candidate segment is marked with >>> ... <<< delimiters.

Your task: determine whether that candidate is a GENUINE QUESTION that receives
a SUBSTANTIVE ANSWER from a DIFFERENT speaker in the surrounding text.

GENUINE QUESTION criteria (ALL must be true):
1. The candidate segment contains an interrogative sentence, or a clear prompt for
   information / opinion directed at another person.
2. A DIFFERENT speaker responds with ≥2 sentences of substantive content (not just
   "thank you" or "sure" or "go ahead").
3. This is not a readiness/tech check ("Can you hear me?", "Are you ready?"),
   greeting, sign-off, moderator hand-off, or Mission Control protocol phrase.
4. The exchange is not primarily about divisive political or social controversy
   (abortion, partisan elections, religious disputes, etc.). Questions about the
   astronaut's personal life, hobbies, family, feelings, or any other non-space
   topic ARE acceptable as long as they meet criteria 1-3.

When determining question_start, include any lead-up sentence(s) immediately
before the interrogative that provide context or set up the question — typically
1-2 sentences. For example, if the interviewer says "You've been up there for six
months. What's the hardest part?" the question_start should begin at "You've been
up there..." not at "What's the hardest part?". Only include lead-up if it is
clearly part of the same turn and directly relates to the question being asked.

If all criteria are met, output ONE pipe-delimited line:
  question_start|question_end|answer_start|answer_end

If multiple speakers give sequential answers to the SAME question:
  question_start|question_end|a1_start|a1_end|a2_start|a2_end

If criteria are NOT met, output exactly:
  NONE

ALL values must be decimal numbers (seconds from start of video).
question_start / question_end span the full question utterance.
answer_start / answer_end span only the answerer's response.
No other text. No commentary. No markdown fences.
"""

_RETRY_REMINDER = (
    "\n\nYOUR PREVIOUS RESPONSE COULD NOT BE PARSED. "
    "Output ONLY a pipe-delimited line like: 899.7|927.7|928.8|982.4\n"
    "or the word NONE. No other text.\n"
)

# Interrogative pattern (duplicated from 5b for standalone use)
_INTERROGATIVE_STARTS = re.compile(
    r"^\s*(what|who|when|where|how|why|which|whose|whom"
    r"|can\s+\w+|could\s+\w+|will\s+\w+|would\s+\w+|should\s+\w+|might\s+\w+"
    r"|do\s+\w+|did\s+\w+|does\s+\w+"
    r"|have\s+\w+|has\s+\w+"
    r"|is\s+\w+|are\s+\w+|was\s+\w+|were\s+\w+"
    r"|tell\s+(?:us|me)\b|talk\s+(?:us|me)\s+through|describe\s+\w+"
    r"|walk\s+(?:us|me)\s+through|share\s+(?:what|how|why|with)\b"
    r"|i(?:\s*'m|\s+am|\s+was)\s+(?:curious|wondering)\b"
    r"|i\s+(?:was\s+wondering|would\s+(?:like|love)\s+to|have\s+a\s+question|wanted\s+to\s+(?:ask|know))\b"
    r"|my\s+(?:question|name)\b"
    r"|any\b|since\b"
    r"|now\s*,?\s*(?:what|how|why|when|where|who|will|would|can|could|are|is|were|was|do|does|did|for|tell)\b"
    r"|so\s*,?\s*(?:what|how|why|when|where|who|tell|can|could|will|would|should|do|does|did|is|are|was|were|have|has)\b"
    r"|but\s+(?:what|how|why|when|where|who|can|could|will|would|do|does|did|is|are|was|were)\b"
    r"|for\s+(?:all|the|each|every|those|you|us|any)\b"
    r"|this\s+(?:question|one)\b"
    r"|if\s+you\b|anything\b"
    r"|we\s+(?:have|had)\s+a\b"
    r")\b",
    re.IGNORECASE,
)

_SALUTATION_PREFIX = re.compile(
    r"^\s*(?:[A-Z][a-zA-Z\-]+(?:\s+[A-Z][a-zA-Z\-]+){0,2},\s*){1,3}",
)


def _find_candidates(segments: list[dict]) -> list[dict]:
    results = []
    for seg in segments:
        text = seg.get("text", "").strip()
        if not text:
            continue
        if "?" in text:
            results.append(seg)
            continue
        text_for_match = _SALUTATION_PREFIX.sub("", text).strip()
        if _INTERROGATIVE_STARTS.match(text) or _INTERROGATIVE_STARTS.match(text_for_match):
            results.append(seg)
    return results


def _group_candidates(
    candidates: list[dict],
    gap_threshold: float = DEFAULT_GROUP_GAP,
) -> list[list[dict]]:
    if not candidates:
        return []
    groups: list[list[dict]] = [[candidates[0]]]
    for cand in candidates[1:]:
        if cand["start"] - groups[-1][-1]["end"] <= gap_threshold:
            groups[-1].append(cand)
        else:
            groups.append([cand])
    return groups


def _build_confirm_prompt(
    group: list[dict],
    all_segments: list[dict],
    *,
    window_pre: float = DEFAULT_WINDOW_PRE,
    window_post: float = DEFAULT_WINDOW_POST,
) -> str:
    g_start = group[0]["start"] - window_pre
    g_end = group[-1]["end"] + window_post
    ctx_segs = [s for s in all_segments if s["end"] >= g_start and s["start"] < g_end]

    candidate_set = {(s["start"], s["end"]) for s in group}
    lines = []
    for seg in ctx_segs:
        key = (seg["start"], seg["end"])
        text = seg.get("text", "").strip()
        ts = f"[{seg['start']:.1f}]"
        sp = seg.get("speaker", "")
        prefix = f"{sp}: " if sp else ""
        if key in candidate_set:
            lines.append(f"{ts} {prefix}>>> {text} <<<")
        else:
            lines.append(f"{ts} {prefix}{text}")

    transcript_block = "\n".join(lines)
    g_anchor_start = group[0]["start"]
    g_anchor_end = group[-1]["end"]

    return (
        f"Transcript excerpt ({g_start:.0f}s – {g_end:.0f}s):\n\n"
        f"{transcript_block}\n\n"
        f"Candidate segment(s) are at {g_anchor_start:.1f}s – {g_anchor_end:.1f}s "
        f"(marked with >>> <<<)."
    )


def confirm_with_lmstudio(
    model: str,
    group: list[dict],
    all_segments: list[dict],
) -> tuple[list[dict], float, str]:
    """Run one LLM confirmation call via LM Studio.

    Returns (valid_pairs, elapsed_seconds, raw_response).
    """
    prompt = _build_confirm_prompt(group, all_segments)
    t0 = time.time()
    raw = call_lmstudio(model, prompt, system=_CONFIRM_SYSTEM, temperature=0.1)
    elapsed = time.time() - t0

    parsed = parse_pipe_qa(raw)
    valid, _ = _validate_qa_pairs(parsed)

    if not valid and raw.strip() and raw.strip().upper() != "NONE":
        retry_prompt = prompt + _RETRY_REMINDER
        t0r = time.time()
        raw2 = call_lmstudio(model, retry_prompt, system=_CONFIRM_SYSTEM, temperature=0.1)
        elapsed += time.time() - t0r
        parsed2 = parse_pipe_qa(raw2)
        valid, _ = _validate_qa_pairs(parsed2)
        raw = raw2

    return valid, elapsed, raw.strip()


def load_baseline_qa(stem: str) -> dict | None:
    """Load the gemma3:12b QA baseline for a transcript stem."""
    qa_path = QA_DIR / f"{stem}.qa.json"
    if not qa_path.exists():
        return None
    return json.loads(qa_path.read_text(encoding="utf-8"))


def run_qa_test(
    model: str,
    transcript_stem: str,
    run_num: int,
    *,
    workers: int = 1,
) -> dict:
    """Run QA extraction for one transcript via LM Studio.

    Returns a result dict with extraction metrics and pair comparison.
    """
    transcript_path = TRANSCRIPTS_DIR / f"{transcript_stem}.json"
    if not transcript_path.exists():
        print(f"  ⚠ Transcript not found: {transcript_path.name}")
        return {"error": "transcript_not_found", "stem": transcript_stem}

    transcript_data = load_transcript(transcript_path)
    segments = transcript_data["segments"]
    baseline = load_baseline_qa(transcript_stem)
    baseline_count = len(baseline["qa_pairs"]) if baseline else None

    print(f"\n  [Run {run_num}] Stage 5b QA extraction — {transcript_stem[:60]}")
    print(f"  Segments: {len(segments)}  |  Baseline (gemma3): "
          f"{baseline_count if baseline_count is not None else 'N/A'} pairs")

    # Pass 1: heuristic candidates
    candidates = _find_candidates(segments)
    groups = _group_candidates(candidates)
    print(f"  Pass 1: {len(candidates)} candidates → {len(groups)} groups")

    if not groups:
        print("  Pass 2: skipped (no candidates)")
        return {
            "run": run_num,
            "model": model,
            "stage": "qa",
            "stem": transcript_stem,
            "n_segments": len(segments),
            "pass1_candidates": 0,
            "pass1_groups": 0,
            "pass2_confirmed": 0,
            "qa_pairs": [],
            "baseline_count": baseline_count,
            "total_elapsed": 0.0,
        }

    # Pass 2: LLM confirmation
    all_pairs: list[dict] = []
    total_elapsed = 0.0
    confirmed = 0
    per_group_results = []
    print_lock = threading.Lock()
    group_results: dict[int, tuple] = {}

    def _confirm_one(gi_group: tuple[int, list[dict]]) -> None:
        gi, group = gi_group
        valid_pairs, elapsed, raw = confirm_with_lmstudio(model, group, segments)
        anchor_start = group[0]["start"]
        status = f"{len(valid_pairs)} pair(s)" if valid_pairs else "NONE"
        with print_lock:
            print(f"    Group {gi:2d}/{len(groups)}  @{anchor_start:.1f}s  → {status}  ({elapsed:.1f}s)")
            group_results[gi] = (valid_pairs, elapsed, raw, anchor_start, group[-1]["end"])

    with ThreadPoolExecutor(max_workers=workers) as executor:
        list(executor.map(_confirm_one, enumerate(groups, 1)))

    for gi in sorted(group_results):
        valid_pairs, elapsed, raw, anchor_start, anchor_end = group_results[gi]
        total_elapsed += elapsed
        if valid_pairs:
            confirmed += 1
            all_pairs.extend(valid_pairs)
        per_group_results.append({
            "group_idx": gi,
            "anchor_start": anchor_start,
            "anchor_end": anchor_end,
            "raw_response": raw,
            "pairs_found": len(valid_pairs),
        })

    print(f"  → {confirmed}/{len(groups)} groups confirmed, {len(all_pairs)} pairs found  "
          f"(baseline={baseline_count})  total={total_elapsed:.1f}s")

    return {
        "run": run_num,
        "model": model,
        "stage": "qa",
        "stem": transcript_stem,
        "n_segments": len(segments),
        "pass1_candidates": len(candidates),
        "pass1_groups": len(groups),
        "pass2_confirmed": confirmed,
        "qa_pairs": all_pairs,
        "n_pairs_found": len(all_pairs),
        "baseline_count": baseline_count,
        "baseline_pairs": baseline.get("qa_pairs") if baseline else None,
        "total_elapsed": round(total_elapsed, 2),
        "avg_per_group": round(total_elapsed / len(groups), 2) if groups else 0,
        "per_group": per_group_results,
    }


# ---------------------------------------------------------------------------
# Summary / reporting
# ---------------------------------------------------------------------------

def print_summary(all_results: dict) -> None:
    """Print a concise comparison summary across all runs."""
    model = all_results["model"]
    runs = all_results["runs"]

    print("\n" + "=" * 70)
    print(f"SUMMARY — {model}")
    print("=" * 70)

    # Classification summary
    classify_runs = [r for r in runs if r.get("stage") == "classify"]
    if classify_runs:
        # Group by prompt_label
        labels = sorted({r.get("prompt_label", "original") for r in classify_runs})
        for label in labels:
            label_runs = [r for r in classify_runs if r.get("prompt_label", "original") == label]
            rates = [r["agreement_rate"] for r in label_runs]
            gt_accs = [r["gt_accuracy"] for r in label_runs]
            avg_rate = sum(rates) / len(rates)
            avg_gt = sum(gt_accs) / len(gt_accs)
            avg_latency = sum(r["avg_elapsed"] for r in label_runs) / len(label_runs)
            print(f"\nStage 2 — Classification  [prompt={label}]  ({len(label_runs)} run(s))")
            print(f"  vs gemma3:12b baseline: {avg_rate:.1%}  "
                  f"(min={min(rates):.1%}, max={max(rates):.1%})")
            print(f"  vs Ground Truth (GT):   {avg_gt:.1%}  "
                  f"(min={min(gt_accs):.1%}, max={max(gt_accs):.1%})")
            print(f"  Avg latency per call:   {avg_latency:.1f}s")
            for r in label_runs:
                print(f"  Run {r['run']}: gemma3={r['agreement_rate']:.1%}  "
                      f"GT={r['gt_accuracy']:.1%}  {r['avg_elapsed']:.1f}s/call")

    # QA extraction summary
    qa_runs = [r for r in runs if r.get("stage") == "qa"]
    if qa_runs:
        print(f"\nStage 5b — Q&A Extraction")
        # Group by transcript stem
        stems = sorted({r["stem"] for r in qa_runs if "stem" in r})
        for stem in stems:
            stem_runs = [r for r in qa_runs if r.get("stem") == stem]
            baseline_count = stem_runs[0].get("baseline_count", "?")
            pair_counts = [r.get("n_pairs_found", 0) for r in stem_runs]
            avg_pairs = sum(pair_counts) / len(pair_counts) if pair_counts else 0
            avg_latency = sum(r.get("total_elapsed", 0) for r in stem_runs) / len(stem_runs)
            print(f"\n  {stem[:60]}")
            print(f"    Baseline (gemma3):  {baseline_count} pairs")
            print(f"    New model ({len(stem_runs)} runs): avg={avg_pairs:.1f} pairs  "
                  f"[{', '.join(str(c) for c in pair_counts)}]")
            print(f"    Avg total time:    {avg_latency:.1f}s")
            # Consistency check
            if len(set(pair_counts)) == 1:
                print(f"    Consistency:       ✓ Identical pair count across all runs")
            else:
                print(f"    Consistency:       ⚠ Varying results across runs")

    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    # Ensure UTF-8 output on Windows (CP1252 can't encode box-drawing chars)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        description="Compare LM Studio models against gemma3:12b pipeline baseline"
    )
    parser.add_argument(
        "--model",
        default=None,
        help="LM Studio model ID to test (default: auto-detect first loaded model)",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=3,
        help="Number of test runs per stage (default: 3)",
    )
    parser.add_argument(
        "--stage",
        choices=["classify", "qa", "all"],
        default="all",
        help="Which pipeline stage(s) to test (default: all)",
    )
    parser.add_argument(
        "--list-models",
        action="store_true",
        help="List available LM Studio models and exit",
    )
    parser.add_argument(
        "--transcript",
        action="append",
        dest="transcripts",
        help="Specific transcript stem to test (can repeat; default: 3 built-in samples)",
    )
    parser.add_argument(
        "--improved-prompt",
        action="store_true",
        help="Also run classification with the improved prompt variant and compare",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Parallel LM Studio requests per stage (default: 4)",
    )
    parser.add_argument(
        "--base-url",
        default="http://localhost:1234",
        help="API base URL (default: LM Studio at :1234; use http://localhost:11434 for Ollama)",
    )
    args = parser.parse_args()

    # Apply base URL (supports swapping between LM Studio and Ollama)
    global LMSTUDIO_BASE_URL, LMSTUDIO_CHAT_URL, LMSTUDIO_MODELS_URL
    LMSTUDIO_BASE_URL = args.base_url.rstrip("/")
    LMSTUDIO_CHAT_URL = f"{LMSTUDIO_BASE_URL}/v1/chat/completions"
    LMSTUDIO_MODELS_URL = f"{LMSTUDIO_BASE_URL}/v1/models"

    # --list-models
    if args.list_models:
        try:
            models = list_lmstudio_models()
            print("Available LM Studio models:")
            for m in models:
                print(f"  {m}")
        except Exception as exc:
            print(f"Error connecting to LM Studio: {exc}")
        return

    # Resolve model
    if args.model is None:
        try:
            models = list_lmstudio_models()
            # Prefer non-embedding models
            chat_models = [m for m in models if "embed" not in m.lower()]
            if not chat_models:
                print("No chat models loaded in LM Studio. Load a model and retry.")
                sys.exit(1)
            args.model = chat_models[0]
            print(f"Auto-selected model: {args.model}")
        except Exception as exc:
            print(f"Cannot connect to API server at {LMSTUDIO_BASE_URL}: {exc}")
            sys.exit(1)

    model = args.model
    print("=" * 70)
    print(f"LM Studio Model Comparison Test")
    print(f"Model:   {model}")
    print(f"Runs:    {args.runs}")
    print(f"Stages:  {args.stage}")
    print(f"Workers: {args.workers}")
    if args.improved_prompt:
        print(f"Prompts: original + improved")
    print(f"Date:    {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print("=" * 70)

    transcripts = args.transcripts or QA_TEST_TRANSCRIPTS
    all_run_results: list[dict] = []

    # ----------------------------------------------------------------
    # Stage 2: Classification
    # ----------------------------------------------------------------
    if args.stage in ("classify", "all"):
        print("\n── Stage 2: Filename Classification ──")
        sample = build_classify_sample()

        # Original prompt
        for run_num in range(1, args.runs + 1):
            result = run_classify_test(model, sample, run_num,
                                       prompt_template=_CLASSIFY_PROMPT_TEMPLATE,
                                       prompt_label="original",
                                       workers=args.workers)
            all_run_results.append(result)

        # Improved prompt (optional)
        if args.improved_prompt:
            print("\n  ── Improved prompt ──")
            for run_num in range(1, args.runs + 1):
                result = run_classify_test(model, sample, run_num,
                                           prompt_template=_CLASSIFY_PROMPT_IMPROVED,
                                           prompt_label="improved",
                                           workers=args.workers)
                all_run_results.append(result)

    # ----------------------------------------------------------------
    # Stage 5b: QA Extraction
    # ----------------------------------------------------------------
    if args.stage in ("qa", "all"):
        print("\n── Stage 5b: Q&A Extraction ──")
        for run_num in range(1, args.runs + 1):
            for stem in transcripts:
                result = run_qa_test(model, stem, run_num, workers=args.workers)
                all_run_results.append(result)

    # ----------------------------------------------------------------
    # Collect & save
    # ----------------------------------------------------------------
    output = {
        "model": model,
        "runs_requested": args.runs,
        "stages_tested": args.stage,
        "improved_prompt_tested": args.improved_prompt,
        "test_transcripts": transcripts,
        "tested_at": datetime.now(timezone.utc).isoformat(),
        "ground_truth_size": len(GROUND_TRUTH),
        "runs": all_run_results,
    }

    print_summary(output)

    # Save results
    out_dir = ROOT / "data" / "model_comparison"
    out_dir.mkdir(parents=True, exist_ok=True)
    safe_model = re.sub(r"[^\w\-]", "_", model)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_path = out_dir / f"{safe_model}_{ts}.json"
    out_path.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Results saved: {out_path}")


if __name__ == "__main__":
    main()

