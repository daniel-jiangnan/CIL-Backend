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
#  LOAD MULTI-ORGANIZATION CONFIG  (NEW YAML SCHEMA)
# ======================================================

CONFIG_DIR = "orgs"

# every org -> { program_name -> { description, keywords, services:{ service_key -> {...}} } }
ORG_PROGRAMS: Dict[str, Dict[str, Any]] = {}
# every org -> { program_name -> [keywords...] }，
ORG_KEYWORDS: Dict[str, Dict[str, List[str]]] = {}


def _ensure_list(x):
    if not x:
        return []
    if isinstance(x, list):
        return x
    return [x]


def _load_org_file(path: str) -> Dict[str, Any]:
    """load yaml as programs_by_name structure"""
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    programs = raw.get("programs", [])
    if not isinstance(programs, list):
        programs = []

    programs_by_name: Dict[str, Any] = {}
    program_keywords_by_name: Dict[str, List[str]] = {}

    for p in programs:
        pname = (p.get("name") or "").strip()
        if not pname:
            # skip NA program
            continue

        pdesc = p.get("description", "") or ""
        pkw = _ensure_list(p.get("keywords"))

        # services -> dict keyed by service.key
        services_list = _ensure_list(p.get("services"))
        services_by_key: Dict[str, Any] = {}
        collected_keywords = [k.lower() for k in pkw if isinstance(k, str)]

        for s in services_list:
            if not isinstance(s, dict):
                continue
            skey = (s.get("key") or "").strip()
            if not skey:
                continue

            sdesc = s.get("description", "") or ""
            sphone = s.get("phone", "") or ""
            skw = [k.lower() for k in _ensure_list(s.get("keywords")) if isinstance(k, str)]
            scontacts = _ensure_list(s.get("contacts"))

            #  service key as key
            # e.g. "Whill Sales" -> ["whill", "sales"]
            skey_terms = [t.strip().lower() for t in skey.replace("/", " ").replace("&", " ").split() if t.strip()]
            all_s_keywords = list({*skw, *skey_terms})

            services_by_key[skey] = {
                "phone": sphone,
                "description": sdesc,
                "keywords": all_s_keywords,
                "contacts": scontacts,
            }

            collected_keywords.extend(all_s_keywords)

        programs_by_name[pname] = {
            "description": pdesc,
            "keywords": [k.lower() for k in collected_keywords],  
            "services": services_by_key,
        }

        program_keywords_by_name[pname] = [k.lower() for k in collected_keywords]

    return {
        "programs_by_name": programs_by_name,
        "program_keywords_by_name": program_keywords_by_name,
    }


# scan org path
for filename in os.listdir(CONFIG_DIR):
    if not filename.endswith(".yaml"):
        continue
    org = filename.replace(".yaml", "")
    loaded = _load_org_file(os.path.join(CONFIG_DIR, filename))
    ORG_PROGRAMS[org] = loaded["programs_by_name"]
    ORG_KEYWORDS[org] = loaded["program_keywords_by_name"]

#  default
if "default" not in ORG_PROGRAMS:
    if ORG_PROGRAMS:
        first = list(ORG_PROGRAMS.keys())[0]
        ORG_PROGRAMS["default"] = ORG_PROGRAMS[first]
        ORG_KEYWORDS["default"] = ORG_KEYWORDS[first]
    else:
        ORG_PROGRAMS["default"] = {}
        ORG_KEYWORDS["default"] = {}

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
def _keyword_guess(text: str, top_k: int, programs: Dict[str, Any], program_keywords: Dict[str, List[str]]) -> ClassifyResponse:
    t = (text or "").lower()
    scores: List[tuple[str, int]] = []
    for pname, kwlist in program_keywords.items():
        score = sum(1 for w in kwlist if w and w in t)
        scores.append((pname, score))
    scores.sort(key=lambda x: x[1], reverse=True)

    if not scores or scores[0][1] == 0:
        # if not mathch, return first program as weak match
        if programs:
            best_cat = list(programs.keys())[0]
            best = Option(
                category=best_cat,
                confidence=0.35,
                reasoning="Weak match",
                description=programs[best_cat].get("description", ""),
            )
        else:
            best = Option(category="Unknown", confidence=0.0, reasoning="No programs loaded", description=None)
        return ClassifyResponse(best=best, alternatives=[], used_fallback=True)

    best_cat = scores[0][0]
    alts = [name for name, _ in scores[1:top_k]]

    best = Option(
        category=best_cat,
        confidence=0.6,
        reasoning="Keyword match",
        description=programs.get(best_cat, {}).get("description", ""),
    )
    alt_opts = [
        Option(
            category=a,
            confidence=0.4,
            reasoning="Partial keyword match",
            description=programs.get(a, {}).get("description", ""),
        )
        for a in alts
        if a in programs
    ]

    return ClassifyResponse(best=best, alternatives=alt_opts, used_fallback=True)

# ======================================================
#   DeepSeek Non-Streaming Classification
#   （categories = program name；services）
# ======================================================
def _call_llm(text: str, top_k: int, programs: Dict[str, Any], categories: List[str]):
    if not DEEPSEEK_API_KEY:
        raise RuntimeError("DeepSeek API key not configured")

    client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)


    compact_programs = {}
    for pname, pdata in programs.items():
        compact_programs[pname] = {
            "description": pdata.get("description", ""),
            "services": [
                {
                    "key": skey,
                    "phone": sdata.get("phone", ""),
                    "has_contacts": bool(sdata.get("contacts")),
                    "has_keywords": bool(sdata.get("keywords")),
                }
                for skey, sdata in (pdata.get("services") or {}).items()
            ],
        }

    system_prompt = f"""
You are a routing assistant for a Center for Independent Living (CIL).
Classify the user's message into ONE of these program categories (top-level programs):
{json.dumps(categories, ensure_ascii=False)}

Return STRICT JSON ONLY:
{{
  "best": {{"category": string, "confidence": number, "reasoning": string}},
  "alternatives": [{{"category": string, "confidence": number, "reasoning": string}}]
}}

Program definitions (each program may contain multiple services):
{json.dumps(compact_programs, ensure_ascii=False, indent=2)}
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
def _programs_for_prompt(programs: Dict[str, Any], max_services_each: int = 4) -> str:
    lines = []
    for pname, pdata in programs.items():
        desc = (pdata.get("description") or "").strip()
        lines.append(f"- Program: {pname} — {desc[:200]}{'...' if len(desc) > 200 else ''}")

        sdict = pdata.get("services") or {}
        if not sdict:
            continue

        cnt = 0
        for skey, sdata in sdict.items():
            phone = sdata.get("phone") or ""
            contacts = sdata.get("contacts") or []

            if contacts:
                # 展示最多前2个联系人
                c_lines = []
                for c in contacts[:2]:
                    name = c.get("name","")
                    email = c.get("email","")
                    c_lines.append(f"{name}{f' <{email}>' if email else ''}")
                contacts_str = "; ".join(c_lines)
            else:
                contacts_str = ""

            line = f"    • Service: {skey}"
            if phone:
                line += f" (Phone: {phone})"
            if contacts_str:
                line += f" — Contacts: {contacts_str}"

            lines.append(line)

            cnt += 1
            if cnt >= max_services_each:
                lines.append("    • ...")
                break

    return "\n".join(lines)



def stream_chat(messages, organization="default"):
    org = organization if organization in ORG_PROGRAMS else "default"
    programs = ORG_PROGRAMS.get(org, {})

    system_prompt = f"""
    You are a warm and helpful intake navigator at a Center for Independent Living.

    Your job:
    1. Understand the user's need.
    2. Identify the MOST relevant program.
    3. IF POSSIBLE, recommend a SPECIFIC SERVICE under that program.
    4. When recommending a service, ALWAYS include any available:
    - Contact person name(s)
    - Email(s)
    - Phone number(s)

    Rules:
    - Keep responses short (2–4 sentences).
    - If the exact service is unclear, ask **one clarifying question** before recommending.
    - If a service has no direct contact, then share:
    • Another service under the same program that DOES have a contact
    • OR the program’s main phone number
    - Do NOT output JSON. Respond conversationally and kindly.

    Available programs & services:
    {_programs_for_prompt(programs)}
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
    org = organization if organization in ORG_PROGRAMS else "default"
    programs = ORG_PROGRAMS.get(org, {})
    program_keywords = ORG_KEYWORDS.get(org, {})
    categories = list(programs.keys())

    if not categories:
        # fall back no programs
        best = Option(category="Unknown", confidence=0.0, reasoning="No programs loaded", description=None)
        return ClassifyResponse(best=best, alternatives=[], used_fallback=True)

    try:
        data = _call_llm(text, top_k, programs, categories)
        best = data.get("best", {})
        alts = _ensure_list(data.get("alternatives"))

        best_cat = best.get("category", categories[0])
        best_opt = Option(
            category=best_cat,
            confidence=float(best.get("confidence", 0.5)),
            reasoning=best.get("reasoning"),
            description=programs.get(best_cat, {}).get("description", ""),
        )

        alt_opts: List[Option] = []
        for o in alts[: max(0, top_k - 1)]:
            oc = o.get("category")
            if not oc or oc not in programs:
                continue
            alt_opts.append(
                Option(
                    category=oc,
                    confidence=float(o.get("confidence", 0.3)),
                    reasoning=o.get("reasoning"),
                    description=programs.get(oc, {}).get("description", ""),
                )
            )

        return ClassifyResponse(best=best_opt, alternatives=alt_opts, used_fallback=False)

    except Exception:
        # fall back to keyword matching
        return _keyword_guess(text, top_k, programs, program_keywords)

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
