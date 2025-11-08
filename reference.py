from __future__ import annotations
import json
import os
from typing import List, Optional, Dict, Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

# --- Optional: load environment from .env ---
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

# --- LLM client (OpenAI-compatible) ---
try:
    from openai import OpenAI
    _HAS_OPENAI = True
except Exception:
    OpenAI = None
    _HAS_OPENAI = False

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
MODEL_NAME = os.getenv("MODEL_NAME", "gpt-4o-mini")

# --- Load services from YAML ---
import yaml
with open("services.yaml", "r", encoding="utf-8") as f:
    SERVICES = yaml.safe_load(f)

CATEGORIES: List[str] = list(SERVICES.keys())

# Build keywords from YAML
tmp_keywords = {}
for name, data in SERVICES.items():
    kws = data.get("keywords", [])
    if isinstance(kws, list):
        tmp_keywords[name] = [k.lower() for k in kws]
    else:
        tmp_keywords[name] = []
KEYWORDS = tmp_keywords

# --- Request/Response models ---
class ClassifyRequest(BaseModel):
    text: str = Field(...)
    top_k: int = Field(3, ge=1, le=len(CATEGORIES))

class Option(BaseModel):
    category: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    reasoning: Optional[str] = None
    description: Optional[str] = None

class ClassifyResponse(BaseModel):
    best: Option
    alternatives: List[Option]
    used_fallback: bool = False

# --- Prompt template ---
SYSTEM_PROMPT = f"""
You are a routing assistant for a Center for Independent Living (CIL).
Your job: classify the user's message into one or more of these programs:
{json.dumps(CATEGORIES, ensure_ascii=False)}

Return STRICT JSON with this schema (no extra text):
{{
  "best": {{"category": string, "confidence": number, "reasoning": string}},
  "alternatives": [{{"category": string, "confidence": number, "reasoning": string}}]
}}

Definitions:
{json.dumps(SERVICES, ensure_ascii=False, indent=2)}
"""

USER_TEMPLATE = (
    "Classify the following message and ONLY output the specified JSON.\n\n"
    "Message:\n{text}\n"
    "Top-K: {top_k}"
)

# --- Keyword fallback ---
def _keyword_guess(text: str, top_k: int) -> ClassifyResponse:
    t = text.lower()
    scores = []
    for cat, kws in KEYWORDS.items():
        score = sum(1 for w in kws if w in t)
        scores.append((cat, score))
    scores.sort(key=lambda x: x[1], reverse=True)

    if not scores or scores[0][1] == 0:
        best_cat = "Independent Living Peer Support"
        best = Option(
            category=best_cat,
            confidence=0.35,
            reasoning="No strong match; defaulting to peer support.",
            description=SERVICES[best_cat].get("description")
        )
        alts = [c for c, _ in scores[:top_k] if c != best_cat]
        alt_opts = [
            Option(
                category=a,
                confidence=0.2,
                reasoning="Weak match",
                description=SERVICES[a].get("description")
            ) for a in alts
        ]
        return ClassifyResponse(best=best, alternatives=alt_opts, used_fallback=True)

    best_cat = scores[0][0]
    alts = [c for c, _ in scores[1:top_k]]
    best = Option(
        category=best_cat,
        confidence=0.6,
        reasoning="Keyword match",
        description=SERVICES[best_cat].get("description")
    )
    alt_opts = [
        Option(
            category=a,
            confidence=0.4,
            reasoning="Partial keyword match",
            description=SERVICES[a].get("description")
        ) for a in alts
    ]
    return ClassifyResponse(best=best, alternatives=alt_opts, used_fallback=True)

# --- LLM call ---
def _call_llm(text: str, top_k: int) -> Dict[str, Any]:
    if not (_HAS_OPENAI and OPENAI_API_KEY):
        raise RuntimeError("LLM client not configured")

    client = OpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": USER_TEMPLATE.format(text=text, top_k=top_k)},
    ]
    resp = client.chat.completions.create(
        model=MODEL_NAME,
        messages=messages,
        temperature=0.0,
        max_tokens=300,
    )
    raw = resp.choices[0].message.content or "{}"
    return json.loads(raw)

# --- classify orchestrator ---
def classify(text: str, top_k: int = 3) -> ClassifyResponse:
    try:
        data = _call_llm(text, top_k)
        best = data.get("best", {})
        alts = data.get("alternatives", [])

        best_opt = Option(
            category=best.get("category", CATEGORIES[0]),
            confidence=float(best.get("confidence", 0.5)),
            reasoning=best.get("reasoning"),
            description=SERVICES.get(best.get("category", ""), {}).get("description")
        )
        alt_opts = [
            Option(
                category=o.get("category", CATEGORIES[0]),
                confidence=float(o.get("confidence", 0.3)),
                reasoning=o.get("reasoning"),
                description=SERVICES.get(o.get("category", ""), {}).get("description")
            ) for o in alts[:top_k-1]
        ]
        return ClassifyResponse(best=best_opt, alternatives=alt_opts, used_fallback=False)
    except Exception:
        return _keyword_guess(text, top_k)

# --- FastAPI app ---
app = FastAPI()

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/classify", response_model=ClassifyResponse)
def classify_endpoint(body: ClassifyRequest):
    if not body.text.strip():
        raise HTTPException(status_code=400, detail="Empty text")
    return classify(body.text.strip(), top_k=body.top_k)

class BatchRequest(BaseModel):
    items: List[str]
    top_k: int = 3

class BatchResponse(BaseModel):
    results: List[ClassifyResponse]

@app.post("/classify:batch", response_model=BatchResponse)
def classify_batch(body: BatchRequest):
    return BatchResponse(results=[classify(t, body.top_k) for t in body.items])