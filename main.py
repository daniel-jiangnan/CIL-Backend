from __future__ import annotations
import json
import os
from typing import List, Optional, Dict, Any
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from fastapi.middleware.cors import CORSMiddleware

import yaml

# DeepSeek (OpenAI Compatible Client)
from openai import OpenAI

# Appointment Management
from consumer_book_appointment import (
    get_appointments_by_date,
    get_matched_appointments,
)

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


# === AI Classification Models ===
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


# === Appointment Management Models ===
class SearchByDateRequest(BaseModel):
    """Request model for searching appointments by date"""

    target_date: str
    service_account_file: str = "service_accounts.txt"
    calendar_ids_file: str = "calendars.json"


class SearchByCustomerRequest(BaseModel):
    """Request model for searching appointments by customer details"""

    first_name: str
    last_name: str
    appointment_date: str
    service: str
    service_account_file: str = "service_accounts.txt"
    calendar_ids_file: str = "calendars.json"


class AppointmentResponse(BaseModel):
    """Response model for appointment details"""

    event_id: str
    calendar_id: str
    event_summary: str
    attendee_email: Optional[str]
    attendee_name: str
    datetime: str
    date: str
    time: str
    service_account: str


class SearchByDateResponse(BaseModel):
    """Response model for date-based search"""

    success: bool
    message: str
    date: str
    count: int
    appointments: List[AppointmentResponse]


class SearchByCustomerResponse(BaseModel):
    """Response model for customer-based search"""

    success: bool
    message: str
    customer_name: str
    search_date: str
    service: str
    count: int
    appointments: List[AppointmentResponse]


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
        best = Option(
            category=best_cat,
            confidence=0.35,
            reasoning="Weak match",
            description=services[best_cat].get("description"),
        )
        return ClassifyResponse(best=best, alternatives=[], used_fallback=True)

    best_cat = scores[0][0]
    alts = scores[1:top_k]
    best = Option(
        category=best_cat,
        confidence=0.6,
        reasoning="Keyword match",
        description=services[best_cat].get("description"),
    )
    alt_opts = [
        Option(
            category=a,
            confidence=0.4,
            reasoning="Partial keyword match",
            description=services[a].get("description"),
        )
        for a, _ in alts
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
            {"role": "user", "content": user_prompt},
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
def classify(
    text: str, top_k: int = 2, organization: str = "default"
) -> ClassifyResponse:
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
            description=services.get(best.get("category", ""), {}).get("description"),
        )

        alt_opts = [
            Option(
                category=o.get("category"),
                confidence=float(o.get("confidence", 0.3)),
                reasoning=o.get("reasoning"),
                description=services[o.get("category", "")].get("description"),
            )
            for o in alts[: top_k - 1]
        ]

        return ClassifyResponse(
            best=best_opt, alternatives=alt_opts, used_fallback=False
        )

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


# ======================================================
#   Appointment Management Endpoints
# ======================================================
LOCAL_TZ = ZoneInfo("America/Los_Angeles")


@app.post(
    "/api/appointments/by-date",
    response_model=SearchByDateResponse,
    summary="Search appointments by date",
    description="Search all appointments for a specific date (Admin view)",
)
async def search_appointments_by_date(request: SearchByDateRequest):
    """Search all appointments for a specific date (Admin view)"""
    try:
        # Parse the date
        try:
            if "T" in request.target_date:
                target_date = datetime.fromisoformat(request.target_date).replace(
                    tzinfo=LOCAL_TZ
                )
            else:
                target_date = datetime.strptime(
                    request.target_date, "%Y-%m-%d"
                ).replace(tzinfo=LOCAL_TZ)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="Invalid date format. Use 'YYYY-MM-DD' or 'YYYY-MM-DDTHH:MM:SS'",
            )

        # Get appointments
        appointments = get_appointments_by_date(
            target_date=target_date,
            service_account_file=request.service_account_file,
            calendar_ids_file=request.calendar_ids_file,
        )

        # Format response
        formatted_appointments = [
            AppointmentResponse(
                event_id=appt["event_id"],
                calendar_id=appt["calendar_id"],
                event_summary=appt["event_summary"],
                attendee_email=appt["attendee_email"],
                attendee_name=appt["attendee_name"],
                datetime=appt["datetime"].isoformat(),
                date=appt["date"].isoformat(),
                time=appt["time"].isoformat(),
                service_account=appt["service_account"],
            )
            for appt in appointments
        ]

        return SearchByDateResponse(
            success=True,
            message=f"Found {len(appointments)} appointment(s) on {request.target_date}",
            date=request.target_date,
            count=len(appointments),
            appointments=formatted_appointments,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error searching appointments: {str(e)}",
        )


@app.post(
    "/api/appointments/by-customer",
    response_model=SearchByCustomerResponse,
    summary="Search appointments by customer details",
    description="Search appointments for a specific customer by their information",
)
async def search_appointments_by_customer(request: SearchByCustomerRequest):
    """Search appointments for a specific customer"""
    try:
        # Parse the date
        try:
            if "T" in request.appointment_date:
                appointment_date = datetime.fromisoformat(
                    request.appointment_date
                ).replace(tzinfo=LOCAL_TZ)
            else:
                appointment_date = datetime.strptime(
                    request.appointment_date, "%Y-%m-%d"
                ).replace(tzinfo=LOCAL_TZ)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="Invalid date format. Use 'YYYY-MM-DD' or 'YYYY-MM-DDTHH:MM:SS'",
            )

        # Get matched appointments
        appointments = get_matched_appointments(
            first_name=request.first_name,
            last_name=request.last_name,
            start_time=appointment_date,
            service=request.service,
            service_account_file=request.service_account_file,
            calendar_ids_file=request.calendar_ids_file,
        )

        # Format response
        formatted_appointments = [
            AppointmentResponse(
                event_id=appt["event_id"],
                calendar_id=appt["calendar_id"],
                event_summary=appt["event_summary"],
                attendee_email=appt["attendee_email"],
                attendee_name=appt["attendee_name"],
                datetime=appt["datetime"].isoformat(),
                date=appt["date"].isoformat(),
                time=appt["time"].isoformat(),
                service_account=appt["service_account"],
            )
            for appt in appointments
        ]

        return SearchByCustomerResponse(
            success=True,
            message=f"Found {len(appointments)} appointment(s) for {request.first_name} {request.last_name}",
            customer_name=f"{request.first_name} {request.last_name}",
            search_date=request.appointment_date,
            service=request.service,
            count=len(appointments),
            appointments=formatted_appointments,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error searching appointments: {str(e)}",
        )


# ======================================================
#   AI Classification Endpoints
# ======================================================


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
        stream_chat(messages, organization), media_type="text/plain"
    )
