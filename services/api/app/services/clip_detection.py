"""Smart clip detection.

Scores every transcript segment on several virality/retention signals, then
assembles candidate windows and picks the top non-overlapping clips:

- Hook detection ..... question openers, curiosity phrases, numbers,
                       superlatives (English + Hindi/Hinglish keyword banks)
- Energy ............. audio RMS loudness of the segment vs the video median
- Speech rate ........ words/second vs the video median (excitement proxy)
- Keyword importance . TF-based salience of rare-but-repeated content words
- Silence removal .... boundaries snapped away from silence; windows with a
                       high silence ratio are penalised
"""

from __future__ import annotations

import math
import re
import wave
from dataclasses import dataclass, field
from typing import Any

import numpy as np

# ---------------------------------------------------------------------------
# Keyword banks (English + Hindi + Hinglish)
# ---------------------------------------------------------------------------

HOOK_PATTERNS = [
    # English
    r"\bwhat if\b", r"\bdid you know\b", r"\bhere'?s (?:why|how|the)\b", r"\bthe secret\b",
    r"\bnobody (?:tells|talks about)\b", r"\byou won'?t believe\b", r"\bthe biggest mistake\b",
    r"\bstop doing\b", r"\bbefore you\b", r"\bthe truth (?:is|about)\b", r"\blisten\b",
    r"\bimagine\b", r"\blet me (?:tell|show)\b", r"\bthis is (?:how|why|the)\b",
    r"\bmost people\b", r"\bnever\b", r"\balways\b", r"\bfree\b", r"\bhack\b", r"\btrick\b",
    r"\bwarning\b", r"\bmind[- ]?blowing\b", r"\binsane\b", r"\bcrazy\b", r"\bshocking\b",
    # Hindi (Devanagari)
    r"क्या आप जानते", r"सबसे बड़ी गलती", r"राज़", r"सच्चाई", r"कभी मत", r"सुनो", r"ध्यान से",
    r"सोचिए", r"मान लीजिए", r"सबसे", r"चौंकाने", r"कमाल", r"जरूर", r"ज़रूर", r"मुफ़्त", r"मुफ्त",
    # Hinglish / romanised Hindi
    r"\bkya aap\b", r"\bsabse badi galti\b", r"\bsach(?:chai)?\b", r"\bsuno\b", r"\bdhyan se\b",
    r"\bsochiye\b", r"\bkamaal\b", r"\bzaroor\b", r"\bpaisa\b", r"\bmagic\b",
]

QUESTION_WORDS = [
    "what", "why", "how", "when", "who", "which", "kya", "kyun", "kaise", "kab", "kaun",
    "क्या", "क्यों", "कैसे", "कब", "कौन",
]

EMPHASIS_WORDS = [
    "important", "amazing", "incredible", "guaranteed", "proven", "best", "worst",
    "million", "billion", "lakh", "crore", "money", "growth", "viral",
    "जरूरी", "ज़रूरी", "महत्वपूर्ण", "शानदार", "गारंटी", "लाख", "करोड़", "पैसा", "पैसे",
]

STOPWORDS = set(
    """a an the and or but of to in on for with is are was were be been am do does did i you he she it we
they this that these those as at by from not no yes so if then than too very can could will would should
have has had my your his her its our their me him them what which who when where why how ka ki ke ko se
me par hai hain tha the ho na aur ya to bhi kya ye woh है हैं था थे हो ना और या तो भी क्या ये वह का की के को से में पर""".split()
)

_HOOK_RE = [re.compile(p, re.IGNORECASE) for p in HOOK_PATTERNS]
_NUM_RE = re.compile(r"\b\d[\d,.]*\b|[०-९]+")


@dataclass
class ClipCandidate:
    start: float
    end: float
    score: float
    breakdown: dict[str, float] = field(default_factory=dict)
    text: str = ""
    hook_text: str = ""
    title: str = ""

    @property
    def duration(self) -> float:
        return self.end - self.start


# ---------------------------------------------------------------------------
# Audio energy
# ---------------------------------------------------------------------------

def _load_rms_curve(audio_path: str, hop_s: float = 0.5) -> tuple[np.ndarray, float]:
    """Return (rms per hop window, hop seconds) from a 16-bit mono WAV."""
    with wave.open(audio_path, "rb") as wf:
        sr = wf.getframerate()
        n = wf.getnframes()
        raw = wf.readframes(n)
    samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    hop = max(1, int(sr * hop_s))
    n_windows = max(1, len(samples) // hop)
    trimmed = samples[: n_windows * hop].reshape(n_windows, hop)
    rms = np.sqrt(np.mean(trimmed**2, axis=1) + 1e-9)
    return rms, hop_s


def _window_energy(rms: np.ndarray, hop_s: float, start: float, end: float) -> float:
    i0 = max(0, int(start / hop_s))
    i1 = min(len(rms), max(i0 + 1, int(math.ceil(end / hop_s))))
    return float(np.mean(rms[i0:i1])) if i1 > i0 else 0.0


# ---------------------------------------------------------------------------
# Text feature scoring
# ---------------------------------------------------------------------------

def _tokenize(text: str) -> list[str]:
    return [t for t in re.findall(r"[\w\u0900-\u097F']+", text.lower()) if t not in STOPWORDS and len(t) > 2]


def _hook_score(text: str) -> float:
    t = text.lower()
    score = 0.0
    for rx in _HOOK_RE:
        if rx.search(t):
            score += 1.0
    first_word = (t.split() or [""])[0].strip("?,.!")
    if first_word in QUESTION_WORDS or "?" in text:
        score += 0.8
    if _NUM_RE.search(text):
        score += 0.4
    for w in EMPHASIS_WORDS:
        if w in t:
            score += 0.3
    return min(score, 3.0) / 3.0  # normalise to 0..1


def _keyword_weights(segments: list[dict[str, Any]]) -> dict[str, float]:
    """TF-based salience: words repeated across the video but not stopwords."""
    counts: dict[str, int] = {}
    for seg in segments:
        for tok in set(_tokenize(seg["text"])):
            counts[tok] = counts.get(tok, 0) + 1
    if not counts:
        return {}
    max_c = max(counts.values())
    return {w: c / max_c for w, c in counts.items() if c >= 2}


def _keyword_score(text: str, weights: dict[str, float]) -> float:
    toks = _tokenize(text)
    if not toks:
        return 0.0
    return min(1.0, sum(weights.get(t, 0.0) for t in toks) / max(4, len(toks)) * 3.0)


# ---------------------------------------------------------------------------
# Main detection
# ---------------------------------------------------------------------------

def detect_clips(
    segments: list[dict[str, Any]],
    audio_path: str,
    silences: list[tuple[float, float]],
    num_clips: int = 5,
    min_duration: float = 15.0,
    max_duration: float = 60.0,
    remove_silence: bool = True,
) -> list[ClipCandidate]:
    if not segments:
        return []

    try:
        rms, hop_s = _load_rms_curve(audio_path)
        median_energy = float(np.median(rms[rms > 0.005])) if np.any(rms > 0.005) else 1e-3
    except Exception:
        rms, hop_s, median_energy = np.zeros(1), 0.5, 1e-3

    kw_weights = _keyword_weights(segments)

    # Per-segment speech rate baseline
    rates = []
    for seg in segments:
        dur = max(0.3, seg["end"] - seg["start"])
        rates.append(len(seg["text"].split()) / dur)
    median_rate = float(np.median(rates)) if rates else 2.0

    seg_scores: list[dict[str, float]] = []
    for seg, rate in zip(segments, rates):
        energy = _window_energy(rms, hop_s, seg["start"], seg["end"])
        seg_scores.append(
            {
                "hook": _hook_score(seg["text"]),
                "energy": min(1.5, energy / (median_energy + 1e-9)) / 1.5,
                "rate": min(1.5, rate / (median_rate + 1e-9)) / 1.5,
                "keywords": _keyword_score(seg["text"], kw_weights),
            }
        )

    def silence_overlap(start: float, end: float) -> float:
        total = 0.0
        for s, e in silences:
            total += max(0.0, min(end, e) - max(start, s))
        return total / max(0.1, end - start)

    # Build candidate windows: start at each segment, greedily extend.
    candidates: list[ClipCandidate] = []
    n = len(segments)
    for i in range(n):
        w_start = segments[i]["start"]
        j = i
        while j < n and segments[j]["end"] - w_start <= max_duration:
            w_end = segments[j]["end"]
            length = w_end - w_start
            ends_sentence = segments[j]["text"].rstrip().endswith((".", "?", "!", "।", "|"))
            if length >= min_duration and (ends_sentence or j == n - 1 or length >= 0.8 * max_duration):
                window = seg_scores[i : j + 1]
                mean = {k: float(np.mean([s[k] for s in window])) for k in ("hook", "energy", "rate", "keywords")}
                opening_hook = seg_scores[i]["hook"]
                sil = silence_overlap(w_start, w_end)
                completeness = 0.15 if ends_sentence else 0.0
                # Sweet-spot duration bonus: 20–45s performs best for shorts.
                dur_bonus = 0.1 if 20.0 <= length <= 45.0 else 0.0

                score = (
                    0.30 * opening_hook
                    + 0.15 * mean["hook"]
                    + 0.20 * mean["energy"]
                    + 0.10 * mean["rate"]
                    + 0.15 * mean["keywords"]
                    + completeness
                    + dur_bonus
                    - (0.35 * sil if remove_silence else 0.0)
                )
                text = " ".join(s["text"] for s in segments[i : j + 1]).strip()
                candidates.append(
                    ClipCandidate(
                        start=w_start,
                        end=w_end,
                        score=round(max(0.0, score) * 100, 1),
                        breakdown={
                            "hook": round(opening_hook, 3),
                            "energy": round(mean["energy"], 3),
                            "speech_rate": round(mean["rate"], 3),
                            "keywords": round(mean["keywords"], 3),
                            "silence_ratio": round(sil, 3),
                            "sentence_complete": 1.0 if ends_sentence else 0.0,
                        },
                        text=text,
                        hook_text=segments[i]["text"].strip(),
                    )
                )
            j += 1

    if not candidates:
        # Video shorter than min_duration or no sentence boundaries — one clip.
        start, end = segments[0]["start"], segments[-1]["end"]
        candidates = [
            ClipCandidate(start=start, end=min(end, start + max_duration), score=50.0,
                          text=" ".join(s["text"] for s in segments),
                          hook_text=segments[0]["text"])
        ]

    # Rank and pick non-overlapping winners.
    candidates.sort(key=lambda c: c.score, reverse=True)
    picked: list[ClipCandidate] = []
    for cand in candidates:
        if len(picked) >= num_clips:
            break
        if all(cand.end <= p.start + 1.0 or cand.start >= p.end - 1.0 for p in picked):
            picked.append(cand)

    # Snap boundaries away from silence and add tiny lead-in/out padding.
    for clip in picked:
        if remove_silence:
            for s, e in silences:
                if s <= clip.start < e:
                    clip.start = min(e, clip.end - 3.0)
                if s < clip.end <= e:
                    clip.end = max(s, clip.start + 3.0)
        clip.start = max(0.0, clip.start - 0.15)
        clip.end = clip.end + 0.25
        clip.title = _make_title(clip.hook_text or clip.text)

    picked.sort(key=lambda c: c.start)
    return picked


def _make_title(text: str, max_len: int = 60) -> str:
    text = re.sub(r"\s+", " ", text).strip().strip('"')
    if len(text) <= max_len:
        return text
    cut = text[:max_len]
    if " " in cut:
        cut = cut[: cut.rfind(" ")]
    return cut + "…"
