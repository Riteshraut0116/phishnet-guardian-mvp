import os
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, List, Tuple

from fastapi import FastAPI, HTTPException, Response, UploadFile, File, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from dotenv import load_dotenv

# Gemini-only agent functions (no fallback)
from .ai.agent import analyze_text, _call_gemini_vision

# ---------- Env & Paths ----------
load_dotenv()

APP_DIR = Path(__file__).parent                 # backend/app
ROOT_DIR = APP_DIR.parent.parent                # project root
FRONTEND_DIR = ROOT_DIR / "frontend"
DB_PATH = ROOT_DIR / "phishnet.db"


# ---------- DB bootstrap ----------
def _init_db() -> None:
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS scans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                input_text TEXT,
                classification TEXT,
                risk_level TEXT,
                confidence REAL,
                red_flags_json TEXT,
                actions_json TEXT,
                agent_trace_json TEXT,
                created_at TEXT
            )
        """
        )
        conn.commit()
    finally:
        conn.close()


_init_db()


# ---------- Language Helpers ----------
SUPPORTED_BASE = {"en", "hi", "mr"}

def _norm_accept_language(accept_language: str | None) -> Optional[str]:
    """
    Extract first language range from header, e.g.:
      'hi-IN,hi;q=0.9,en;q=0.8' -> 'hi-IN'
    """
    if not accept_language:
        return None
    first = accept_language.split(",")[0].strip()
    return first or None


def _normalize_lang_tag(lang: Optional[str]) -> Optional[str]:
    """
    Normalize incoming language to a base tag the agent understands.

    Returns:
      - 'en' | 'hi' | 'mr' when recognized
      - 'auto' when unknown or empty (let the model detect)
      - None only when caller didn't specify and no header present;
        we will convert None -> 'auto' right before calling the agent.
    """
    if not lang:
        return None
    tag = lang.strip().lower()
    if tag == "auto":
        return "auto"
    base = tag.split("-")[0]
    if base in SUPPORTED_BASE:
        return base
    return "auto"


# ---------- Pydantic models ----------
class ScanRequest(BaseModel):
    text: str = Field(..., min_length=5, description="Suspicious message text to analyze")
    # NOTE: allow region codes; we'll normalize to base
    language: Optional[str] = Field(
        None,
        description="Preferred output language: 'en'|'hi'|'mr' or region like 'hi-IN'. "
                    "If omitted, server uses Accept-Language or auto-detect."
    )


# ---------- FastAPI app ----------
app = FastAPI(title="PhishNet Guardian – API", version="0.4.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],            # lock down in prod if needed
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=[
        "Content-Type",
        "Accept",
        "Accept-Language",         # important for multilingual
        "Authorization",
        "X-Requested-With"
    ],
)

# Simple request logger (helpful on Render)
@app.middleware("http")
async def access_log(request: Request, call_next):
    try:
        response = await call_next(request)
        return response
    finally:
        # Minimal log; avoid dumping bodies in prod
        print(
            "REQ",
            request.method,
            request.url.path,
            "| Accept-Language:",
            request.headers.get("Accept-Language", "-"),
            "| UA:",
            request.headers.get("User-Agent", "-"),
            flush=True,
        )


# ---------- Helpers ----------
def _persist_result(input_text: str, result: Dict[str, Any]) -> None:
    """Insert one scan row into SQLite, surfacing errors if any."""
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO scans (
                input_text, classification, risk_level, confidence,
                red_flags_json, actions_json, agent_trace_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                input_text,
                result.get("classification", ""),
                result.get("risk_level", ""),
                float(result.get("confidence", 0.0)),
                json.dumps(result.get("red_flags", []), ensure_ascii=False),
                json.dumps(
                    {
                        "recommended_actions": result.get("recommended_actions", []),
                        "not_to_do": result.get("not_to_do", []),
                        "plan": result.get("plan", []),
                    },
                    ensure_ascii=False,
                ),
                json.dumps(result.get("trace", []), ensure_ascii=False),
                result.get("created_at", datetime.utcnow().isoformat() + "Z"),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _resolve_language(request: Request, body_lang: Optional[str], query_lang: Optional[str] = None) -> str:
    """
    Resolve final language order:
      1) explicit body param (language)
      2) query param (?lang=)
      3) Accept-Language header
      4) auto (model detects)
    """
    # 1) body
    lang = _normalize_lang_tag(body_lang)
    if lang:
        return lang

    # 2) query
    lang = _normalize_lang_tag(query_lang)
    if lang:
        return lang

    # 3) Accept-Language
    header_tag = _norm_accept_language(request.headers.get("Accept-Language"))
    lang = _normalize_lang_tag(header_tag)
    if lang:
        return lang

    # 4) default to 'auto' (let the model detect)
    return "auto"


# ---------- API Routes ----------
@app.get("/api/health")
def health():
    return {"status": "ok", "time": datetime.utcnow().isoformat() + "Z"}


@app.post("/api/scan")
async def api_scan(req: ScanRequest, request: Request):
    """
    Text analysis (Gemini-only). If Gemini/auth/network fails, return a readable 500 detail.
    Multilingual: picks language from body or Accept-Language or auto-detect.
    """
    try:
        final_lang = _resolve_language(request, req.language)
        result = analyze_text(req.text, preferred_language=final_lang)
    except Exception as e:
        # Print full traceback on server for quick pinpointing
        import traceback; traceback.print_exc()
        # Surface a clear message to the client (shown in the orange toast)
        raise HTTPException(status_code=500, detail=str(e))

    # Persist
    try:
        _persist_result(req.text, result)
    except Exception as db_err:
        import traceback; traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"DB write failed: {db_err}")

    # Optionally echo which lang was used (handy for UI/debug)
    result.setdefault("_lang_used", final_lang)
    return result


@app.post("/api/scan-image")
async def api_scan_image(
    request: Request,
    file: UploadFile = File(...),
    # allow query param ?lang=mr-IN
    lang: Optional[str] = Query(None, description="Preferred language e.g. hi-IN, mr, en-US"),
    language: Optional[str] = Query(None, description="Alias for lang")  # tolerate both names
):
    """
    Screenshot analysis (Gemini Vision).
    Picks language from query, header, or auto-detect.
    """
    # Prefer explicit 'lang' over 'language' if both present
    query_lang = lang or language
    try:
        image_bytes = file.file.read()
        final_lang = _resolve_language(request, body_lang=None, query_lang=query_lang)
        result = _call_gemini_vision(image_bytes, preferred_language=final_lang)
    except Exception as e:
        import traceback; traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

    # Persist
    try:
        _persist_result("[screenshot upload]", result)
    except Exception as db_err:
        import traceback; traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"DB write failed: {db_err}")

    result.setdefault("_lang_used", final_lang)
    return result


# Helpful preflight handler (optional)
@app.options("/api/scan")
def options_scan():
    return Response(status_code=200)


@app.get("/api/history")
def history(limit: int = 25):
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        cur.execute(
            """SELECT id, input_text, classification, risk_level, confidence,
                      red_flags_json, actions_json, agent_trace_json, created_at
               FROM scans ORDER BY id DESC LIMIT ?""",
            (limit,),
        )
        rows = cur.fetchall()
    finally:
        conn.close()

    items: List[Dict[str, Any]] = []
    for r in rows:
        actions = json.loads(r[6]) if r[6] else {}
        items.append(
            {
                "id": r[0],
                "input_text": r[1],
                "classification": r[2],
                "risk_level": r[3],
                "confidence": r[4],
                "red_flags": json.loads(r[5]) if r[5] else [],
                "recommended_actions": actions.get("recommended_actions", []),
                "not_to_do": actions.get("not_to_do", []),
                "plan": actions.get("plan", []),
                "created_at": r[8],
            }
        )
    return {"items": items, "count": len(items)}


@app.get("/api/history.csv")
def history_csv(limit: int = 500):
    import csv, io

    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        cur.execute(
            """SELECT id, input_text, classification, risk_level, confidence,
                      red_flags_json, actions_json, agent_trace_json, created_at
               FROM scans ORDER BY id DESC LIMIT ?""",
            (limit,),
        )
        rows = cur.fetchall()
    finally:
        conn.close()

    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(
        ["id", "input_text", "classification", "risk_level",
         "confidence", "red_flags", "actions", "trace", "created_at"]
    )
    for r in rows:
        w.writerow(r)
    return Response(content=out.getvalue(), media_type="text/csv")


@app.get("/api/stats")
def stats():
    """
    Totals + classification distribution for dashboard KPIs.
    """
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        cur.execute("""SELECT classification, COUNT(*) FROM scans GROUP BY classification""")
        dist = {k if k else "Unknown": v for k, v in cur.fetchall()}
        cur.execute("""SELECT COUNT(*) FROM scans""")
        total = cur.fetchone()[0]
    finally:
        conn.close()
    return {"total": total, "distribution": dist}


# ---------- Static Frontend (MOUNT LAST) ----------
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
