"""Resume text -> structured profile.

Tries the LLM first (strict schema, temperature 0, one repair retry),
then falls back to a deterministic heuristic parser so the pipeline never dies.
"""

import re
from datetime import datetime, timezone
from typing import Optional

from app.core.logging import get_logger
from app.services.llm.client import llm, load_prompt
from app.services.llm.schemas import ResumeProfile
from app.services.skills.normalizer import extract_known_skills, normalize_many

log = get_logger("resume.parser")

SECTION_ALIASES = {
    "skills": ["skills", "technical skills", "technologies", "tech stack", "core competencies", "skills & tools"],
    "experience": ["experience", "work experience", "professional experience", "employment", "internships", "employment history"],
    "projects": ["projects", "academic projects", "personal projects", "key projects"],
    "education": ["education", "academic background", "qualifications"],
    "certifications": ["certifications", "certificates", "courses", "achievements"],
}

URL_RE = re.compile(r"https?://[^\s,;)\]>]+")
_MONTH = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?"
_DATE = rf"(?:{_MONTH}\s*)?'?\d{{2,4}}(?:\s*[-/]\s*\d{{1,2}})?"
DATE_RANGE_RE = re.compile(
    rf"(?P<start>{_DATE})\s*(?:[-–—]|\bto\b)\s*(?P<end>present|current|now|{_DATE})",
    re.I,
)
MONTHS = {m.lower(): i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}


def _find_sections(text: str) -> dict[str, str]:
    """Works with both layouts:

    EDUCATION
    --------
    ...content...

    and single-line resumes:
        Skills: Python, FastAPI, Docker
        Projects: Payment API - Python, PostgreSQL
    """
    content: dict[str, list[str]] = {key: [] for key in SECTION_ALIASES}
    current: Optional[str] = None
    for line in text.splitlines():
        stripped = line.strip()
        low = stripped.lower()
        key: Optional[str] = None
        rest = ""

        inline = re.match(r"^([a-z &/+]{2,30}):\s*(.*)$", low)
        if inline:
            label = inline.group(1).strip()
            for candidate, names in SECTION_ALIASES.items():
                if label in names:
                    key, rest = candidate, inline.group(2).strip()
                    break
        if key is None:
            label = re.sub(r"[^a-z &/+]", "", low).strip()
            if label and len(label) <= 40:
                for candidate, names in SECTION_ALIASES.items():
                    if label in names:
                        key = candidate
                        break
        if key is not None:
            current = key
            if rest:
                content[current].append(rest)
            continue
        if current is not None and stripped:
            content[current].append(stripped)
    return {key: "\n".join(lines) for key, lines in content.items() if lines}


def _parse_date(value: str) -> Optional[datetime]:
    value = value.strip().lower().replace("'", "20").replace(".", "")
    if value in {"present", "current", "now"}:
        return None
    value = value.strip()
    for fmt in ("%Y-%m", "%Y/%m", "%b %Y", "%B %Y", "%b %y", "%B %y", "%Y", "%m/%Y", "%m-%Y"):
        try:
            candidate = value.title() if "%b" in fmt or "%B" in fmt else value
            return datetime.strptime(candidate, fmt)
        except ValueError:
            continue
    m = re.search(r"(20\d{2}|\d{2})", value)
    if m:
        year = int(m.group(1))
        if year < 100:
            year += 2000
        return datetime(year, 1, 1)
    return None


def _duration_years(start_s: str, end_s: str) -> float:
    start = _parse_date(start_s)
    end = _parse_date(end_s)
    if end is None:
        end = datetime.now(timezone.utc).replace(tzinfo=None)
    if start is None:
        return 0.0
    if end < start:
        return 0.0
    return round(((end - start).days) / 365.25, 2)


def heuristic_parse(text: str, filename: str = "") -> dict:
    sections = _find_sections(text)
    skills = extract_known_skills(text)

    experience = []
    total_years = 0.0
    for raw_line in (sections.get("experience") or text).splitlines():
        line = raw_line.strip(" -*•\t")
        if not line or len(line) < 8:
            continue
        m = DATE_RANGE_RE.search(line)
        if not m:
            # continuation bullet belonging to the previous job
            if experience:
                experience[-1]["summary"] = (experience[-1]["summary"] + " " + line)[:400]
            continue
        years = _duration_years(m.group("start"), m.group("end"))
        if years > 0:
            total_years += years
        before = line[: m.start()].strip(" |,|-( ")
        before = re.sub(
            r"^(?:professional\s+|work\s+|relevant\s+)?experience\s*:?\s*", "", before, flags=re.I
        ).strip()
        if re.search(r"\bat\b", before, re.I):
            split_at = before.lower().rfind(" at ")
            title = before[:split_at].strip()
            company = before[split_at + 4 :].strip(" |,(\t")
        else:
            parts = re.split(r"\s[@|]\s|\s+-\s+|\s*,\s+", before)
            title = parts[0].strip() if parts else ""
            company = parts[1].strip() if len(parts) > 1 else ""
        title = re.sub(
            r"^\d+(?:\.\d+)?\s*\+?\s*years?(?:\s*of)?(?:\s*experience)?\s*", "", title, flags=re.I
        ).strip()
        if not title:
            title = company
        experience.append(
            {
                "company": company[:120],
                "title": title[:120],
                "start": m.group("start"),
                "end": None if m.group("end").lower() in {"present", "current", "now"} else m.group("end"),
                "skills_used": extract_known_skills(line),
                "summary": line[:300],
            }
        )

    if not experience:
        m = re.search(r"(\d+(?:\.\d+)?)\s*\+?\s*years?", text, re.I)
        if m:
            total_years = float(m.group(1))

    projects = []
    for line in (sections.get("projects") or "").splitlines():
        line = line.strip(" -*•\t")
        if len(line) < 12:
            continue
        name = re.split(r"[:|–—-]", line)[0].strip()[:120]
        projects.append(
            {
                "name": name,
                "tech": normalize_many(extract_known_skills(line)),
                "description": line[:400],
                "has_metrics": bool(re.search(r"\d+\s*%|\b\d+(\.\d+)?\s*(k|m)?\s*(req|users|requests|qps|ms|seconds|x)\b|\bincreased|\breduced|\bimproved", line, re.I)),
            }
        )

    education = [ln.strip(" -*•\t") for ln in (sections.get("education") or "").splitlines() if len(ln.strip()) > 5]
    certifications = [
        ln.strip(" -*•\t") for ln in (sections.get("certifications") or "").splitlines() if len(ln.strip()) > 5
    ]
    links = URL_RE.findall(text)

    name = ""
    for line in text.splitlines()[:5]:
        clean = line.strip()
        if 2 <= len(clean) <= 60 and not URL_RE.search(clean) and not clean.isdigit():
            if not re.search(r"@|\d{4}", clean):
                name = clean
                break

    return {
        "name": name or filename.rsplit(".", 1)[0],
        "skills": skills,
        "experience": experience[:10],
        "projects": projects[:15],
        "education": education[:5],
        "certifications": certifications[:10],
        "links": links[:10],
        "years_experience": round(total_years, 2),
    }


def parse_resume(text: str, filename: str = "") -> tuple[dict, str]:
    """Returns (profile_dict, strategy)."""
    if not text or len(text.strip()) < 40:
        return heuristic_parse(text or "", filename), "heuristic"

    if llm.enabled:
        prompt = load_prompt("extract_resume.txt", resume_text=text[:9000])
        for attempt in range(2):
            raw = llm.generate_json(prompt)
            if raw:
                try:
                    profile = ResumeProfile.model_validate(raw)
                    data = profile.model_dump()
                    if data.get("skills") or data.get("experience"):
                        if not data.get("years_experience"):
                            data["years_experience"] = heuristic_parse(text, filename).get("years_experience", 0.0)
                        data["skills"] = normalize_many(data.get("skills", []))
                        return data, f"llm:{llm.model}"
                except Exception as exc:
                    log.warning("resume LLM validation failed (attempt %d): %s", attempt + 1, exc)
                    prompt = load_prompt(
                        "extract_resume.txt", resume_text=text[:9000]
                    ) + f"\nYour previous answer was invalid: {exc}. Return valid JSON only."
            else:
                break

    return heuristic_parse(text, filename), "heuristic"


def resume_quality(profile: dict, text: str) -> float:
    """0..1: clear sections, measurable results, reasonable length."""
    score = 0.0
    low = (text or "").lower()
    if len(text or "") > 800:
        score += 0.2
    if len(text or "") > 2000:
        score += 0.1
    present = sum(1 for k in SECTION_ALIASES if k in _find_sections(text or ""))
    score += 0.25 * (present / len(SECTION_ALIASES))
    metrics = len(re.findall(r"\d+\s*%|\b\d+(\.\d+)?\s*(k|m)?\s*(users|requests|req/s|ms|seconds|x)\b", low))
    score += min(0.25, 0.08 * metrics)
    if profile.get("projects"):
        score += 0.1
    if profile.get("experience"):
        score += 0.1
    return round(min(1.0, score), 3)
