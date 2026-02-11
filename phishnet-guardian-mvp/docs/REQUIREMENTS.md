# 🧾 REQUIREMENTS — PhishNet Guardian Automation (MVP → Prod)

> **Purpose:** Define product, functional, and non‑functional requirements for *PhishNet Guardian* — a multi‑agent app that detects and explains phishing/scam messages and guides users with safe actions. This document aligns with the current FastAPI + Vanilla JS architecture and Gemini‑only AI integration.

---

## 1. Product Overview
- **Goal:** Help users quickly assess suspicious messages (text or screenshots) and prevent fraud by providing an explainable verdict and concrete actions.
- **Primary use cases:**
  - Paste a suspicious SMS/Email/Chat → get classification, risks, next steps.
  - Upload a screenshot (e.g., WhatsApp chat) → same analysis using Gemini Vision.
  - Review history (auditable), export CSV, and observe basic stats.
- **Audience:** Consumers, cyber‑awareness teams, L1 analysts, demo stakeholders.
- **Languages (UI & responses):** English (`en`), Hindi (`hi`), Marathi (`mr`).

---

## 2. Objectives & Success Criteria
- **O1. Accuracy & Utility:** Provide a clear verdict (Safe / Suspicious / Scam) with red flags and actionable steps.
- **O2. Explainability:** Deliver a concise micro‑lesson, 1‑question quiz, and trace of reasoning hops.
- **O3. Latency:** Median end‑to‑end < **4 s** (text), < **7 s** (image) per request on MVP infra.
- **O4. Reliability:** ≥ **99%** successful responses under demo load; graceful errors otherwise.
- **O5. Usability:** One‑screen workflow, image preview before submit, light/dark theme.
- **O6. Localizable:** Responses in selected language consistently.

---

## 3. Scope
### In‑Scope (MVP)
- Text & image (screenshot) analysis via **Gemini** (model configurable by `.env`).
- Strict JSON outputs; backend persists runs into **SQLite** (`phishnet.db`).
- Frontend: message form, image upload with **preview**, results pane, KPIs, history, CSV export, theme toggle.
- API routes: `/api/scan`, `/api/scan-image`, `/api/history`, `/api/history.csv`, `/api/stats`, `/api/health`.

### Out‑of‑Scope (MVP)
- User accounts, authN/Z, roles.
- Payments/billing, rate‑limit tiers.
- Cloud OCR fallback; non‑image file types.
- Postgres, Kubernetes, HA/DR (covered under Prod readiness).

---

## 4. Personas
- **End User:** Non‑technical user checking a message or screenshot; needs quick yes/no and what‑to‑do.
- **Security Analyst (L1):** Verifies user submissions; may export CSV for reviewing patterns.
- **Demo Owner / PM:** Needs stable flows for presentations and PoCs.

---

## 5. Functional Requirements (FR)
**FR‑1 Text Analyze:**
- **Input:** JSON `{ text: string(≥5), language?: 'en'|'hi'|'mr' }`.
- **Process:** Call Gemini text model with strict prompt; parse strict JSON; persist to DB.
- **Output:** Structured JSON (classification, risk_level, confidence, red_flags[], recommended_actions[], not_to_do[], plan[], micro_lesson, quiz{question,options[],answer,explanation}, trace[], created_at).

**FR‑2 Image Analyze:**
- **Input:** `multipart/form-data` with `file: image/*`, `language?: enum`.
- **Process:** Call Gemini (multimodal) with image bytes; parse strict JSON; persist.
- **Output:** Same schema as FR‑1.

**FR‑3 Multilingual Responses:**
- Model instructed to respond strictly in selected language; UI defaults to English; dropdown overrides.

**FR‑4 History & Export:**
- List `N` most recent entries with classification, risk, confidence, timestamp.
- Export CSV of recent runs.

**FR‑5 KPIs / Dashboard:**
- Totals and distribution of classifications.

**FR‑6 UI/UX:**
- Image **preview** thumbnail with name+size before submit.
- Theme toggle persisted; responsive layout; error toasts with readable details.
- Quiz options are **clickable** with immediate correct/incorrect feedback.

**FR‑7 Health:**
- `/api/health` returns service status + UTC time.

---

## 6. Non‑Functional Requirements (NFR)
- **NFR‑1 Performance:** P50 LAT text <4 s; image <7 s under normal network.
- **NFR‑2 Availability:** ≥99% during demos; clear message for upstream/API errors.
- **NFR‑3 Security:** No secrets in logs; validate file type & size; CORS controlled.
- **NFR‑4 Privacy:** Do not store user PII beyond submitted text/image (MVP stores texts for history; images not persisted to disk by default). Add a toggle later to avoid storing inputs.
- **NFR‑5 Observability:** Basic request logs + error traces; counters via `/api/stats`.
- **NFR‑6 Internationalization:** UTF‑8 throughout; content generated in selected language.
- **NFR‑7 Portability:** No system‑specific dependencies; runs on Linux/Windows/Mac with Python 3.11+.

---

## 7. System Architecture (Current)
```
Frontend (HTML/CSS/JS)
  ├─ Text form  ──────► POST /api/scan ─┐
  └─ Image form ─────► POST /api/scan-image │
                                     FastAPI ──► Gemini (text/vision)
                                         │
                                         └─ SQLite (phishnet.db) for history & stats
```
- **Model name** from `.env`: `GEMINI_MODEL` (recommended: `gemini-2.5-flash`).

---

## 8. API Contracts
### 8.1 `POST /api/scan`
**Request**
```json
{
  "text": "KYC will be blocked in 1 hour... http://bit.ly/xyz",
  "language": "en"
}
```
**Response (excerpt)**
```json
{
  "classification": "Scam",
  "risk_level": "High",
  "confidence": 0.92,
  "red_flags": ["Urgency/time pressure", "Shortened link (bit.ly)"]
}
```

### 8.2 `POST /api/scan-image`
**FormData:** `file=image/*`, `language=en|hi|mr`

### 8.3 `GET /api/history?limit=25`
**Response**
```json
{ "items": [{"id": 1, "classification": "Suspicious", "confidence": 0.64, "created_at": "2026-01-10T18:02:00Z"}],
  "count": 1 }
```

### 8.4 `GET /api/history.csv`
- CSV with columns: id, input_text, classification, risk_level, confidence, red_flags_json, actions_json, agent_trace_json, created_at

### 8.5 `GET /api/stats`
**Response**
```json
{ "total": 42, "distribution": {"Scam": 10, "Suspicious": 12, "Safe": 20} }
```

### 8.6 `GET /api/health`
**Response**
```json
{ "status": "ok", "time": "2026-02-11T10:01:11Z" }
```

---

## 9. Data Model (SQLite)
```
Table: scans
- id INTEGER PK AUTOINCREMENT
- input_text TEXT                # for image runs, stores a marker like "[screenshot upload]"
- classification TEXT            # Safe|Suspicious|Scam
- risk_level TEXT                # Low|Medium|High|Critical
- confidence REAL                # 0..1
- red_flags_json TEXT            # JSON array
- actions_json  TEXT             # JSON with recommended_actions, not_to_do, plan
- agent_trace_json TEXT          # JSON array (explainability)
- created_at TEXT                # ISO 8601 UTC
```

---

## 10. Security, Privacy, Compliance
- **API keys:** Read from `.env`; never hard‑code; rotate easily.
- **Uploads:** Restrict to `image/*`; validate size (e.g., ≤ 5 MB by default); do not store images on disk (MVP) — only process in memory.
- **Logs:** Avoid logging message content or secrets. Log request ids and error summaries.
- **CORS:** Allow UI origin(s) only for production; `*` is acceptable for local dev.
- **Compliance (future):** Add privacy notice, data deletion policy, opt‑out.

---

## 11. Error Handling & UX
- **Server:** Wrap Gemini calls; return `HTTP 500` with readable `detail` (auth/quota/model/JSON/db).
- **Client:** Show non‑blocking toast with error detail; keep inputs intact for re‑submit.
- **Common cases:** 404 model → suggest switching `GEMINI_MODEL` in `.env` and restarting.

---

## 12. Configuration & Environments
```
# .env
GEMINI_API_KEY=...
GEMINI_MODEL=gemini-2.5-flash   # widely available for text+image
```
- **Dev:** `--reload`, open CORS, SQLite.
- **Staging/Prod (future):** Reverse proxy, HTTPS, Postgres, secrets manager, observability.

---

## 13. Deployment Strategy (MVP)
- Uvicorn app service or container; mount frontend as static.
- Health endpoint for probes.
- Single instance acceptable; scale‑out not required for demos.

---

## 14. Testing & QA
- **Unit:** JSON parsing, API contracts.
- **Integration:** End‑to‑end text/image flows with mock responses.
- **Manual:** Multilingual checks, theme toggle, image preview.
- **Smoke:** Health, stats, history not empty after runs.

---

## 15. KPIs & Analytics
- Volumes: total scans per day; class distribution.
- Quality: user‑flagged false positives/negatives (future form).
- Performance: P50/P95 latencies per route.

---

## 16. Accessibility & Localization
- Keyboard‑navigable forms and buttons.
- Color contrast for light/dark; readable badges.
- I18N: ensure UTF‑8; prompt enforcements; selectable language.

---

## 17. Dependencies & Versions
- Python 3.11+
- FastAPI, Uvicorn, python‑dotenv, google‑generativeai, python‑multipart
- Frontend: Vanilla JS/CSS (no bundler)

---

## 18. Assumptions & Constraints
- Internet egress to Gemini API is available.
- Free tier may throttle; model availability varies per account/region.
- SQLite fits MVP logs; not intended for multi‑tenant heavy traffic.

---

## 19. Risks & Mitigations
- **Model 404 / permission issues:** expose clear error, allow `GEMINI_MODEL` override in `.env`.
- **Quota/rate limits:** backoff, show user guidance; move to paid tier if needed.
- **Non‑JSON outputs:** strict prompts + robust parser with helpful errors.
- **Large/unsupported files:** enforce MIME + size limits; client hints.

---

## 20. Rollout Plan
- **Week 1:** Consolidate Gemini‑only flows, strict JSON, error surfacing.
- **Week 2:** UX polish (preview, theme, quiz), KPI & history, README/Requirements.
- **Week 3:** Stakeholder demo; gather feedback; plan Postgres & auth for next phase.

---

## 21. Acceptance Criteria (MVP)
- A user can: (1) analyze text; (2) analyze a screenshot with preview; (3) see actionable results & quiz; (4) view history and CSV; (5) observe KPIs; (6) switch theme; (7) choose output language.
- All endpoints return 2xx under normal conditions; failures include readable `detail`.

---

## 22. Appendices
### A. Example Success (text)
```json
{
  "classification": "Suspicious",
  "risk_level": "Medium",
  "confidence": 0.78,
  "red_flags": ["Shortened link (bit.ly)", "KYC urgency"],
  "micro_lesson": "Time pressure + links are classic phishing cues. Verify via official app/website.",
  "quiz": {
    "question": "Should you tap the shortened link?",
    "options": ["Yes", "No"],
    "answer": "No",
    "explanation": "Always type the official address instead of tapping unknown links."
  }
}
```

### B. Example Error (model 404)
```json
{ "detail": "Gemini text call failed: 404 models/gemini-2.0-pro is not found ..." }
```

---

**© 2026 Radeon Rizers — PhishNet Guardian**
