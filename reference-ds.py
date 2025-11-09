from __future__ import annotations
import json
import os
from typing import List, Optional, Dict, Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from fastapi.middleware.cors import CORSMiddleware

import yaml

# DeepSeek (OpenAI Compatible Client)
from openai import OpenAI

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-chat"   


# ======================================================
#  LOAD MULTI-ORGANIZATION CONFIG
# ======================================================
CONFIG_DIR = "orgs"

ORG_SERVICES: Dict[str, Dict[str, Any]] = {}
ORG_KEYWORDS: Dict[str, Dict[str, List[str]]] = {}

for filename in os.listdir(CONFIG_DIR):
    if filename.endswith(".yaml"):
        org = filename.replace(".yaml", "")
        with open(os.path.join(CONFIG_DIR, filename), "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        ORG_SERVICES[org] = data

        tmp = {}
        for cat, info in data.items():
            kws = info.get("keywords", [])
            tmp[cat] = [k.lower() for k in kws] if isinstance(kws, list) else []
        ORG_KEYWORDS[org] = tmp

if "default" not in ORG_SERVICES:
    first = list(ORG_SERVICES.keys())[0]
    ORG_SERVICES["default"] = ORG_SERVICES[first]
    ORG_KEYWORDS["default"] = ORG_KEYWORDS[first]


# ======================================================
#   Models
# ======================================================
class ClassifyRequest(BaseModel):
    text: str = Field(...)
    top_k: int = 2
    organization: str = "default"

class Option(BaseModel):
    category: str
    confidence: float
    reasoning: Optional[str] = None
    description: Optional[str] = None

class ClassifyResponse(BaseModel):
    best: Option
    alternatives: List[Option]
    used_fallback: bool = False


# ======================================================
#   Keyword fallback
# ======================================================
def _keyword_guess(text: str, top_k: int, services, keywords) -> ClassifyResponse:
    t = text.lower()
    scores = []
    for cat, kws in keywords.items():
        score = sum(1 for w in kws if w in t)
        scores.append((cat, score))
    scores.sort(key=lambda x: x[1], reverse=True)

    if not scores or scores[0][1] == 0:
        best_cat = list(services.keys())[0]
        best = Option(category=best_cat, confidence=0.35, reasoning="Weak match",
                      description=services[best_cat].get("description"))
        return ClassifyResponse(best=best, alternatives=[], used_fallback=True)

    best_cat = scores[0][0]
    alts = scores[1:top_k]
    best = Option(category=best_cat, confidence=0.6, reasoning="Keyword match",
                  description=services[best_cat].get("description"))
    alt_opts = [
        Option(category=a, confidence=0.4, reasoning="Partial keyword match",
               description=services[a].get("description")) for a, _ in alts
    ]

    return ClassifyResponse(best=best, alternatives=alt_opts, used_fallback=True)


# ======================================================
#   DeepSeek Non-Streaming Classification
# ======================================================
def _call_llm(text: str, top_k: int, services, categories):
    if not DEEPSEEK_API_KEY:
        raise RuntimeError("DeepSeek API key not configured")

    client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)

    system_prompt = f"""
You are a routing assistant for a Center for Independent Living (CIL).
Classify into one of these program categories:
{json.dumps(categories, ensure_ascii=False)}

Return STRICT JSON ONLY:
{{
  "best": {{"category": string, "confidence": number, "reasoning": string}},
  "alternatives": [{{"category": string, "confidence": number, "reasoning": string}}]
}}

Program definitions:
{json.dumps(services, ensure_ascii=False, indent=2)}
"""

    user_prompt = f"Message:\n{text}\nTop-K: {top_k}"

    resp = client.chat.completions.create(
        model=DEEPSEEK_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0,
        max_tokens=300,
    )

    raw = resp.choices[0].message.content or "{}"
    return json.loads(raw)


# ======================================================
#   Streaming Chat for Conversation
# ======================================================
def stream_chat(messages, organization="default"):
    services = ORG_SERVICES.get(organization, ORG_SERVICES["default"])

    system_prompt = f"""
You are a friendly intake assistant at a Center for Independent Living.
Your job is to warmly ask questions, understand needs, and suggest appropriate services.
Keep responses short, supportive, and conversational.

Available services:
{json.dumps(services, ensure_ascii=False, indent=2)}
"""

    client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)

    resp = client.chat.completions.create(
        model=DEEPSEEK_MODEL,
        messages=[{"role": "system", "content": system_prompt}] + messages,
        stream=True,
        temperature=0.3,
        max_tokens=300,
    )

    for chunk in resp:
        delta = chunk.choices[0].delta
        content = getattr(delta, "content", None)
        if content:
            yield content



# ======================================================
#   Classify Orchestrator
# ======================================================
def classify(text: str, top_k: int = 2, organization: str = "default") -> ClassifyResponse:
    services = ORG_SERVICES.get(organization, ORG_SERVICES["default"])
    keywords = ORG_KEYWORDS.get(organization, ORG_KEYWORDS["default"])
    categories = list(services.keys())

    try:
        data = _call_llm(text, top_k, services, categories)
        best = data.get("best", {})
        alts = data.get("alternatives", [])

        best_opt = Option(
            category=best.get("category", categories[0]),
            confidence=float(best.get("confidence", 0.5)),
            reasoning=best.get("reasoning"),
            description=services.get(best.get("category", ""), {}).get("description")
        )

        alt_opts = [
            Option(
                category=o.get("category"),
                confidence=float(o.get("confidence", 0.3)),
                reasoning=o.get("reasoning"),
                description=services[o.get("category", "")].get("description")
            ) for o in alts[:top_k-1]
        ]

        return ClassifyResponse(best=best_opt, alternatives=alt_opts, used_fallback=False)

    except Exception:
        return _keyword_guess(text, top_k, services, keywords)


# ======================================================
#   FastAPI
# ======================================================
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/classify", response_model=ClassifyResponse)
def classify_endpoint(body: ClassifyRequest):
    if not body.text.strip():
        raise HTTPException(status_code=400, detail="Empty text")
    return classify(body.text.strip(), top_k=body.top_k, organization=body.organization)

@app.post("/chat/stream")
def chat_stream(body: Dict[str, Any]):
    messages = body.get("messages", [])
    organization = body.get("organization", "default")

    if not messages:
        raise HTTPException(status_code=400, detail="messages required")

    return StreamingResponse(
        stream_chat(messages, organization),
        media_type="text/plain"
    )
