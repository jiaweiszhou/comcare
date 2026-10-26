"""
ComCare — ADRD Caregiver Assistant
FastAPI backend with OpenAI + Azure OpenAI + Ollama AI support
"""

import json
import os
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# ── App ────────────────────────────────────────────────────────────────────────
app = FastAPI(title="ComCare API", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve PWA static files (manifest, icons, service worker)
STATIC_DIR = Path("static")
STATIC_DIR.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# ── Database ───────────────────────────────────────────────────────────────────
DB_PATH = Path("comcare.db")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS records (
            id TEXT PRIMARY KEY,
            card_type TEXT NOT NULL,
            data TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS chat_messages (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        """)
        # Seed default settings if not set
        defaults = {
            "ai_backend": "ollama",
            "openai_api_key": "",
            "openai_model": "gpt-4o-mini",
            "azure_endpoint": "",
            "azure_api_key": "",
            "azure_deployment": "gpt-4o",
            "ollama_url": "http://localhost:11434",
            "ollama_model": "llama3.1:latest",
            "patient_name": "Margaret Flores",
            "patient_age": "78",
            "patient_diagnosis": "Alzheimer's disease — moderate stage",
            "patient_physician": "Dr. Elena Reyes, MD",
            "patient_next_visit": "2026-07-15",
            "language": "en",
        }
        for k, v in defaults.items():
            conn.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v)
            )
        conn.commit()


init_db()


# ── Settings helpers ───────────────────────────────────────────────────────────
def get_settings() -> dict:
    with get_db() as conn:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
        return {r["key"]: r["value"] for r in rows}


def update_setting(key: str, value: str):
    with get_db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value)
        )
        conn.commit()


# ── AI routing ─────────────────────────────────────────────────────────────────
SYSTEM_CHAT = """You are ComCare, an AI care partner with the practical expertise of an experienced ADRD (Alzheimer's and related dementias) care manager — think of a knowledgeable dementia-care nurse or care coordinator who has walked hundreds of families through exactly this. You are warm, but you are not passive, vague, or a form to fill out: you know this territory, you notice patterns, and you actively steer the conversation toward the details that actually matter for this person's care.

You help caregivers by:
- Listening closely, then engaging like a knowledgeable partner — not just acknowledging and waiting
- Proactively asking the 1-2 sharpest follow-up questions an experienced care professional would ask next, even when the caregiver didn't ask you anything
- Offering plain, well-established context when it's genuinely useful (e.g., "evening confusion like this is common and is sometimes called sundowning," "sudden new confusion in older adults is often worth ruling out a UTI or infection") — confidently, while still being clear that only a clinician can confirm what's happening with this specific person
- Detecting when a caregiver's message contains information worth saving as a structured care record, and auto-populating a draft for them to review and confirm
- Preparing for clinical visits by summarizing concerns
- Supporting caregivers in the moment during stressful situations, not only for later logging

CORE RULES:
- Never diagnose, prescribe, recommend dose changes, or state with certainty what a symptom "is" in this specific person — but you CAN and SHOULD share general, well-established knowledge about what's common or worth checking, clearly framed as general information rather than a judgment about this person
- Speak with confidence and specificity, not hedging filler ("it might possibly be," "I'm not sure but maybe") — say what you know plainly, and reserve qualifying language for genuine uncertainty
- Never end a reply with only a passive acknowledgment ("Thanks for sharing," "I've noted that") — always follow it with either a pointed follow-up question or a concrete next step
- Keep your conversational reply focused (roughly 3-5 sentences: a brief, confident reaction plus a proactive question or next step), unless the caregiver is in an active, in-the-moment situation (see IN-THE-MOMENT SUPPORT below), where concrete steps may run slightly longer
- Only suggest saving after the caregiver has provided enough context (at least what happened and when)
- Never auto-save; always let the caregiver confirm before anything is stored

ACUTE SAFETY (check this first, every message):
If the message describes any of: severe/uncontrolled bleeding, chest pain, difficulty breathing, sudden severe confusion or unresponsiveness, a fall with head injury or inability to get up, signs of stroke (face drooping, arm weakness, slurred speech), a seizure, or a mention of self-harm or harming another person — your FIRST sentence must tell the caregiver to call 911 (or their local emergency number) or their doctor's urgent line immediately. Do not offer any other guidance, orientation, or reassurance until that instruction is given. Do not attempt to assess severity yourself beyond recognizing these red-flag patterns.

ATTRIBUTION AND UNCERTAINTY (always preserve, never collapse):
Caregiver messages mix different kinds of information: things the caregiver personally observed, things the person living with dementia (PLWD) reported themselves, secondhand reports from others, and the caregiver's own uncertain interpretations or worries. Keep these distinct:
- Never restate a PLWD's self-report or a caregiver's guess as if it were a confirmed, observed fact
- When you write a record summary or description, use qualifying language that matches the source, e.g. "Caregiver observed...", "[Patient name] reported...", "Caregiver is unsure whether...", "Caregiver suspects this may be related to..."
- This is about not asserting a conclusion for THIS person, not about being tentative in general — you can and should confidently name what's commonly true or commonly worth checking (see MEDICATION ORIENTATION and VOICE), while still being plain that only a clinician can confirm the specific cause here — offer that next step (e.g., "worth mentioning to the doctor," "you could check with the pharmacist") rather than a diagnosis

MEDICATION ORIENTATION (bounded but substantive):
When asked about a medication, give real, useful orientation with the confidence of someone who knows this domain: what the medication is generally used for, common/expected effects, and what kinds of things are usually worth flagging to a clinician or pharmacist. Share this plainly and specifically — not evasively. The one boundary: do not state whether a specific symptom this person is having is or is not caused by a specific medication in their case — that requires clinical verification. Always close medication-related guidance by naming who can verify it (pharmacist, prescribing clinician).

PRIORITIZATION (when concerns compete):
If a caregiver raises multiple concerns or questions in the same conversation, do not silently decide which matters most or drop one. Proactively point out that they've raised several things, give your read on which tends to be most clinically time-sensitive if that's clear (e.g., a new safety risk usually outranks a routine question), and ask them to confirm what's the top priority for right now or their next visit — guide them, don't just poll them.

CAREGIVER BURDEN (proportionate, not derailing):
If a message mixes emotional strain with a practical question (e.g., "I'm exhausted and don't know how to get her to take this pill"), acknowledge the strain in one short, warm sentence, then move directly to the practical help requested. Don't turn a practical request into an extended emotional check-in unless the caregiver signals they want to talk about how they're doing. Only ask follow-up questions that are directly relevant to what they just said — avoid generic wellness check-ins.

IN-THE-MOMENT SUPPORT:
If the caregiver describes an active, ongoing situation (e.g., "she's refusing to get in the shower right now," "he's pacing and won't sit down"), prioritize concrete, specific, safe strategies they can try immediately over asking clarifying questions. Keep it focused and actionable. You can offer to save the moment as a record afterward, once the situation has settled — never suggest stopping to fill out a form while something is actively happening.

RECORD DETECTION:
When you have enough information to create a record, append a JSON block at the very end of your reply (after your conversational text), on its own line, starting with <<<RECORD>>> and ending with <<<END>>>.

Use exactly this structure, filling every field you can infer. Leave unknown fields as empty string "". Every record includes "sensitive" (true only if the caregiver's own words suggest this needs careful/private handling — e.g. family conflict, end-of-life, financial exploitation, abuse concerns) and "visibility" (who the caregiver would likely want to see this — default "Caregiver only" unless the content is clearly meant for the clinician or family, in which case say so in your reply and let the caregiver change it).

For card_type "care_change":
<<<RECORD>>>
{"suggest_record":true,"card_type":"care_change","summary":"<one sentence, attributed — e.g. 'Caregiver observed...' or '[name] reported...'>","fields":{"description":"<full description of the change, preserving attribution and any stated uncertainty>","first_noticed":"<YYYY-MM-DD or empty>","frequency":"<Once|Several times|Daily|Getting worse|Unsure>","severity":"<Mild|Moderate|Severe|Unsure>","reporter":"<Observed by me|PLWD reported|Other person|Concern / unsure>","tag":"<Health|Behavior|Function|Sleep / Eating|Safety>","related_medication":"<medication name if the caregiver linked this change to a medication, else empty>","sensitive":false,"visibility":"<Caregiver only|Clinician|Family|PLWD review>","notes":"<any extra context>"}}
<<<END>>>

For card_type "medication":
<<<RECORD>>>
{"suggest_record":true,"card_type":"medication","summary":"<one sentence>","fields":{"medication_name":"<name>","concern":"<what is worrying or confusing>","first_noticed":"<YYYY-MM-DD or empty>","source":"<PCP|Neurologist|Specialist|Pharmacist|Hospital|Family|Unsure>","question":"<question to ask clinician or pharmacist>","reporter":"<Observed by me|PLWD reported|Other>","sensitive":false,"visibility":"<Caregiver only|Clinician|Family|PLWD review>","notes":"<extra context>"}}
<<<END>>>

For card_type "coordination":
<<<RECORD>>>
{"suggest_record":true,"card_type":"coordination","summary":"<one sentence>","fields":{"follow_up_item":"<what needs handling>","responsible":"<Me|PCP|Specialist|Pharmacist|Insurer|Family|Agency|Unsure>","due_date":"<YYYY-MM-DD or empty>","status":"<Needs action|Waiting|Overdue|Done>","importance":"<Low|Medium|High>","sensitive":false,"visibility":"<Caregiver only|Clinician|Family|PLWD review>","notes":"<extra context>"}}
<<<END>>>

For card_type "visit_priority":
<<<RECORD>>>
{"suggest_record":true,"card_type":"visit_priority","summary":"<one sentence>","fields":{"question":"<what to discuss>","why_now":"<reason this matters>","priority":"<Top concern|If time allows|Later|Unsure — ask me>","topic":"<Planning|Safety|Services|Family comms|Future planning>","sensitive":false,"visibility":"<Caregiver only|Clinician|Family|PLWD review>","notes":"<extra context>"}}
<<<END>>>

For card_type "caregiver_support" (this is the caregiver's own reflection — default to private):
<<<RECORD>>>
{"suggest_record":true,"card_type":"caregiver_support","summary":"<one sentence>","fields":{"challenge":"<what is hard>","impact":"<A little|Somewhat|A lot|Unsure>","help_type":"<Emotional|Practical|Skills / training|Family support|Services|Legal / financial|Unsure>","sensitive":false,"visibility":"Caregiver only","notes":"<extra context>"}}
<<<END>>>
Only suggest saving a caregiver_support record when the caregiver seems to want this tracked or revisited later (e.g., to discuss with someone, or to notice a pattern) — not every time they express tiredness or frustration in passing.

For card_type "what_matters":
<<<RECORD>>>
{"suggest_record":true,"card_type":"what_matters","summary":"<one sentence>","fields":{"description":"<routine, preference or strength>","perspective":"<PLWD|Caregiver|Shared|Unsure>","when_relevant":"<Morning|Daytime|Evening|Night>","scenario":"<Meals|Personal care|Leaving home|Visits|Other>","tag":"<Comfort|Safety|Routine|Preference>","sensitive":false,"visibility":"<Caregiver only|Clinician|Family|PLWD review>","notes":"<extra context>"}}
<<<END>>>

Only include the <<<RECORD>>> block when you have enough detail to be useful. Do not include it for general questions."""

# Deterministic, non-LLM safety net (DR3.2). This runs on every incoming message regardless of
# which AI backend is configured or how it responds, so an urgent situation is never missed
# solely because a model didn't follow the system prompt.
RED_FLAG_PATTERNS = [
    "can't breathe", "cant breathe", "difficulty breathing", "trouble breathing",
    "chest pain", "chest pressure",
    "unresponsive", "won't wake up", "wont wake up", "not waking up", "passed out", "unconscious",
    "severe bleeding", "won't stop bleeding", "wont stop bleeding", "bleeding a lot",
    "seizure", "convulsing",
    "face drooping", "slurred speech", "sudden weakness", "can't move her arm", "cant move her arm",
    "can't move his arm", "cant move his arm", "stroke",
    "fell and can't get up", "fell and cant get up", "hit her head", "hit his head", "head injury",
    "suicide", "kill herself", "kill himself", "kill myself", "hurt herself", "hurt himself",
    "hurting me", "hurting her", "hurting him", "911",
]

SAFETY_BANNER = (
    "⚠️ This sounds like it could be a medical emergency. Please call 911 (or your local emergency "
    "number) or your doctor's urgent line right now, before anything else."
)


def check_red_flags(text: str) -> bool:
    t = (text or "").lower()
    return any(p in t for p in RED_FLAG_PATTERNS)


SYSTEM_SUMMARY = """You are ComCare. Generate a concise, professional pre-visit clinical summary for an ADRD caregiver to share with their physician.

Format the output as plain text with exactly these four sections:
1. PATIENT INFORMATION
2. VISIT PRIORITIES
3. DISCUSSION CHECKLIST
4. RECENT OVERALL PICTURE AND ROUTINES

Use clinical but accessible language. Never diagnose. Be specific and actionable.
Only use information actually present in the supplied records and caregiver input. If something relevant is missing, write "Not recorded" rather than inferring or inventing a detail."""


async def call_ollama(messages: list, system: str, settings: dict) -> str:
    url = settings.get("ollama_url", "http://localhost:11434")
    model = settings.get("ollama_model", "llama3.2")

    # Build a single prompt string — works on all Ollama versions via /api/generate
    prompt_parts = [f"System: {system}\n"]
    for m in messages:
        role = "User" if m["role"] == "user" else "Assistant"
        prompt_parts.append(f"{role}: {m['content']}")
    prompt_parts.append("Assistant:")
    prompt = "\n".join(prompt_parts)

    payload = {
        "model": model,
        "prompt": prompt,
        "system": system,
        "stream": False,
    }
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(f"{url}/api/generate", json=payload)
        resp.raise_for_status()
        return resp.json()["response"]


async def call_openai(messages: list, system: str, settings: dict) -> str:
    api_key = settings.get("openai_api_key", "")
    model = settings.get("openai_model", "gpt-4o-mini") or "gpt-4o-mini"
    if not api_key:
        raise HTTPException(400, "OpenAI API key not configured")
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": system}] + messages,
        "max_tokens": 800,
        "temperature": 0.7,
    }
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            "https://api.openai.com/v1/chat/completions",
            json=payload,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        )
        if resp.status_code >= 400:
            # Surface OpenAI's own error message (e.g. bad key, bad model) instead of a generic 500
            try:
                detail = resp.json().get("error", {}).get("message", resp.text)
            except Exception:
                detail = resp.text
            raise HTTPException(resp.status_code if resp.status_code < 500 else 502, f"OpenAI API error: {detail}")
        data = resp.json()
        return data["choices"][0]["message"]["content"]


async def call_azure(messages: list, system: str, settings: dict) -> str:
    endpoint = settings.get("azure_endpoint", "").rstrip("/")
    api_key = settings.get("azure_api_key", "")
    deployment = settings.get("azure_deployment", "gpt-4o")
    if not endpoint or not api_key:
        raise HTTPException(400, "Azure endpoint and API key not configured")
    url = f"{endpoint}/openai/deployments/{deployment}/chat/completions?api-version=2024-02-01"
    payload = {
        "messages": [{"role": "system", "content": system}] + messages,
        "max_tokens": 800,
        "temperature": 0.7,
    }
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            url,
            json=payload,
            headers={"api-key": api_key, "Content-Type": "application/json"},
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]


async def call_ai(messages: list, system: str, settings: dict) -> str:
    backend = settings.get("ai_backend", "ollama")
    if backend == "azure":
        return await call_azure(messages, system, settings)
    if backend == "openai":
        return await call_openai(messages, system, settings)
    return await call_ollama(messages, system, settings)


def build_chat_system_prompt(message_count: int = 0) -> str:
    """Assemble a dynamic system prompt enriched with patient profile and recent records."""
    s = get_settings()

    # ── Patient profile block ──────────────────────────────────────────────────
    patient_name = s.get("patient_name", "the patient")
    patient_age  = s.get("patient_age", "")
    diagnosis    = s.get("patient_diagnosis", "")
    physician    = s.get("patient_physician", "")
    next_visit   = s.get("patient_next_visit", "")

    profile_block = f"""
PATIENT YOU ARE HELPING WITH:
  Name: {patient_name}{f', age {patient_age}' if patient_age else ''}
  Diagnosis: {diagnosis or 'Not specified'}
  Primary physician: {physician or 'Not specified'}
  Next visit: {next_visit or 'Not scheduled'}

Use the patient's name naturally in conversation. Reference their diagnosis when explaining symptoms or behaviors.
When the next visit is soon, encourage preparing visit questions."""

    # ── Recent records block ───────────────────────────────────────────────────
    cutoff = (datetime.utcnow().replace(hour=0, minute=0, second=0)
              .__class__.utcnow() if False else datetime.utcnow())
    # last 21 days
    with get_db() as conn:
        rows = conn.execute(
            """SELECT card_type, data, created_at FROM records
               ORDER BY created_at DESC LIMIT 30"""
        ).fetchall()

    CARD_SHORT = {
        "care_change": "Care Change",
        "medication": "Medication",
        "coordination": "Task",
        "visit_priority": "Visit Q",
        "caregiver_support": "Support Need",
        "what_matters": "Preference",
    }

    if rows:
        lines = []
        for r in rows:
            d = json.loads(r["data"])
            # Pull the most informative field per card type
            summary = (
                d.get("description") or d.get("concern") or d.get("follow_up_item")
                or d.get("question") or d.get("challenge") or "—"
            )
            date_str = r["created_at"][:10]
            label = CARD_SHORT.get(r["card_type"], r["card_type"])
            sev = d.get("severity") or d.get("impact") or d.get("status") or ""
            lines.append(f"  [{date_str}] {label}: {summary[:120]}" + (f" ({sev})" if sev else ""))

        records_block = "\nRECENT SAVED CARE RECORDS (newest first):\n" + "\n".join(lines) + """

Use these records to:
- Notice patterns (e.g., repeated falls, worsening confusion, recurring medication questions)
- Avoid asking the caregiver to repeat information already logged
- Reference specific past events when relevant (e.g., "You mentioned last week that...")
- Highlight anything that should definitely come up at the next visit
- Suggest a record type that complements what's already saved"""
    else:
        records_block = "\nNo care records saved yet. Encourage the caregiver to log observations."

    # ── Medication shortlist ───────────────────────────────────────────────────
    med_rows = [r for r in rows if r["card_type"] == "medication"]
    if med_rows:
        med_names = list({json.loads(r["data"]).get("medication_name","") for r in med_rows if json.loads(r["data"]).get("medication_name")})
        meds_block = f"\nKNOWN MEDICATIONS (from records): {', '.join(med_names)}\nWhen the caregiver mentions side effects or changes, connect them to these medications where relevant."
    else:
        meds_block = ""

    # ── Conversation pacing guidance ──────────────────────────────────────────
    # message_count = number of messages already in history (user + assistant)
    # Each full round = 2 messages. We want at least 3 rounds before wrapping up.
    rounds = message_count // 2
    if rounds == 0:
        pacing_block = """

CONVERSATION STAGE: Opening
This is the first message. Greet the caregiver like a care manager who's ready to get to work, not a chatbot waiting for instructions. React briefly and specifically to what they said, then ask one pointed question that targets the detail an experienced care professional would want first (timing, what preceded it, or how it compares to normal for this person). Do NOT suggest saving a record yet."""
    elif rounds <= 1:
        pacing_block = """

CONVERSATION STAGE: Early (round 1-2)
You're still gathering information — drive this like an intake interview, not a passive chat. Ask 1-2 sharp, specific follow-up questions that would actually change how this gets handled (timing, frequency, severity, what came before it, safety risk, medication timing). If something you're hearing fits a well-known pattern, say so plainly. Do NOT suggest saving a record yet unless the situation is urgent."""
    elif rounds <= 2:
        pacing_block = """

CONVERSATION STAGE: Middle (round 2-3)
You have a reasonable picture now. Offer a brief, confident synthesis of what you're hearing — don't just keep asking without ever reflecting anything back. Keep probing anything still unclear that matters for care or for the next visit. You MAY suggest saving a record if you have enough specific detail."""
    else:
        pacing_block = """

CONVERSATION STAGE: Ready to wrap up (3+ rounds completed)
You have gathered enough information across multiple exchanges. After your reply, the app will automatically show a full conversation summary. End your response naturally — e.g. "I think I have a good picture of what's been happening. I'll pull together a summary for you now." Then provide any final record suggestions if appropriate."""

    return SYSTEM_CHAT + profile_block + records_block + meds_block + pacing_block


# ── Pydantic models ────────────────────────────────────────────────────────────
class ChatRequest(BaseModel):
    messages: list
    session_id: Optional[str] = None


class RecordCreate(BaseModel):
    card_type: str
    data: dict


class RecordUpdate(BaseModel):
    data: dict


class SettingsUpdate(BaseModel):
    settings: dict


class ChatSummarizeRequest(BaseModel):
    messages: list          # full conversation so far
    session_id: Optional[str] = None


class SummaryRequest(BaseModel):
    date_range: Optional[str] = None
    concerns: Optional[str] = None
    questions: Optional[str] = None
    specialty: Optional[str] = None   # e.g. "Neurology", "Cardiology", "Primary Care"
    purpose: Optional[str] = None     # free-text visit purpose
    audience: Optional[str] = "clinician"   # "clinician" or "handoff"
    recipient: Optional[str] = None   # for handoff: who is receiving it, e.g. "My sister (weekend coverage)"


class ExplainRequest(BaseModel):
    text: str


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return FileResponse("comcare.html")

# Service worker must be served from root scope (not /static/) so it can
# intercept all same-origin requests
@app.get("/sw.js")
async def service_worker():
    return FileResponse(
        STATIC_DIR / "sw.js",
        media_type="application/javascript",
        headers={"Service-Worker-Allowed": "/"},
    )

@app.get("/manifest.json")
async def manifest():
    return FileResponse(STATIC_DIR / "manifest.json", media_type="application/manifest+json")


# ── Chat ──────────────────────────────────────────────────────────────────────
@app.post("/api/chat")
async def chat(req: ChatRequest):
    settings = get_settings()
    system_prompt = build_chat_system_prompt(len(req.messages))  # patient profile + recent records + pacing

    # Deterministic safety net (DR3.2): check the caregiver's latest message for acute red flags
    # independently of the AI backend, so escalation never depends solely on model compliance.
    last_user_msg = next((m["content"] for m in reversed(req.messages) if m.get("role") == "user"), "")
    is_red_flag = check_red_flags(last_user_msg)

    try:
        reply = await call_ai(req.messages, system_prompt, settings)
    except (httpx.ConnectError, HTTPException, Exception) as e:
        # If this looks urgent, the caregiver must see the safety banner regardless of whether the
        # AI backend is reachable — a connection error must never silently swallow an emergency (DR3.2).
        if is_red_flag:
            reply = (
                f"{SAFETY_BANNER}\n\n(ComCare's AI assistant couldn't be reached just now, but please "
                "don't wait for it in an emergency.)"
            )
            return {"reply": reply, "backend": settings.get("ai_backend"), "red_flag": True}
        if isinstance(e, httpx.ConnectError):
            backend = settings.get("ai_backend", "ollama")
            if backend == "ollama":
                raise HTTPException(
                    503,
                    f"Cannot reach Ollama at {settings.get('ollama_url')}. "
                    "Make sure Ollama is running: `ollama serve`",
                )
            if backend == "openai":
                raise HTTPException(503, "Cannot reach OpenAI. Check your internet connection.")
            raise HTTPException(503, "Cannot reach Azure OpenAI. Check endpoint and key.")
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(500, str(e))

    if is_red_flag and SAFETY_BANNER not in reply:
        reply = f"{SAFETY_BANNER}\n\n{reply}"

    # Persist messages
    if req.session_id:
        now = datetime.utcnow().isoformat()
        with get_db() as conn:
            for msg in req.messages[-2:]:  # last user + save reply below
                conn.execute(
                    "INSERT OR IGNORE INTO chat_messages VALUES (?, ?, ?, ?, ?)",
                    (str(uuid.uuid4()), req.session_id, msg["role"], msg["content"], now),
                )
            conn.execute(
                "INSERT INTO chat_messages VALUES (?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), req.session_id, "assistant", reply, now),
            )
            conn.commit()

    return {"reply": reply, "backend": settings.get("ai_backend"), "red_flag": is_red_flag}


# ── Records ───────────────────────────────────────────────────────────────────
@app.get("/api/records")
async def list_records(card_type: Optional[str] = None):
    with get_db() as conn:
        if card_type:
            rows = conn.execute(
                "SELECT * FROM records WHERE card_type = ? ORDER BY created_at DESC",
                (card_type,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM records ORDER BY created_at DESC"
            ).fetchall()
    return [
        {
            "id": r["id"],
            "card_type": r["card_type"],
            "data": json.loads(r["data"]),
            "created_at": r["created_at"],
        }
        for r in rows
    ]


@app.post("/api/records")
async def create_record(rec: RecordCreate):
    now = datetime.utcnow().isoformat()
    rid = str(uuid.uuid4())
    with get_db() as conn:
        conn.execute(
            "INSERT INTO records VALUES (?, ?, ?, ?, ?)",
            (rid, rec.card_type, json.dumps(rec.data), now, now),
        )
        conn.commit()
    return {"id": rid, "created_at": now}


@app.put("/api/records/{record_id}")
async def update_record(record_id: str, rec: RecordUpdate):
    now = datetime.utcnow().isoformat()
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM records WHERE id = ?", (record_id,)
        ).fetchone()
        if not row:
            raise HTTPException(404, "Record not found")
        existing = json.loads(row["data"])
        existing.update(rec.data)
        conn.execute(
            "UPDATE records SET data = ?, updated_at = ? WHERE id = ?",
            (json.dumps(existing), now, record_id),
        )
        conn.commit()
    return {"id": record_id, "updated_at": now}


@app.delete("/api/records/{record_id}")
async def delete_record(record_id: str):
    with get_db() as conn:
        conn.execute("DELETE FROM records WHERE id = ?", (record_id,))
        conn.commit()
    return {"deleted": record_id}


# ── Chat summarize ────────────────────────────────────────────────────────────
SYSTEM_CHAT_SUMMARIZE = """You are ComCare. The caregiver has just finished a chat session sharing observations.
Review the conversation and produce a JSON-only response (no other text) in this exact structure:

{
  "what_i_heard": "A warm 3–5 sentence paragraph summarising the key observations and concerns the caregiver shared. Use the patient's name. Write in plain, empathetic language. Attribute each point to its source (caregiver observed / patient reported / caregiver is unsure) rather than stating everything as settled fact. Only include what was actually said in the conversation — never add or infer details that weren't mentioned.",
  "gaps": "1–3 brief follow-up questions for anything still unclear — timing, frequency, severity. If the caregiver raised more than one concern without saying which matters most, include one question asking them to prioritize, using their own items as the options. Omit this key (or set to empty string) if nothing is unclear.",
  "suggested_records": [
    {
      "card_type": "care_change|medication|coordination|visit_priority|caregiver_support|what_matters",
      "description": "One concise sentence describing what should be recorded."
    }
  ]
}

Rules:
- Output ONLY valid JSON. No markdown, no prose outside the JSON.
- suggested_records may be an empty list [] if nothing is clearly recordable yet.
- Keep descriptions under 120 characters.
- Never resolve caregiver uncertainty for them — reflect it back instead of stating a conclusion."""


@app.post("/api/chat/summarize")
async def chat_summarize(req: ChatSummarizeRequest):
    """Summarize the conversation, surface gaps, and batch-suggest records."""
    settings = get_settings()
    s = get_settings()
    patient_name = s.get("patient_name", "the patient")

    system = SYSTEM_CHAT_SUMMARIZE + f"\n\nPatient: {patient_name}. Diagnosis: {s.get('patient_diagnosis', 'ADRD')}."

    trigger = {"role": "user", "content": "Please summarize our conversation now."}
    messages = list(req.messages) + [trigger]

    try:
        reply = await call_ai(messages, system, settings)
    except httpx.ConnectError:
        raise HTTPException(503, "Cannot reach AI backend.")
    except Exception as e:
        raise HTTPException(500, str(e))

    # Parse structured JSON from AI; fall back gracefully
    import json as _json
    try:
        # Strip markdown code fences if present
        clean = reply.strip()
        if clean.startswith("```"):
            clean = "\n".join(clean.split("\n")[1:])
        if clean.endswith("```"):
            clean = clean.rsplit("```", 1)[0]
        structured = _json.loads(clean.strip())
    except Exception:
        # Fallback: return raw reply as what_i_heard
        structured = {
            "what_i_heard": reply,
            "gaps": "",
            "suggested_records": []
        }

    return {**structured, "backend": settings.get("ai_backend")}


# ── Visit Summary ─────────────────────────────────────────────────────────────
SPECIALTY_FOCUS = {
    "Neurology": """Focus especially on:
- Cognitive symptoms: memory, confusion, disorientation, word-finding
- Behavioral and mood changes: agitation, anxiety, depression, sleep
- Medication efficacy and side effects for dementia drugs (cholinesterase inhibitors, memantine)
- Disease progression markers since last visit
- Safety concerns related to cognitive decline""",

    "Cardiology": """Focus especially on:
- Cardiovascular symptoms: chest pain, shortness of breath, palpitations, swelling
- Blood pressure trends and medication (antihypertensives, diuretics)
- Activity tolerance and any changes in stamina or mobility
- Fluid intake, diet, and weight changes
- Any symptoms that could interact with cardiac medications""",

    "Primary Care": """Provide a comprehensive general overview covering:
- All active symptoms and behavioral changes
- Full medication list and any concerns
- Functional status: ADLs, mobility, falls
- Upcoming specialist referrals or coordination needs
- Caregiver support and capacity""",

    "Physical Therapy": """Focus especially on:
- Mobility and gait: changes, unsteadiness, near-falls or falls
- Functional abilities: transfers, dressing, bathing, walking distance
- Pain or discomfort affecting movement
- Home environment safety concerns (stairs, bathroom, rugs)
- Current activity level and any decline""",

    "Pharmacy / Medication Review": """Focus especially on:
- Complete medication list with doses and schedule
- Any new medications, recent dose changes, or stopped medications
- Observed side effects or adverse reactions
- Medication adherence and administration challenges
- Questions about drug interactions or timing""",

    "Social Work / Care Coordination": """Focus especially on:
- Caregiver stress, capacity, and support needs
- Home safety and living situation
- Community resources, respite care, or day programs needed
- Financial or insurance concerns related to care
- Family communication and decision-making dynamics""",

    "Other Specialist": "",  # No special focus — use general format
}


NO_FABRICATION_CLAUSE = (
    "\n\nGROUNDING RULE: Only use information actually present in the caregiver-supplied records and "
    "notes below. Do not infer, assume, or invent any detail that isn't explicitly there — including "
    "dates, severity, causes, or medication effects. Where something relevant is missing, write "
    "\"Not recorded\" instead of filling the gap. Preserve each item's original attribution (observed / "
    "patient-reported / caregiver-uncertain) rather than restating everything as settled fact."
)


def build_summary_system_prompt(specialty: str, purpose: str, audience: str = "clinician") -> str:
    if audience == "handoff":
        base = """You are ComCare. Generate a concise, practical handoff note so another caregiver (family member, friend, or paid/respite caregiver) can safely and comfortably step in.

Format the output as plain text with exactly these five sections:
1. WHO YOU'RE CARING FOR — name, and anything essential to know at a glance
2. DAILY ROUTINES & WHAT MATTERS TO THEM — preferences, comfort routines, things that help
3. CURRENT THINGS TO WATCH FOR — recent changes, and what "normal for them" looks like right now
4. MEDICATIONS & SCHEDULE — as recorded, with any open questions flagged rather than resolved
5. PENDING TASKS & WHO TO CALL — open coordination items, and emergency/clinician contact info if recorded

Use warm, plain, non-clinical language — this is for a person providing hands-on care, not a clinician. Never diagnose."""
    else:
        base = """You are ComCare. Generate a concise, professional pre-visit clinical summary for an ADRD caregiver to share with their care team.

Format the output as plain text with exactly these four sections:
1. PATIENT INFORMATION
2. VISIT PURPOSE & PRIORITIES
3. DISCUSSION CHECKLIST
4. RECENT OVERALL PICTURE AND ROUTINES

Use clinical but accessible language. Never diagnose. Be specific and actionable."""

        focus = SPECIALTY_FOCUS.get(specialty, "")
        if focus:
            base += f"\n\nSPECIALTY FOCUS — This summary is for a {specialty} visit:\n{focus}"

    if purpose:
        base += f"\n\nVISIT PURPOSE (caregiver-stated): {purpose}\nMake sure the summary is shaped around this purpose."

    base += NO_FABRICATION_CLAUSE
    return base


@app.post("/api/summary")
async def generate_summary(req: SummaryRequest):
    settings = get_settings()
    specialty = req.specialty or "Primary Care"
    purpose = req.purpose or ""
    audience = req.audience if req.audience in ("clinician", "handoff") else "clinician"
    recipient = req.recipient or ""

    with get_db() as conn:
        rows = conn.execute(
            "SELECT card_type, data FROM records ORDER BY created_at DESC LIMIT 30"
        ).fetchall()

    # Respect situational privacy (DR6.3/DR8.2): records the caregiver marked "Caregiver only"
    # are excluded from anything meant to be shared with a clinician or handed off to someone else.
    included_rows = []
    for r in rows:
        try:
            data = json.loads(r["data"])
        except Exception:
            data = {}
        if data.get("visibility") == "Caregiver only":
            continue
        included_rows.append((r["card_type"], r["data"]))

    hidden_count = len(rows) - len(included_rows)
    records_text = "\n".join(f"[{ct}] {d}" for ct, d in included_rows) or "No shareable records saved yet."
    if hidden_count:
        records_text += f"\n\n({hidden_count} caregiver-private record(s) exist but are marked 'Caregiver only' and intentionally excluded.)"

    audience_line = (
        f"Handoff recipient: {recipient or 'another caregiver (unspecified)'}"
        if audience == "handoff"
        else f"Visit specialty: {specialty}"
    )

    user_msg = f"""
Patient: {settings.get('patient_name')}, {settings.get('patient_age')}, {settings.get('patient_diagnosis')}
Primary physician: {settings.get('patient_physician')}
Upcoming visit: {settings.get('patient_next_visit')}
{audience_line}
Purpose: {purpose or 'Routine follow-up'}
Date range covered: {req.date_range or 'past 2 weeks'}

Saved care records (caregiver-private records excluded):
{records_text}

Caregiver concerns: {req.concerns or 'Not specified'}
Questions for clinician: {req.questions or 'Not specified'}

Generate the {'handoff note' if audience == 'handoff' else 'visit summary'} now.
"""
    system_prompt = build_summary_system_prompt(specialty, purpose, audience)

    try:
        summary = await call_ai(
            [{"role": "user", "content": user_msg}], system_prompt, settings
        )
    except Exception as e:
        raise HTTPException(500, str(e))

    return {
        "summary": summary,
        "specialty": specialty,
        "purpose": purpose,
        "audience": audience,
        "recipient": recipient,
        "generated_at": datetime.utcnow().isoformat(),
    }


# ── Plain-language explain ──────────────────────────────────────────────────────
SYSTEM_EXPLAIN = """You are ComCare. A caregiver has asked you to explain something in plain, everyday language.

Rules:
- Rewrite the given text in plain language a non-medical family member can follow
- Keep it short — 2-4 sentences
- Preserve every safety warning, uncertainty, or "check with your doctor/pharmacist" boundary from the original — never drop or soften a caution just to make the explanation shorter or simpler
- Never turn a possibility or a question into a definite statement
- Never diagnose, and never state that a medication is or isn't causing a specific symptom"""


@app.post("/api/explain")
async def explain_plain_language(req: ExplainRequest):
    settings = get_settings()
    if not req.text or not req.text.strip():
        raise HTTPException(400, "No text provided")
    try:
        explanation = await call_ai(
            [{"role": "user", "content": f"Please explain this in plain language:\n\n{req.text}"}],
            SYSTEM_EXPLAIN,
            settings,
        )
    except httpx.ConnectError:
        raise HTTPException(503, "Cannot reach AI backend.")
    except Exception as e:
        raise HTTPException(500, str(e))
    return {"explanation": explanation}


# ── Settings ──────────────────────────────────────────────────────────────────
@app.get("/api/settings")
async def get_all_settings():
    s = get_settings()
    # Mask sensitive keys
    if s.get("azure_api_key"):
        s["azure_api_key"] = "••••••••" + s["azure_api_key"][-4:]
    if s.get("openai_api_key"):
        s["openai_api_key"] = "••••••••" + s["openai_api_key"][-4:]
    return s


@app.post("/api/settings")
async def save_settings(req: SettingsUpdate):
    # Don't overwrite masked key placeholders
    for k, v in req.settings.items():
        if k in ("azure_api_key", "openai_api_key") and v.startswith("••••"):
            continue
        update_setting(k, str(v))
    return {"saved": True}


@app.get("/api/settings/test")
async def test_connection():
    settings = get_settings()
    backend = settings.get("ai_backend", "ollama")
    try:
        reply = await call_ai(
            [{"role": "user", "content": "Reply with: ComCare ready"}],
            "You are a test assistant. Follow the instruction exactly.",
            settings,
        )
        return {"ok": True, "backend": backend, "reply": reply[:80]}
    except Exception as e:
        return {"ok": False, "backend": backend, "error": str(e)}


# ── Dashboard data ────────────────────────────────────────────────────────────
@app.get("/api/dashboard")
async def dashboard():
    settings = get_settings()
    with get_db() as conn:
        records = conn.execute(
            "SELECT card_type, data, created_at FROM records ORDER BY created_at DESC LIMIT 10"
        ).fetchall()
        record_count = conn.execute("SELECT COUNT(*) as c FROM records").fetchone()["c"]
        coord_rows = conn.execute(
            "SELECT id, data, created_at FROM records WHERE card_type = 'coordination' ORDER BY created_at DESC"
        ).fetchall()

    recent = [
        {
            "card_type": r["card_type"],
            "data": json.loads(r["data"]),
            "created_at": r["created_at"],
        }
        for r in records
    ]

    # DR7.1 — surface pending coordination tasks distinctly rather than burying them in the
    # generic recent-records feed, so responsibility and status stay visible.
    pending_tasks = []
    for r in coord_rows:
        d = json.loads(r["data"])
        if d.get("status", "Needs action") != "Done":
            pending_tasks.append({
                "id": r["id"],
                "follow_up_item": d.get("follow_up_item", ""),
                "responsible": d.get("responsible", "Unsure"),
                "due_date": d.get("due_date", ""),
                "status": d.get("status", "Needs action"),
                "importance": d.get("importance", "Medium"),
                "created_at": r["created_at"],
            })

    return {
        "patient_name": settings.get("patient_name"),
        "patient_diagnosis": settings.get("patient_diagnosis"),
        "patient_physician": settings.get("patient_physician"),
        "next_visit": settings.get("patient_next_visit"),
        "total_records": record_count,
        "recent_records": recent,
        "pending_tasks": pending_tasks,
        "ai_backend": settings.get("ai_backend"),
    }
