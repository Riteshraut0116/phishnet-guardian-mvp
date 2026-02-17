from __future__ import annotations

import os
import json
from datetime import datetime
from typing import Any, Dict, Optional, List


# -------------------------- Environment / Config --------------------------

def _require_key() -> str:
    key = (os.getenv("GEMINI_API_KEY") or "").strip()
    if not key:
        raise RuntimeError("GEMINI_API_KEY is not set in environment")
    return key


def _model_name() -> str:
    return (os.getenv("GEMINI_MODEL") or "gemini-1.5-flash").strip()


# -------------------------- Utilities --------------------------

def _safe_json_parse(raw: str) -> Dict[str, Any]:
    try:
        return json.loads(raw)
    except Exception:
        import re
        m = re.search(r"\{[\s\S]*\}", raw or "")
        if not m:
            raise ValueError("Model did not return JSON")
        return json.loads(m.group(0))


def _norm_lang(lang: Optional[str]) -> str:
    """
    Normalize user/HTTP language tag:
      - Accept 'en', 'hi', 'mr' and region variants 'en-US', 'hi-IN', 'mr-IN'.
      - Support 'auto' to let the model detect from input.
      - Fallback: 'auto' if not provided; final fallback done in prompt to 'en'.
    """
    if not lang:
        return "auto"

    tag = lang.strip().lower()
    if tag == "auto":
        return "auto"

    # Keep only the base language part (e.g., 'hi-IN' -> 'hi')
    base = tag.split("-")[0]

    if base in {"en", "hi", "mr"}:
        return base

    # Unknown language -> let model detect
    return "auto"


def _stamp(d: Dict[str, Any]) -> Dict[str, Any]:
    d["created_at"] = d.get("created_at") or (datetime.utcnow().isoformat() + "Z")
    return d


# -------------------------- Prompt Builders --------------------------

def _system_prompt_for_text(lang: str) -> str:
    """
    Build a system prompt that:
      - Keeps JSON keys and controlled vocab in English.
      - Ensures all free-text values are in the target/detected language.
    """
    base_instr = (
        "You are PhishNet Guardian, an AI agent that detects phishing/scam messages and returns STRICT JSON only. "
        "Follow the reasoning pipeline: Intent -> Analysis -> Decision -> Action. "
        "Return ONLY JSON with the following keys (keys MUST be in English): "
        "intent, classification (Safe|Suspicious|Scam), risk_level (Low|Medium|High|Critical), confidence (0-1), "
        "red_flags (list of strings), recommended_actions (list of strings), not_to_do (list of strings), "
        "plan (list of strings), micro_lesson (string), "
        "quiz (object with 'question','options','answer','explanation'), "
        "trace (list of step objects with {stage,notes}), created_at (ISO). "
        "The controlled vocabulary fields classification and risk_level MUST be in English exactly as specified. "
        "However, all free-text VALUES (red_flags/recommended_actions/not_to_do/plan/micro_lesson/"
        "quiz.question/quiz.options/quiz.explanation/trace.notes) MUST be in the final output language."
    )

    if lang == "auto":
        lang_instr = (
            "Detect the user's language from the provided input text. "
            "If the detected language is one of {English, Hindi, Marathi}, write all free-text values in that language. "
            "Otherwise, write free-text in English. "
            "Never mix multiple languages; use exactly one language for all free-text values."
        )
    else:
        # Map to human-readable label for clarity in the instruction
        map_label = {"en": "English", "hi": "Hindi", "mr": "Marathi"}[lang]
        lang_instr = (
            f"Use {map_label} for ALL free-text values in the JSON. "
            "Do NOT include any other language."
        )

    return f"{base_instr} {lang_instr}"


def _system_prompt_for_vision(lang: str) -> str:
    base_instr = (
        "You are PhishNet Guardian. Analyze the screenshot for phishing/scam signals. "
        "Extract key text if needed and return STRICT JSON with keys (keys MUST be in English): "
        "intent, classification (Safe|Suspicious|Scam), risk_level (Low|Medium|High|Critical), confidence (0-1), "
        "red_flags (list), recommended_actions (list), not_to_do (list), plan (list), micro_lesson (string), "
        "quiz (object with 'question','options','answer','explanation'), trace (list of {stage,notes}), created_at. "
        "classification and risk_level must use the English labels above. "
        "All free-text values must be in the final output language."
    )

    if lang == "auto":
        lang_instr = (
            "Detect the dominant language from visible text in the image (or infer from context). "
            "If it is one of {English, Hindi, Marathi}, write all free-text values in that language; "
            "otherwise, write them in English. Use exactly one language."
        )
    else:
        map_label = {"en": "English", "hi": "Hindi", "mr": "Marathi"}[lang]
        lang_instr = f"Use {map_label} for ALL free-text values. Do not include any other language."

    return f"{base_instr} {lang_instr}"


# -------------------------- Gemini Calls --------------------------

def _call_gemini(text: str, preferred_language: Optional[str] = None) -> Dict[str, Any]:
    import google.generativeai as genai

    genai.configure(api_key=_require_key())
    model = genai.GenerativeModel(_model_name())

    lang = _norm_lang(preferred_language)
    sys_prompt = _system_prompt_for_text(lang)

    payload = {"text": text, "preferred_language": lang}
    parts = [sys_prompt, "\nInput:", json.dumps(payload, ensure_ascii=False)]

    try:
        resp = model.generate_content(parts)
    except Exception as e:
        raise RuntimeError(f"Gemini text call failed: {e}") from e

    try:
        data = _safe_json_parse(resp.text)
    except Exception as e:
        raw = (resp.text or "").strip()
        raise RuntimeError(f"Gemini returned non-JSON or blocked output. Raw head: {raw[:180]}") from e

    return _stamp(data)


def _call_gemini_vision(image_bytes: bytes, preferred_language: Optional[str] = None) -> Dict[str, Any]:
    import google.generativeai as genai

    genai.configure(api_key=_require_key())
    model = genai.GenerativeModel(_model_name())

    lang = _norm_lang(preferred_language)
    sys_prompt = _system_prompt_for_vision(lang)

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
    pre_trace: List[Dict[str, Any]] = [{"stage": "Intent", "notes": "Analyze potential scam text"}]
    result = _call_gemini(text, preferred_language)
    upstream = result.get("trace", [])
    result["trace"] = (pre_trace + upstream) if isinstance(upstream, list) else pre_trace
    return result


__all__ = [
    "analyze_text",
    "_call_gemini_vision",
]
