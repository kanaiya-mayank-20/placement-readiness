"""Gemini REST client with graceful fallbacks.

- No API key / network error / bad JSON  -> returns None, caller falls back to rules.
- Embeddings fall back to a deterministic hashed bag-of-words vector so that
  retrieval ALWAYS works, even fully offline.
"""

import hashlib
import json
import re
from typing import Optional

import httpx

from app.core.config import PROMPTS_DIR, settings
from app.core.logging import get_logger

log = get_logger("llm")

GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"


def load_prompt(name: str, **kwargs: str) -> str:
    text = (PROMPTS_DIR / name).read_text(encoding="utf-8")
    for key, value in kwargs.items():
        text = text.replace("{" + key + "}", value)
    return text


def _extract_json(text: str):
    if not text:
        return None
    text = text.strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    # fenced block
    m = re.search(r"```(?:json)?\s*(.+?)\s*```", text, re.S)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            pass
    # first balanced object/array
    for opener, closer in (("{", "}"), ("[", "]")):
        start = text.find(opener)
        if start == -1:
            continue
        depth = 0
        for idx in range(start, len(text)):
            if text[idx] == opener:
                depth += 1
            elif text[idx] == closer:
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start : idx + 1])
                    except Exception:
                        break
    return None


class LLMClient:
    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key if api_key is not None else settings.GEMINI_API_KEY
        self.model = model or settings.GEMINI_MODEL

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def generate_json(self, prompt: str, system: Optional[str] = None, temperature: float = 0.0):
        if not self.enabled:
            return None
        contents = [{"parts": [{"text": prompt}]}]
        if system:
            contents.insert(0, {"role": "user", "parts": [{"text": system}]})
        body = {
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
                "responseMimeType": "application/json",
                "maxOutputTokens": 4096,
            },
        }
        url = f"{GEMINI_BASE}/models/{self.model}:generateContent"
        try:
            resp = httpx.post(
                url,
                params={"key": self.api_key},
                json=body,
                timeout=settings.LLM_TIMEOUT,
            )
            if resp.status_code >= 400:
                log.warning("Gemini error %s: %s", resp.status_code, resp.text[:300])
                return None
            data = resp.json()
            parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
            text = "".join(p.get("text", "") for p in parts)
            return _extract_json(text)
        except Exception as exc:  # network / timeout / shape issues
            log.warning("Gemini call failed: %s", exc)
            return None

    # ---------------- embeddings ----------------
    def embed(self, text: str) -> Optional[list[float]]:
        if not self.enabled or not text:
            return None
        model = settings.EMBEDDING_MODEL
        body = {"model": f"models/{model}", "content": {"parts": [{"text": text[:4000]}]}}
        url = f"{GEMINI_BASE}/models/{model}:embedContent"
        try:
            resp = httpx.post(url, params={"key": self.api_key}, json=body, timeout=45)
            if resp.status_code >= 400:
                log.warning("Gemini embed error %s: %s", resp.status_code, resp.text[:200])
                return None
            data = resp.json()
            values = (
                data.get("embedding", {}).get("values")
                or (data.get("embeddings") or [{}])[0].get("values")
                or data.get("values")
            )
            if values and isinstance(values, list):
                return [float(v) for v in values]
        except Exception as exc:
            log.warning("Gemini embed failed: %s", exc)
        return None

    def embed_or_hash(self, text: str) -> list[float]:
        return self.embed(text) or hash_embed(text)


def hash_embed(text: str) -> list[float]:
    """Deterministic offline embedding: hashed token + bigram TF vector, L2 normalized."""
    dim = settings.EMBEDDING_FALLBACK_DIM
    vec = [0.0] * dim
    tokens = re.findall(r"[a-z0-9+#.\-]{2,}", (text or "").lower())
    grams = tokens + [f"{a}_{b}" for a, b in zip(tokens, tokens[1:])]
    if not grams:
        grams = ["empty"]
    for gram in grams:
        digest = hashlib.md5(gram.encode("utf-8")).digest()
        idx = int.from_bytes(digest[:4], "little") % dim
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vec[idx] += sign
    norm = sum(v * v for v in vec) ** 0.5 or 1.0
    return [v / norm for v in vec]


def cosine(a: Optional[list], b: Optional[list]) -> float:
    if not a or not b:
        return 0.0
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    if not na or not nb:
        return 0.0
    return max(-1.0, min(1.0, dot / (na * nb)))


llm = LLMClient()
