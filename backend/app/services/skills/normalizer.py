"""Skill taxonomy loader + normalizer.

`ReactJS`, `React.js` and `react` must all become the same canonical skill,
otherwise nothing downstream can be compared.
"""

import re
from functools import lru_cache
from pathlib import Path
from typing import Iterable, Optional

import yaml
from rapidfuzz import fuzz, process

DEFAULT_TAXONOMY_PATH = Path(__file__).with_name("taxonomy.yaml")

FUZZY_CUTOFF = 90
RELATED_CREDIT = 0.6  # partial credit when JD wants X and candidate has a related skill


class Taxonomy:
    def __init__(self, data: dict):
        self.version = str(data.get("version", "1"))
        self.skills: dict[str, dict] = data.get("skills", {})
        self.alias_to_canonical: dict[str, str] = {}
        for canonical, meta in self.skills.items():
            key = canonical.lower().strip()
            self.alias_to_canonical[key] = canonical
            for alias in meta.get("aliases", []) or []:
                self.alias_to_canonical[str(alias).lower().strip()] = canonical
        self.all_aliases = list(self.alias_to_canonical.keys())
        self.related: dict[str, set[str]] = {
            name: set(meta.get("related", []) or []) for name, meta in self.skills.items()
        }
        self.categories: dict[str, str] = {
            name: (meta.get("category") or "other") for name, meta in self.skills.items()
        }
        self.roles: dict[str, set[str]] = {
            name: set(meta.get("roles", []) or []) for name, meta in self.skills.items()
        }

    def category(self, skill: str) -> str:
        return self.categories.get(skill, "other")

    def related_for(self, skill: str) -> set[str]:
        out = set(self.related.get(skill, set()))
        for other, rel in self.related.items():
            if skill in rel:
                out.add(other)
        return out


@lru_cache(maxsize=4)
def load_taxonomy(path: Optional[str] = None) -> Taxonomy:
    target = Path(path) if path else DEFAULT_TAXONOMY_PATH
    with open(target, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return Taxonomy(data)


_TAXONOMY = load_taxonomy()

TOKEN_RE = re.compile(r"[a-z0-9+#.\-]+")


def _clean(raw: str) -> str:
    return re.sub(r"\s+", " ", (raw or "").strip().lower())


def normalize(skill: str, taxonomy: Optional[Taxonomy] = None) -> Optional[str]:
    """Map any free-text skill name to its canonical taxonomy name (or None)."""
    tax = taxonomy or _TAXONOMY
    s = _clean(skill)
    if not s:
        return None
    s = s.strip(".,;:()[]{}|/\\\"'")
    if s in tax.alias_to_canonical:
        return tax.alias_to_canonical[s]
    # try token-pair exact match (e.g. "react.js frontend")
    for token in TOKEN_RE.findall(s):
        if token in tax.alias_to_canonical:
            return tax.alias_to_canonical[token]
    match = process.extractOne(s, tax.all_aliases, score_cutoff=FUZZY_CUTOFF)
    if match:
        return tax.alias_to_canonical[match[0]]
    return None


def normalize_many(skills: Iterable[str], taxonomy: Optional[Taxonomy] = None) -> list[str]:
    seen: dict[str, None] = {}
    for raw in skills:
        canon = normalize(raw, taxonomy)
        if canon:
            seen.setdefault(canon, None)
    return list(seen.keys())


def extract_known_skills(text: str, taxonomy: Optional[Taxonomy] = None) -> list[str]:
    """Find every taxonomy skill mentioned in a blob of text (word-boundary safe)."""
    tax = taxonomy or _TAXONOMY
    low = f" {re.sub(r'[^a-z0-9+#.\\-]+', ' ', (text or '').lower())} "
    found: dict[str, None] = {}
    for alias, canonical in tax.alias_to_canonical.items():
        if not alias or len(alias) < 2:
            continue
        if re.search(rf"(?<![a-z0-9+#]){re.escape(alias)}(?![a-z0-9+#])", low):
            found.setdefault(canonical, None)
    return list(found.keys())


def skill_credit(candidate_skills: dict[str, float], skill: str) -> float:
    """How much (0..1) the candidate satisfies `skill`, giving partial credit for related skills."""
    if skill in candidate_skills:
        return max(0.0, min(1.0, float(candidate_skills[skill])))
    tax = _TAXONOMY
    related = tax.related_for(skill)
    category = tax.category(skill)
    best = 0.0
    for cand, value in candidate_skills.items():
        if cand in related:
            best = max(best, RELATED_CREDIT * min(1.0, float(value) + 0.2))
        elif category != "other" and tax.category(cand) == category:
            # same family (e.g. two backend frameworks) - weaker credit.
            # Different programming languages must NOT earn this.
            best = max(best, 0.2 * min(1.0, float(value)) if category == "language" else 0.5 * min(1.0, float(value)))
    return min(best, 1.0)
