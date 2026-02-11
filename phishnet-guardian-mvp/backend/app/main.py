import os
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, List

from fastapi import FastAPI, HTTPException, Response, UploadFile, File
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


# ---------- Pydantic models ----------
class ScanRequest(BaseModel):
    text: str = Field(..., min_length=5, description="Suspicious message text to analyze")
    language: Optional[str] = Field(None, description="Preferred output language: 'en' | 'hi' | 'mr'")


# ---------- FastAPI app ----------
app = FastAPI(title="PhishNet Guardian – API", version="0.3.2")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------- Helpers ----------
def _persist_result(
    input_text: str,
    result: Dict[str, Any],
) -> None:
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


# ---------- API Routes ----------
@app.get("/api/health")
def health():
    return {"status": "ok", "time": datetime.utcnow().isoformat() + "Z"}


@app.post("/api/scan")
def api_scan(req: ScanRequest):
    """
    Text analysis (Gemini-only). If Gemini/auth/network fails, return a readable 500 detail.
    """
    try:
        result = analyze_text(req.text, preferred_language=req.language)
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

    return result


@app.post("/api/scan-image")
def api_scan_image(file: UploadFile = File(...), language: Optional[str] = None):
    """
    Screenshot analysis (Gemini Vision). Same error reporting pattern.
    """
    try:
        image_bytes = file.file.read()
        result = _call_gemini_vision(image_bytes, preferred_language=language)
    except Exception as e:
        import traceback; traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

    # Persist
    try:
        _persist_result("[screenshot upload]", result)
    except Exception as db_err:
        import traceback; traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"DB write failed: {db_err}")

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