"""
HVAC AI Voice Receptionist - Demo Backend
------------------------------------------
This FastAPI app exposes the "tools" that the Vapi assistant calls during
a live conversation. Everything is backed by in-memory mock data so the
demo works instantly with zero external dependencies (no real CRM,
no real calendar, no real DB). Swap the mock functions for real
integrations (Google Calendar, GoHighLevel, etc.) once you have a paying
client.

Run locally:
    pip install -r requirements.txt
    uvicorn app.main:app --reload --port 8000

Expose to Vapi during the demo with a tunnel:
    ngrok http 8000
    (or) cloudflared tunnel --url http://localhost:8000
Then paste the public URL into each Vapi tool's "Server URL" field.
"""

from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

app = FastAPI(title="HVAC Voice Agent - Demo Tools API")

# Serves the shareable voice-widget demo page at /demo
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
app.mount("/demo", StaticFiles(directory=STATIC_DIR, html=True), name="demo")

# ---------------------------------------------------------------------------
# MOCK DATA (replace with real DB / CRM / Calendar calls later)
# ---------------------------------------------------------------------------

SERVICE_AREAS = {
    "dallas", "plano", "richardson", "garland", "irving", "addison",
    "75201", "75202", "75204", "75220", "75238", "75240", "75243", "75251",
    "north dallas", "east dallas", "uptown dallas", "lake highlands",
}

# Pretend calendar: next 5 days, 9am-5pm, hourly slots, some pre-booked
def _generate_slots():
    slots = []
    now = datetime.now().replace(minute=0, second=0, microsecond=0)
    booked_offsets = {3, 7, 12}  # a few slots already taken, for realism
    idx = 0
    for day in range(1, 6):
        date = now + timedelta(days=day)
        for hour in range(9, 17):
            slot_time = date.replace(hour=hour)
            slots.append({
                "id": f"slot_{idx}",
                "datetime": slot_time.isoformat(),
                "available": idx not in booked_offsets,
            })
            idx += 1
    return slots

CALENDAR_SLOTS = _generate_slots()
APPOINTMENTS = []
CALL_SUMMARIES = []

EMERGENCY_KEYWORDS = {
    "gas leak", "gas smell", "smell gas", "smoke", "fire",
    "carbon monoxide", "co detector", "co alarm", "sparking", "electrical fire",
    "no heat", "no ac", "no cooling at all", "flooding", "burning smell",
}

# ---------------------------------------------------------------------------
# REQUEST/RESPONSE MODELS
# ---------------------------------------------------------------------------

class ServiceAreaRequest(BaseModel):
    location: str

class SlotsRequest(BaseModel):
    days_ahead: Optional[int] = 5

class BookingRequest(BaseModel):
    customer_name: str
    phone_number: str
    slot_id: str
    issue_description: str
    address: Optional[str] = None

class ContactRequest(BaseModel):
    customer_name: str
    phone_number: str
    notes: Optional[str] = None

class SmsRequest(BaseModel):
    phone_number: str
    message: str

class SummaryRequest(BaseModel):
    caller_name: Optional[str] = None
    phone_number: Optional[str] = None
    summary: str
    outcome: str  # e.g. "booked", "emergency_transferred", "no_availability"

class TransferRequest(BaseModel):
    reason: str

class EmergencyCheckRequest(BaseModel):
    transcript_snippet: str


# ---------------------------------------------------------------------------
# TOOL ENDPOINTS  (one per Vapi "function")
# ---------------------------------------------------------------------------

@app.get("/", include_in_schema=False)
def home():
    return RedirectResponse("/demo/")


@app.get("/health")
def health():
    return {"status": "ok", "service": "HVAC Voice Agent Demo Backend"}


@app.post("/check-service-area")
def check_service_area(req: ServiceAreaRequest):
    """Vapi function: check_service_area(location)"""
    loc = req.location.strip().lower()
    in_area = any(area in loc or loc in area for area in SERVICE_AREAS)
    return {
        "in_service_area": in_area,
        "message": (
            "Great news, we cover that area."
            if in_area
            else "That location is outside our current service area, "
                 "but I can still take your details and have our team confirm."
        ),
    }


@app.post("/get-available-slots")
def get_available_slots(req: SlotsRequest):
    """Vapi function: get_available_slots(days_ahead)"""
    limit_time = datetime.now() + timedelta(days=req.days_ahead or 5)
    available = [
        s for s in CALENDAR_SLOTS
        if s["available"] and datetime.fromisoformat(s["datetime"]) <= limit_time
    ]
    # Return only the next few to keep the voice response short
    return {"available_slots": available[:6]}


@app.post("/book-appointment")
def book_appointment(req: BookingRequest):
    """Vapi function: book_appointment(customer_name, phone_number, slot_id, issue_description, address)"""
    slot = next((s for s in CALENDAR_SLOTS if s["id"] == req.slot_id), None)
    if not slot or not slot["available"]:
        return {"success": False, "message": "That slot is no longer available. Please choose another."}

    slot["available"] = False
    appointment = {
        "appointment_id": f"appt_{len(APPOINTMENTS) + 1}",
        "customer_name": req.customer_name,
        "phone_number": req.phone_number,
        "datetime": slot["datetime"],
        "issue_description": req.issue_description,
        "address": req.address,
        "status": "confirmed",
    }
    APPOINTMENTS.append(appointment)
    return {
        "success": True,
        "appointment_id": appointment["appointment_id"],
        "confirmed_time": slot["datetime"],
        "message": f"You're booked for {slot['datetime']}. A confirmation text is on its way.",
    }


@app.post("/create-contact")
def create_contact(req: ContactRequest):
    """Vapi function: create_contact(customer_name, phone_number, notes) - mock CRM write"""
    return {
        "success": True,
        "contact_id": f"contact_{req.phone_number[-4:]}",
        "message": "Contact saved to CRM (mock).",
    }


@app.post("/send-sms")
def send_sms(req: SmsRequest):
    """Vapi function: send_sms(phone_number, message) - mock, logs instead of real Twilio send"""
    print(f"[MOCK SMS] to {req.phone_number}: {req.message}")
    return {"success": True, "message": "SMS sent (mock)."}


@app.post("/notify-team")
def notify_team(req: SummaryRequest):
    """Vapi function: notify_team(...) - mock Slack/technician alert"""
    print(f"[MOCK TEAM ALERT] {req.outcome}: {req.summary}")
    return {"success": True, "message": "Team notified (mock)."}


@app.post("/check-emergency")
def check_emergency(req: EmergencyCheckRequest):
    """Vapi function: check_emergency(transcript_snippet) - simple keyword-based flag"""
    text = req.transcript_snippet.lower()
    is_emergency = any(kw in text for kw in EMERGENCY_KEYWORDS)
    return {
        "is_emergency": is_emergency,
        "action": "transfer_to_human_immediately" if is_emergency else "continue_normal_flow",
    }


@app.post("/transfer-call")
def transfer_call(req: TransferRequest):
    """Vapi function: transfer_call(reason) - in real deployment this triggers Vapi's transferCall action"""
    print(f"[MOCK TRANSFER] reason: {req.reason}")
    return {"success": True, "message": f"Transferring call. Reason: {req.reason}"}


@app.post("/save-summary")
def save_summary(req: SummaryRequest):
    """Vapi function: save_summary(...) - store post-call summary"""
    CALL_SUMMARIES.append(req.dict())
    return {"success": True, "message": "Summary saved."}


# ---------------------------------------------------------------------------
# Convenience endpoints for YOU to inspect demo state (not called by Vapi)
# ---------------------------------------------------------------------------

@app.get("/debug/appointments")
def debug_appointments():
    return {"appointments": APPOINTMENTS}


@app.get("/debug/summaries")
def debug_summaries():
    return {"summaries": CALL_SUMMARIES}