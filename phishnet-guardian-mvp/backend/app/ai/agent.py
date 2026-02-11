from __future__ import annotations

import os
import json
from datetime import datetime
from typing import Any, Dict, Optional, List


# -------------------------- Environment / Config --------------------------

def _require_key() -> str:
    """
    Fail fast if the key is missing. This keeps the pipeline Gemini-only
    and avoids any silent fallback.
    """
    key = (os.getenv("GEMINI_API_KEY") or "").strip()
    if not key:
        raise RuntimeError("GEMINI_API_KEY is not set in environment")
    return key


def _model_name() -> str:
    """
    Allow switching model via .env without code changes.
    Defaults to gemini-1.5-flash.
    """
    return (os.getenv("GEMINI_MODEL") or "gemini-1.5-flash").strip()


# -------------------------- Utilities --------------------------

def _safe_json_parse(raw: str) -> Dict[str, Any]:
    """
    Parse JSON from model output; if there is extra text, extract the first {...} block.
    Raises a ValueError with a helpful message if JSON cannot be parsed.
    """
    try:
        return json.loads(raw)
    except Exception:
        import re
        m = re.search(r"\{[\s\S]*\}", raw or "")
        if not m:
            raise ValueError("Model did not return JSON")
        return json.loads(m.group(0))


def _norm_lang(lang: Optional[str]) -> str:
    lang = (lang or "en").strip().lower()
    return lang if lang in {"en", "hi", "mr"} else "en"


def _stamp(d: Dict[str, Any]) -> Dict[str, Any]:
    d["created_at"] = d.get("created_at") or (datetime.utcnow().isoformat() + "Z")
    return d


# -------------------------- Gemini Calls --------------------------

def _call_gemini(text: str, preferred_language: Optional[str] = None) -> Dict[str, Any]:
    """
    Primary text analysis via Gemini (NO fallback).
    Enforces strict JSON and the requested output language.
    """
    import google.generativeai as genai

    genai.configure(api_key=_require_key())
    model = genai.GenerativeModel(_model_name())

    lang = _norm_lang(preferred_language)
    sys_prompt = (
        "You are PhishNet Guardian, an AI agent that detects phishing/scam messages and returns STRICT JSON only. "
        "Follow the reasoning pipeline: Intent -> Analysis -> Decision -> Action. "
        "Return ONLY JSON with keys: "
        "intent, classification (Safe|Suspicious|Scam), risk_level (Low|Medium|High|Critical), confidence (0-1), "
        "red_flags (list of strings), recommended_actions (list of strings), not_to_do (list of strings), "
        "plan (list of strings), micro_lesson (string), "
        "quiz (object with 'question','options','answer','explanation'), "
        "trace (list of step objects with {stage,notes}), created_at (ISO). "
        f"IMPORTANT: Respond STRICTLY in {lang}. Do not include any other language."
    )

    payload = {"text": text, "preferred_language": lang}
    parts = [sys_prompt, "\nInput:", json.dumps(payload, ensure_ascii=False)]

    try:
        resp = model.generate_content(parts)
    except Exception as e:
        # Bubble a readable message to FastAPI; the UI will show this in the toast
        raise RuntimeError(f"Gemini text call failed: {e}") from e

    try:
        data = _safe_json_parse(resp.text)
    except Exception as e:
        raw = (resp.text or "").strip()
        raise RuntimeError(f"Gemini returned non-JSON or blocked output. Raw head: {raw[:180]}") from e

    return _stamp(data)


def _call_gemini_vision(image_bytes: bytes, preferred_language: Optional[str] = None) -> Dict[str, Any]:
    """
    Screenshot analysis via Gemini (Vision). NO fallback.
    Returns strict JSON, stamps defaults.
    """
    import google.generativeai as genai

    genai.configure(api_key=_require_key())
    model = genai.GenerativeModel(_model_name())

    lang = _norm_lang(preferred_language)
    sys_prompt = (
        "You are PhishNet Guardian. Analyze the screenshot for phishing/scam signals. "
        "Extract key text if needed and return STRICT JSON with keys: "
        "intent, classification (Safe|Suspicious|Scam), risk_level (Low|Medium|High|Critical), confidence (0-1), "
        "red_flags (list), recommended_actions (list), not_to_do (list), plan (list), micro_lesson (string), "
        "quiz (object with 'question','options','answer','explanation'), trace (list of {stage,notes}), created_at. "
        f"IMPORTANT: Respond STRICTLY in {lang}. Do not include any other language."
    )

    parts = [
        sys_prompt,
        "Analyze this image and return STRICT JSON only.",
        {"mime_type": "image/png", "data": image_bytes},
    ]

    try:
        resp = model.generate_content(parts)
    except Exception as e:
        raise RuntimeError(f"Gemini vision call failed: {e}") from e

    try:
        data = _safe_json_parse(resp.text)
    except Exception as e:
        raw = (resp.text or "").strip()
        raise RuntimeError(f"Gemini returned non-JSON or blocked output (vision). Raw head: {raw[:180]}") from e

    data.setdefault("intent", "analyze_scam_image")
    return _stamp(data)


# -------------------------- Public API --------------------------

def analyze_text(text: str, preferred_language: Optional[str] = None) -> Dict[str, Any]:
    """
    Gemini-only TEXT flow (no heuristic fallback).
    Adds a small initial trace entry for UI consistency.
    """
    pre_trace: List[Dict[str, Any]] = [{"stage": "Intent", "notes": "Analyze potential scam text"}]

    result = _call_gemini(text, preferred_language)
    upstream = result.get("trace", [])
    result["trace"] = (pre_trace + upstream) if isinstance(upstream, list) else pre_trace
    return result


__all__ = [
    "analyze_text",
    "_call_gemini_vision",
]