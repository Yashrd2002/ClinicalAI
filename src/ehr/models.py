from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class SlotStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    HELD = "HELD"
    BOOKED = "BOOKED"


class AppointmentStatus(str, Enum):
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"
    RESCHEDULED = "RESCHEDULED"


class HoldStatus(str, Enum):
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    CONVERTED = "CONVERTED"
    RELEASED = "RELEASED"


class Patient(BaseModel):
    id: str
    first_name: str
    last_name: str
    dob: str  # YYYY-MM-DD
    phone: str
    email: Optional[str] = None
    existing_notes: Optional[str] = None


class Provider(BaseModel):
    id: str
    name: str
    specialty: str
    clinic_location: str


class Slot(BaseModel):
    id: str
    provider_id: str
    start_time: str  # ISO string or YYYY-MM-DD HH:MM
    end_time: str
    status: SlotStatus = SlotStatus.AVAILABLE


class Hold(BaseModel):
    id: str
    slot_id: str
    patient_id: str
    created_at: str
    expires_at: str
    status: HoldStatus = HoldStatus.ACTIVE


class Appointment(BaseModel):
    id: str
    slot_id: str
    patient_id: str
    provider_id: str
    reason: str
    status: AppointmentStatus = AppointmentStatus.CONFIRMED
    created_at: str
    updated_at: Optional[str] = None


class AuditLogEntry(BaseModel):
    timestamp: str
    tool_name: str
    patient_id: Optional[str]
    parameters: Dict[str, Any]
    result: Dict[str, Any]
    success: bool
    error_message: Optional[str] = None
