"""Model router. Policy: identifiable data -> Ollama only. De-identified -> Groq (fast) or Gemini (deep)."""
import re

import httpx

from .config import settings

_PATTERNS = [
    (re.compile(r"\b\d{6}\s?\d{4}\s?\d{3}\b"), "[ID]"),             # SA ID-style numbers
    (re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b"), "[EMAIL]"),
    (re.compile(r"\b(?:\+?27|0)\d{9}\b"), "[PHONE]"),
    (re.compile(r"0x[a-fA-F0-9]{40}"), "[WALLET]"),
]


def deidentify(text: str) -> str:
    """Basic regex scrub. Names/addresses need an NER model for real use."""
    for rx, repl in _PATTERNS:
        text = rx.sub(repl, text)
    return text


async def _ollama(prompt: str) -> str:
    async with httpx.AsyncClient(timeout=120) as c:
        r = await c.post(f"{settings.ollama_url}/api/generate",
                         json={"model": settings.ollama_model, "prompt": prompt, "stream": False})
        r.raise_for_status()
        return r.json()["response"]


async def _groq(prompt: str) -> str:
    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.post("https://api.groq.com/openai/v1/chat/completions",
                         headers={"Authorization": f"Bearer {settings.groq_api_key}"},
                         json={"model": settings.groq_model, "messages": [{"role": "user", "content": prompt}]})
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]


async def _gemini(prompt: str) -> str:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{settings.gemini_model}:generateContent"
    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.post(url, headers={"x-goog-api-key": settings.gemini_api_key},
                         json={"contents": [{"parts": [{"text": prompt}]}]})
        r.raise_for_status()
        return r.json()["candidates"][0]["content"]["parts"][0]["text"]


async def complete(prompt: str, *, sensitive: bool, complexity: str = "simple") -> tuple[str, str]:
    """Returns (text, model_used). sensitive=True never leaves our infrastructure."""
    if sensitive:
        return await _ollama(prompt), "ollama"
    safe = deidentify(prompt)
    if complexity == "complex" and settings.gemini_api_key:
        return await _gemini(safe), "gemini"
    if settings.groq_api_key:
        return await _groq(safe), "groq"
    return await _ollama(prompt), "ollama"


async def tavily_search(query: str) -> list[dict]:
    if not settings.tavily_api_key:
        return []
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post("https://api.tavily.com/search",
                         json={"api_key": settings.tavily_api_key, "query": query, "max_results": 3})
        r.raise_for_status()
        return [{"title": x["title"], "url": x["url"], "content": x["content"][:400]} for x in r.json()["results"]]
