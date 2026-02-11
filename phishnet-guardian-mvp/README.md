
# PhishNet Guardian – AMD Slingshot Hackathon MVP

An AI-driven automation platform that **detects and explains phishing/scam messages** and guides users with safe next steps.

> **Agentic flow:** Intent → Analysis → Decision → Action

---

## 🚩 Problem Statement (from submission)
AI + Cybersecurity & Privacy: **Detect and prevent phishing/scam messages** (SMS/Email/WhatsApp/UPI/job scams) using explainable AI; provide safe actions and micro-training to reduce fraud.

## ✨ What this MVP Delivers
- A single intelligent agent that:
  - Accepts text input via UI
  - **Uploads screenshots** (Gemini Vision primary, mocked fallback)
  - Understands intent and analyzes for scams
  - Produces an explainable verdict with red flags
  - Returns safe actions, a micro‑lesson, and a 1‑question quiz
  - Logs all results to SQLite for history/analytics
- Primary AI: **Gemini Free API**; fallback to **rule‑based heuristics** (and a mocked vision fallback)
- Clean, responsive UI with **dark/light mode**, gradients, cards, filters & CSV export

## 🧱 Architecture
```
frontend (HTML/CSS/JS)  →  FastAPI (Python)  →  AI Agent (Gemini or Heuristics)
                                        ↘  SQLite (logs)
```
- **Backend:** FastAPI, endpoints: `/api/scan`, `/api/scan-image`, `/api/history`, `/api/history.csv`, `/api/health`
- **AI Layer:** Google Gemini 1.5 Flash (text + image). If `GEMINI_API_KEY` not set => text heuristics; image has mocked fallback.
- **DB:** SQLite `phishnet.db`

## 🤖 AI Workflow (Agentic)
1. **Intent**: Determine task = analyze_scam_text or analyze_scam_image
2. **Analysis**: Pattern checks (URLs, urgency, sensitive info, rewards, WFH job lures, UPI) or Gemini reasoning/vision
3. **Decision**: Classification = Safe / Suspicious / Scam + risk level + confidence
4. **Action**: Recommended steps, avoid list, micro‑lesson, quiz, and structured trace

## 📦 Repository Layout
```
phishnet-guardian-mvp/
├─ backend/
│  └─ app/
│     ├─ main.py           # FastAPI app + endpoints + SQLite persistence
│     ├─ ai/
│     │  └─ agent.py       # Agent: Gemini (text & vision) + deterministic fallback
│     └─ utils/
│        └─ heuristics.py  # URL/urgency/sensitive/UPI/job-scam rules
├─ frontend/
│  ├─ index.html           # Dashboard + forms (text + image) + results + history
│  └─ assets/
│     ├─ styles.css        # Gradient UI, responsive, dark/light, chips, meter, toasts
│     ├─ script.js         # API calls, filters, CSV export, theme toggle
│     └─ shield.svg        # App icon
├─ docs/
│  └─ (add architecture images if needed)
├─ .env.example            # Put GEMINI_API_KEY here (copy to .env)
├─ requirements.txt        # Minimal backend deps
└─ README.md
```

## ⚙️ Setup & Run (Local)
```bash
python -m venv .venv
source .venv/bin/activate  # (Windows: .venv\Scripts\activate)

pip install -r requirements.txt
cp .env.example .env
# edit .env and set GEMINI_API_KEY=your_key  # optional for text; required for screenshot AI

uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
```
Open **http://localhost:8000** for the UI.

## 🧪 Example
```bash
curl -X POST http://localhost:8000/api/scan   -H 'Content-Type: application/json'   -d '{"text": "Your KYC will be blocked in 1 hour. Update at http://bit.ly/xyz", "language":"en"}'
```

## 🔐 Notes
- No secrets committed; configure via `.env`.
- Heuristic image fallback returns explainable guidance if Gemini key absent.

## 🚀 Demo Script (3 minutes)
1. Paste a scam SMS → **Analyze** → verdict + red flags + actions + meter
2. Upload a WhatsApp screenshot → **Analyze Screenshot** → (Gemini/heuristic) verdict
3. Show **History** with filters and **Export CSV**

MIT License. Built by **Radeon Rizers** (Lead: Ritesh Raut).
