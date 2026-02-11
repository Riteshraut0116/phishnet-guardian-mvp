
import re
from typing import Dict, List

URL_RE = re.compile(r"https?://[\w\.-]+\.[a-z]{2,}(?:/\S*)?", re.I)
SHORTENERS = ["bit.ly", "tinyurl.com", "t.co", "is.gd", "buff.ly", "rb.gy", "ow.ly"]
URGENCY = ["urgent", "immediately", "within", "24 hours", "1 hour", "last warning", "final notice"]
SENSITIVE = ["otp", "password", "cvv", "pin", "kyc", "aadhar", "pan", "account blocked", "verify"]
REWARD = ["cash prize", "lottery", "winner", "reward", "gift"]
JOB = ["part-time", "work from home", "salary", "telegram", "whatsapp"]

LOOKALIKE_RE = re.compile(r"([a-z0-9]+)l([a-z0-9]+)\.|([a-z0-9]+)rn([a-z0-9]+)\.", re.I)

def domain_from_url(u: str) -> str:
    try:
        return re.findall(r"https?://([^/]+)", u, re.I)[0].lower()
    except Exception:
        return ""

def heuristic_assess(text: str) -> Dict:
    t = text.lower().strip()
    red_flags: List[str] = []
    features: List[str] = []

    urls = URL_RE.findall(t)
    if urls:
        features.append(f"urls:{len(urls)}")
        for u in urls:
            d = domain_from_url(u)
            if any(s in d for s in SHORTENERS):
                red_flags.append(f"Shortened link detected: {d}")
            if LOOKALIKE_RE.search(d):
                red_flags.append(f"Look-alike domain pattern: {d}")

    if any(k in t for k in URGENCY):
        red_flags.append("Urgency / time pressure language")
        features.append("urgency")
    if any(k in t for k in SENSITIVE):
        red_flags.append("Request for sensitive info (OTP/password/KYC)")
        features.append("sensitive")
    if any(k in t for k in REWARD):
        red_flags.append("Unsolicited reward/lottery claim")
        features.append("reward")
    if any(k in t for k in JOB):
        red_flags.append("Work-from-home/Telegram job lure")
        features.append("job_scam")

    upi = re.findall(r"[\w\.\-]+@[a-z]{3,}", t)
    if upi:
        red_flags.append("UPI handle involved; verify before paying")
        features.append("upi")

    phones = re.findall(r"\+?\d{10,13}", t)
    if phones:
        features.append("phone_numbers")

    score = 0
    score += 0.25 if urls else 0
    score += 0.25 if "sensitive" in features else 0
    score += 0.2 if "urgency" in features else 0
    score += 0.15 if "reward" in features else 0
    score += 0.15 if "job_scam" in features else 0
    score = min(1.0, score + 0.1 * len([f for f in red_flags if f.startswith("Look-alike")]))

    if score >= 0.75:
        classification = "Scam"
        risk = "Critical"
    elif score >= 0.5:
        classification = "Suspicious"
        risk = "High"
    elif score >= 0.25:
        classification = "Suspicious"
        risk = "Medium"
    else:
        classification = "Safe"
        risk = "Low"

    recommended = [
        "Verify with the official app/website—do not use links in the message",
        "Never share OTP, PIN, CVV, or passwords",
        "If it's bank/KYC related, call the official helpline number",
    ]
    not_to_do = [
        "Do not click shortened links",
        "Do not forward this to others",
        "Do not pay or share personal details",
    ]

    micro = (
        "Phishing often uses urgency + link + sensitive-info request. Pause, check sender, and go to the official app."
    )

    return {
        'classification': classification,
        'risk_level': risk,
        'confidence': round(score, 2),
        'red_flags': sorted(set(red_flags)),
        'recommended_actions': recommended,
        'not_to_do': not_to_do,
        'micro_lesson': micro,
        'features_detected': features,
    }
