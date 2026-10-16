"""Raw JD text -> fixed structured shape.

LLM first (strict schema, temperature 0, one repair retry), heuristic fallback.
Everything is normalised through the same skills taxonomy as resumes.
"""

import re
from typing import Optional

from app.core.config import ROLES, SENIORITY_VALUES
from app.core.logging import get_logger
from app.services.llm.client import llm, load_prompt
from app.services.llm.schemas import StructuredJD
from app.services.skills.normalizer import Taxonomy, extract_known_skills, load_taxonomy, normalize_many

log = get_logger("jd.extractor")

MUST_MARKERS = [
    "required", "must have", "must-have", "must have", "strong knowledge", "essential",
    "you should have", "we need", "minimum", "requirements", "required skills",
]
NICE_MARKERS = [
    "good to have", "good-to-have", "plus", "preferred", "nice to have", "desirable",
    "optional", "bonus", "added advantage", "plus point",
]
DEGREE_MARKERS = ["b.tech", "b.e", "be ", "bachelor", "m.tech", "m.e", "master", "mba", "mca", "bca", "b.sc", "m.sc", "ph.d", "degree"]
CITIES = [
    "bangalore", "bengaluru", "hyderabad", "pune", "mumbai", "delhi", "chennai", "gurgaon",
    "noida", "ahmedabad", "kolkata", "cochin", "jaipur", "indore", "chandigarh", "remote",
]
SENIORITY_KEYWORDS = [
    ("intern", ["intern", "internship", "trainee"]),
    ("junior", ["junior", "entry level", "entry-level", "fresher", "0-2 years", "0-3 years", "associate"]),
    ("senior", ["senior", "sr.", "staff", "lead", "architect", "5+ years", "6+ years", "7+ years", "8+ years"]),
    ("mid", ["mid level", "mid-level", "2-5 years", "3-5 years", "4-6 years", "experienced"]),
]
RESPONSIBILITY_MARKERS = ["responsibilities", "what you", "you will", "roles", "day to day", "key duties"]


def _sentences(text: str) -> list[str]:
    parts = re.split(r"[\n\r]+|(?<=[.;])\s+(?=[A-Z])", text)
    return [p.strip() for p in parts if p and p.strip()]


def _classify_role(text: str, skills: list[str], hint: Optional[str]) -> str:
    tax: Taxonomy = load_taxonomy()
    scores = {role: 0.0 for role in ROLES}
    for skill in skills:
        for role in tax.roles.get(skill, set()):
            if role in scores:
                scores[role] += 1.0
    title_match = re.search(
        r"frontend|backend|full[\s-]?stack|data\s*(analyst|engineer|scientist)|machine\s*learning|\bml\b|devops|cloud|mobile|android|ios|flutter",
        text[:400],
        re.I,
    )
    if title_match:
        token = title_match.group(0).lower().replace(" ", "")
        mapping = {
            "frontend": "frontend", "backend": "backend", "fullstack": "fullstack",
            "full-stack": "fullstack", "dataanalyst": "data", "dataengineer": "data",
            "datascientist": "data", "machinelearning": "ml", "ml": "ml",
            "devops": "devops", "cloud": "devops", "mobile": "mobile",
            "android": "mobile", "ios": "mobile", "flutter": "mobile",
        }
        key = title_match.group(0).lower()
        if key in mapping:
            scores[mapping[key]] = scores.get(mapping[key], 0) + 2.5
    if hint in ROLES:
        scores[hint] = scores.get(hint, 0) + 2.0
    best = max(scores.items(), key=lambda kv: kv[1])
    if best[1] <= 0:
        return hint if hint in ROLES else "fullstack"
    return best[0]


def _seniority_of(text: str) -> str:
    low = text[:1500].lower()
    for value, keywords in SENIORITY_KEYWORDS:
        if any(k in low for k in keywords):
            return value
    return "mid"


def _min_years(text: str) -> float:
    m = re.search(r"(\d+(?:\.\d+)?)\s*\+?\s*(?:-\s*\d+\s*)?years?", text, re.I)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            return 0.0
    return 0.0


def _employment_type_of(text: str) -> str:
    low = text.lower()
    if "internship" in low or re.search(r"\bintern\b", low):
        return "internship"
    if re.search(r"full[- ]?time|permanent|\bto\s+hiring\b|\bjobs?\b", low):
        return "full-time"
    if "apprentice" in low:
        return "apprenticeship"
    if "contract" in low:
        return "contract"
    return ""


def _compensation_of(sentences: list[str]) -> str:
    word = re.compile(
        r"stipend|salary|\bctc\b|\blpa\b|compensation|remuneration|rupees?|\binr\b|"
        r"per\s*(?:month|annum|year)|\b(?:monthly|annual|yearly)\b|\bpay\b",
        re.I,
    )
    amount = re.compile(
        r"(?:₹|rs\.?|inr|\$|€|£)?\s*\d[\d,]*|\d[\d,]*(?:\s*[-–—]\s*\d[\d,]*)?\s*(?:lpa|ctc|k)\b",
        re.I,
    )
    for s in sentences:
        if word.search(s) and amount.search(s):
            return s[:160]
    for s in sentences:
        if word.search(s):
            return s[:160]
    return ""


def _eligibility_of(sentences: list[str]) -> str:
    parts: list[str] = []
    for s in sentences:
        low = s.lower()
        if any(m in low for m in DEGREE_MARKERS) or re.search(
            r"\bgpa\b|\bcgpa\b|cut[- ]?off|academic\s+stream|aggregate|eligib\w*|final\s+year",
            low,
        ):
            parts.append(s[:180])
        if len(parts) >= 3:
            break
    return " | ".join(parts)


def _selection_process_of(lines: list[str]) -> list[str]:
    out: list[str] = []
    collecting = False
    for line in lines:
        low = line.lower()
        if "selection process" in low or "recruitment process" in low or "selection:" in low:
            collecting = True
            continue
        if not collecting:
            continue
        clean = re.sub(r"^\d+[.)]\s+|^[-•*]\s+", "", line).strip()
        if not clean or len(clean) > 80:
            collecting = False
            continue
        if re.search(r"(aptitude|coding|technical|group|discussion|hr |interview|test|round|online|mcq|written|assessment)", clean.lower()):
            out.append(clean[:120])
        elif len(out) > 5:
            collecting = False
        if len(out) >= 8:
            break
    return out


def _duration_of(sentences: list[str]) -> str:
    for s in sentences:
        low = s.lower()
        if re.search(
            r"\b\d+\s*(?:[-–—]\s*\d+\s*)?(?:months?|weeks?)\b|\bduration\b|\bfor\s+\d+\b|"
            r"during the \d+(?:st|nd|rd|th)?\s*semester|\bover\s+\d+\s+(?:months?|weeks?)\b",
            low,
        ):
            return s[:150]
    return ""


def _conversion_of(sentences: list[str]) -> str:
    for s in sentences:
        low = s.lower()
        if re.search(r"conversion|convert(?:s|ed)?\s+to\s+(?:a\s+)?full|be[ ]?ame\s+(permanent|full)|full[- ]?time\s+(?:opportunity|employment|job|position)|absorb|post[- ]?internship\s+(salary|offer)", low):
            return s[:180]
    return ""


def _perks_of(sentences: list[str]) -> list[str]:
    out: list[str] = []
    offer_markers = ("you get", "we offer", "we provide", "enjoy", "perks", "benefits", "medical", "insurance", "mentorship", "learning", "stipend", "reimburs", "global travel", "work from", "hybrid")
    for s in sentences:
        if len(s) > 240 or s in out:
            continue
        low = s.lower()
        if re.search(r"\b(perks|benefits|advantage)\b", low) or any(m in low for m in offer_markers):
            if re.search(r"\d|internship|health|insur|travel|flexible|learning|career|growth|mentor", low):
                out.append(s[:200])
        if len(out) >= 8:
            break
    return out


def _about_of(lines: list[str], max_chars: int = 600) -> str:
    start = -1
    for i, line in enumerate(lines[:8]):
        if re.search(
            r"^(?:about(?:\s+us|\s+the\s+company|\s+\w[\w &]*)?|who\s+we\s+are|company\s+overview)[:. \t]*$",
            line.lower().strip(),
        ):
            start = i + 1
            break
    if start == -1:
        for line in lines[:6]:
            if len(line) > 110:
                return line.strip()[:max_chars]
        return ""
    headings = {
        "why us", "why", "about the opportunity", "opportunity details", "duration",
        "eligibility", "eligibility criteria", "selection process", "perks", "benefits",
        "skills", "responsibilities", "what you", "what we are looking for", "requirements",
        "internship stipend", "the role", "job description", "positions", "roles available",
        "selection", "it training focus areas",
    }
    parts: list[str] = []
    for line in lines[start:]:
        low = line.strip()
        key = " ".join(re.sub(r"[^a-z &/]+", " ", low.lower()).split())
        is_heading = (
            "why" == key.split()[0] if key else False
        ) or key in headings or bool(re.match(r"^[a-z][a-z &·./]*:$", key))
        if low and len(low) < 40 and is_heading:
            break
        parts.append(low)
        if sum(len(p) for p in parts) > max_chars:
            break
    return " ".join(parts).strip()[:max_chars]


def heuristic_extract(text: str, hints: dict) -> dict:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    title = (hints.get("title") or (lines[0] if lines else "Role")).strip()[:200]
    sentences = _sentences(text)

    must: list[str] = []
    nice: list[str] = []
    for sentence in sentences:
        low = sentence.lower()
        found = extract_known_skills(sentence)
        if not found:
            continue
        if any(marker in low for marker in MUST_MARKERS):
            must.extend(found)
        elif any(marker in low for marker in NICE_MARKERS):
            nice.extend(found)
    all_skills = extract_known_skills(text)
    title_skills = extract_known_skills(title)
    must.extend(title_skills)
    if not must and not nice:
        must = title_skills or all_skills[:4]
        nice = [s for s in all_skills if s not in must]

    must = normalize_many(must)
    nice = [s for s in normalize_many(nice) if s not in must]
    if not must and not nice:
        nice = all_skills

    role_family = _classify_role(text, all_skills, hints.get("role"))
    seniority = _seniority_of(text)
    min_years = _min_years(text)

    responsibilities = []
    collecting = False
    for line in lines:
        low = line.lower()
        if any(marker in low for marker in RESPONSIBILITY_MARKERS):
            collecting = True
            continue
        if collecting:
            if re.match(r"^[-•*]\s+", line) or re.match(r"^\d+[.)]\s+", line):
                responsibilities.append(re.sub(r"^[-•*]\s+|^\d+[.)]\s+", "", line)[:220])
            elif len(responsibilities) and (len(line) < 25 or line.endswith(":")):
                collecting = False
            elif len(responsibilities) > 8:
                collecting = False
    if not responsibilities:
        responsibilities = [
            s[:220]
            for s in sentences
            if len(s) > 30 and re.search(r"\b(build|design|develop|maintain|own|deliver|implement|collaborate)\b", s, re.I)
        ][:6]

    education = ""
    for sentence in sentences:
        if any(marker in sentence.lower() for marker in DEGREE_MARKERS):
            education = sentence[:200]
            break

    location = ""
    low_all = text.lower()
    for city in CITIES:
        if city in low_all:
            location = city.title()
            break
    if not location:
        m = re.search(r"location[:\s]+([^\n.,;]+)", text, re.I)
        if m:
            location = m.group(1).strip()[:80]

    remote = ""
    if re.search(r"\bremote\b", low_all):
        remote = "remote"
    if re.search(r"\bhybrid\b", low_all):
        remote = "hybrid"
    if re.search(r"\bon[- ]?site\b", low_all):
        remote = "onsite"
    if not remote and re.search(r"work\s*from\s*home|fully\s+remote", low_all):
        remote = "remote"

    return {
        "company": (hints.get("company") or "").strip(),
        "title": title,
        "role_family": role_family,
        "seniority": seniority,
        "min_years": min_years,
        "must_have": must,
        "nice_to_have": nice,
        "responsibilities": responsibilities,
        "education": education,
        "location": location,
        "remote": remote,
        "industry": (hints.get("industry") or "").strip(),
        "employment_type": _employment_type_of(text),
        "compensation": _compensation_of(sentences),
        "work_mode": remote,
        "duration": _duration_of(sentences),
        "conversion": _conversion_of(sentences),
        "eligibility": _eligibility_of(sentences),
        "selection_process": _selection_process_of(lines),
        "perks": _perks_of(sentences),
        "about": _about_of(lines),
    }


def _normalize_struct(data: dict, hints: dict, text: str) -> dict:
    struct = StructuredJD.model_validate({**(data or {}), "company": (data or {}).get("company") or hints.get("company") or ""})
    dump = struct.model_dump()

    must = normalize_many(dump.get("must_have") or [])
    nice = [s for s in normalize_many(dump.get("nice_to_have") or []) if s not in must]
    if not must and not nice:
        fallback = extract_known_skills(text)
        must = fallback[:6]
        nice = fallback[6:]
    dump["must_have"] = must
    dump["nice_to_have"] = nice

    if dump.get("role_family") not in ROLES:
        dump["role_family"] = _classify_role(text, must + nice, hints.get("role"))
    if dump.get("seniority") not in SENIORITY_VALUES:
        dump["seniority"] = _seniority_of(text)
    try:
        dump["min_years"] = max(0.0, float(dump.get("min_years") or 0.0))
    except (TypeError, ValueError):
        dump["min_years"] = 0.0
    if dump.get("title") in (None, ""):
        dump["title"] = hints.get("title") or (text.strip().splitlines() or ["Role"])[0][:200]
    if not dump.get("company"):
        dump["company"] = hints.get("company") or ""
    dump["responsibilities"] = [str(r)[:300] for r in (dump.get("responsibilities") or []) if str(r).strip()][:12]
    dump["employment_type"] = str(dump.get("employment_type") or "").strip()[:30]
    dump["compensation"] = str(dump.get("compensation") or "").strip()[:200]
    dump["work_mode"] = str(dump.get("work_mode") or "").strip()[:30] or dump.get("remote") or ""
    dump["duration"] = str(dump.get("duration") or "").strip()[:200]
    dump["conversion"] = str(dump.get("conversion") or "").strip()[:250]
    dump["eligibility"] = str(dump.get("eligibility") or "").strip()[:400]
    dump["selection_process"] = [str(r)[:160] for r in (dump.get("selection_process") or []) if str(r).strip()][:10]
    dump["perks"] = [str(r)[:200] for r in (dump.get("perks") or []) if str(r).strip()][:12]
    dump["about"] = str(dump.get("about") or "").strip()[:1000]
    dump["summary_text"] = build_summary_text(dump)
    return dump


def build_summary_text(struct: dict) -> str:
    return (
        f"{struct.get('company', '')} - {struct.get('title', '')}. "
        f"Role: {struct.get('role_family', '')}, {struct.get('seniority', '')}, "
        f"min {struct.get('min_years', 0)} years. "
        f"Must have: {', '.join(struct.get('must_have') or [])}. "
        f"Nice to have: {', '.join(struct.get('nice_to_have') or [])}. "
        f"Responsibilities: {'; '.join((struct.get('responsibilities') or [])[:6])}"
    )


def extract_structured_jd(text: str, hints: Optional[dict] = None) -> tuple[dict, str]:
    """Returns (structured_dict, strategy)."""
    hints = hints or {}
    if not text or not text.strip():
        return _normalize_struct(heuristic_extract("", hints), hints, ""), "heuristic"

    if llm.enabled:
        prompt = load_prompt("extract_jd.txt", jd_text=text[:9000])
        for attempt in range(2):
            raw = llm.generate_json(prompt)
            if raw:
                try:
                    return _normalize_struct(raw, hints, text), f"llm:{llm.model}"
                except Exception as exc:
                    log.warning("JD LLM validation failed (attempt %d): %s", attempt + 1, exc)
                    prompt = load_prompt("extract_jd.txt", jd_text=text[:9000]) + (
                        f"\nYour previous answer was invalid: {exc}. Return valid JSON only."
                    )
            else:
                break

    try:
        return _normalize_struct(heuristic_extract(text, hints), hints, text), "heuristic"
    except Exception as exc:
        log.warning("heuristic JD extraction failed: %s - using minimal fallback", exc)
        minimal = {
            "company": hints.get("company") or "",
            "title": hints.get("title") or (text.strip().splitlines() or ["Role"])[0][:200],
            "role_family": hints.get("role") or "fullstack",
            "seniority": "mid",
            "min_years": 0.0,
            "must_have": extract_known_skills(text)[:6],
            "nice_to_have": [],
            "responsibilities": [],
            "education": "",
            "location": "",
            "remote": "",
            "industry": hints.get("industry") or "",
            "employment_type": "",
            "compensation": "",
            "work_mode": "",
            "duration": "",
            "conversion": "",
            "eligibility": "",
            "selection_process": [],
            "perks": [],
            "about": "",
        }
        minimal["summary_text"] = build_summary_text(minimal)
        return minimal, "fallback"
