import uuid
import threading
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any

from src.ehr.models import (
    Patient, Provider, Slot, Hold, Appointment, AuditLogEntry,
    SlotStatus, AppointmentStatus, HoldStatus
)


class EHRDatabase:
    """
    Mock EHR and Scheduling Database with deterministic state, atomic transitions,
    hold expiration (TTL) enforcement, audit logging, thread safety, and simulation hooks.
    """
    def __init__(self):
        self._lock = threading.RLock()
        self.patients: Dict[str, Patient] = {}
        self.providers: Dict[str, Provider] = {}
        self.slots: Dict[str, Slot] = {}
        self.holds: Dict[str, Hold] = {}
        self.appointments: Dict[str, Appointment] = {}
        self.audit_log: List[AuditLogEntry] = []
        self.simulated_outages: set[str] = set()
        self.seed_database()

    def seed_database(self):
        """Populate initial realistic clinical data."""
        self.patients.clear()
        self.providers.clear()
        self.slots.clear()
        self.holds.clear()
        self.appointments.clear()
        self.audit_log.clear()
        self.simulated_outages.clear()

        # Providers
        p1 = Provider(
            id="PRV-101",
            name="Dr. Sarah Chen",
            specialty="Cardiology",
            clinic_location="Heart Health Pavilion, Suite 300"
        )
        p2 = Provider(
            id="PRV-102",
            name="Dr. Michael Reynolds",
            specialty="Primary Care",
            clinic_location="Main Clinic, Room 102"
        )
        p3 = Provider(
            id="PRV-103",
            name="Dr. Elena Rostova",
            specialty="Orthopedics",
            clinic_location="Sports Medicine Wing, Room 210"
        )
        for p in [p1, p2, p3]:
            self.providers[p.id] = p

        # Patients
        pat1 = Patient(
            id="PAT-001",
            first_name="John",
            last_name="Doe",
            dob="1980-05-14",
            phone="555-0199",
            email="johndoe@example.com",
            existing_notes="Hypertension stage 1"
        )
        pat2 = Patient(
            id="PAT-002",
            first_name="Alice",
            last_name="Smith",
            dob="1992-11-23",
            phone="555-0144",
            email="alicesmith@example.com",
            existing_notes="Annual physical"
        )
        pat3 = Patient(
            id="PAT-003",
            first_name="Robert",
            last_name="Johnson",
            dob="1975-03-30",
            phone="555-0188",
            email="rjohnson@example.com",
            existing_notes="Follow-up knee post-arthroscopy"
        )
        for pat in [pat1, pat2, pat3]:
            self.patients[pat.id] = pat

        # Slots: Dr. Sarah Chen (Cardiology) - PRV-101
        slots_data = [
            # Dr. Chen
            Slot(id="SLOT-101", provider_id="PRV-101", start_time="2026-10-12 09:00", end_time="2026-10-12 09:45", status=SlotStatus.AVAILABLE),
            Slot(id="SLOT-102", provider_id="PRV-101", start_time="2026-10-12 11:00", end_time="2026-10-12 11:45", status=SlotStatus.AVAILABLE),
            Slot(id="SLOT-103", provider_id="PRV-101", start_time="2026-10-12 14:00", end_time="2026-10-12 14:45", status=SlotStatus.AVAILABLE),
            Slot(id="SLOT-104", provider_id="PRV-101", start_time="2026-10-13 10:00", end_time="2026-10-13 10:45", status=SlotStatus.AVAILABLE),
            # Dr. Reynolds
            Slot(id="SLOT-201", provider_id="PRV-102", start_time="2026-10-12 10:00", end_time="2026-10-12 10:30", status=SlotStatus.AVAILABLE),
            Slot(id="SLOT-202", provider_id="PRV-102", start_time="2026-10-12 15:00", end_time="2026-10-12 15:30", status=SlotStatus.AVAILABLE),
            Slot(id="SLOT-203", provider_id="PRV-102", start_time="2026-10-14 11:00", end_time="2026-10-14 11:30", status=SlotStatus.AVAILABLE),
            # Dr. Rostova
            Slot(id="SLOT-301", provider_id="PRV-103", start_time="2026-10-13 13:00", end_time="2026-10-13 13:45", status=SlotStatus.AVAILABLE),
            Slot(id="SLOT-302", provider_id="PRV-103", start_time="2026-10-14 09:00", end_time="2026-10-14 09:45", status=SlotStatus.AVAILABLE),
        ]
        for s in slots_data:
            self.slots[s.id] = s

        # Pre-existing appointment for John Doe (PAT-001) for S4 reschedule and S8 cancellation
        existing_slot = Slot(
            id="SLOT-999",
            provider_id="PRV-102",
            start_time="2026-10-16 10:00",
            end_time="2026-10-16 10:30",
            status=SlotStatus.BOOKED
        )
        self.slots[existing_slot.id] = existing_slot
        existing_appt = Appointment(
            id="APT-501",
            slot_id="SLOT-999",
            patient_id="PAT-001",
            provider_id="PRV-102",
            reason="Blood pressure routine follow-up",
            status=AppointmentStatus.CONFIRMED,
            created_at="2026-10-01 08:00"
        )
        self.appointments[existing_appt.id] = existing_appt

    def _now_str(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    def log_audit(self, tool_name: str, parameters: Dict[str, Any], result: Dict[str, Any], success: bool, patient_id: Optional[str] = None, error_message: Optional[str] = None):
        with self._lock:
            entry = AuditLogEntry(
                timestamp=self._now_str(),
                tool_name=tool_name,
                patient_id=patient_id,
                parameters=parameters,
                result=result,
                success=success,
                error_message=error_message
            )
            self.audit_log.append(entry)

    def _expire_stale_holds(self):
        """Release any held slots whose TTL has passed."""
        with self._lock:
            now = datetime.now(timezone.utc)
            for hold in list(self.holds.values()):
                if hold.status == HoldStatus.ACTIVE:
                    expires_at = datetime.fromisoformat(hold.expires_at)
                    if now > expires_at:
                        hold.status = HoldStatus.EXPIRED
                        if hold.slot_id in self.slots and self.slots[hold.slot_id].status == SlotStatus.HELD:
                            self.slots[hold.slot_id].status = SlotStatus.AVAILABLE

    def register_patient(self, first_name: str, last_name: str, dob: Optional[str] = None, phone: Optional[str] = None) -> Patient:
        """Register a new patient into the EHR with 2-identifier auth."""
        with self._lock:
            new_id = f"PAT-{len(self.patients) + 1:03d}"
            new_pat = Patient(
                id=new_id,
                first_name=first_name.strip().title(),
                last_name=last_name.strip().title(),
                dob=dob.strip() if dob else "Unknown",
                phone=phone.strip() if phone else "N/A",
                email=f"{first_name.strip().lower()}.{last_name.strip().lower()}@example.com",
                existing_notes="New patient intake via assistant"
            )
            self.patients[new_id] = new_pat
            return new_pat

    def verify_patient(self, first_name: str, last_name: str, dob: Optional[str] = None, phone: Optional[str] = None) -> Optional[Patient]:
        """
        Enforce 2-identifier verification: (First + Last Name) AND (DOB or Phone).
        Does not accept partial names.
        """
        f_norm = first_name.strip().lower()
        l_norm = last_name.strip().lower()
        dob_norm = dob.strip() if dob else None
        phone_norm = phone.strip().replace("-", "").replace(" ", "").replace("(", "").replace(")", "") if phone else None

        for p in self.patients.values():
            if p.first_name.lower() == f_norm and p.last_name.lower() == l_norm:
                # Check second identifier
                match_dob = dob_norm and p.dob == dob_norm
                p_phone_clean = p.phone.replace("-", "").replace(" ", "").replace("(", "").replace(")", "")
                match_phone = phone_norm and p_phone_clean == phone_norm
                if match_dob or match_phone:
                    return p
        return None

    def search_available_slots(self, specialty: Optional[str] = None, provider_id: Optional[str] = None, date_str: Optional[str] = None) -> List[Dict[str, Any]]:
        self._expire_stale_holds()
        results = []
        for slot in self.slots.values():
            if slot.status != SlotStatus.AVAILABLE:
                continue
            provider = self.providers.get(slot.provider_id)
            if not provider:
                continue

            # Filter by specialty if provided
            if specialty and specialty.strip().lower() not in provider.specialty.lower():
                continue

            # Filter by provider if provided (matches provider ID or provider Name)
            if provider_id:
                p_norm = provider_id.strip().lower()
                matches_id = (slot.provider_id.lower() == p_norm)
                matches_name = (p_norm in provider.name.lower() or provider.name.lower() in p_norm)
                if not matches_id and not matches_name:
                    continue

            # Filter by date if provided (substring match on YYYY-MM-DD)
            if date_str and not slot.start_time.startswith(date_str.strip()):
                continue

            results.append({
                "slot_id": slot.id,
                "provider_id": provider.id,
                "provider_name": provider.name,
                "specialty": provider.specialty,
                "start_time": slot.start_time,
                "end_time": slot.end_time,
                "location": provider.clinic_location
            })
        return results

    def create_hold(self, slot_id: str, patient_id: str, ttl_seconds: int = 300) -> Dict[str, Any]:
        with self._lock:
            self._expire_stale_holds()
            slot = self.slots.get(slot_id)
            if not slot:
                return {"success": False, "error": f"Slot '{slot_id}' not found."}
            if slot.status != SlotStatus.AVAILABLE:
                return {"success": False, "error": f"Slot '{slot_id}' is no longer available (status: {slot.status.value})."}

            now = datetime.now(timezone.utc)
            expires_at = now + timedelta(seconds=ttl_seconds)

            hold_id = f"HLD-{uuid.uuid4().hex[:8].upper()}"
            hold = Hold(
                id=hold_id,
                slot_id=slot_id,
                patient_id=patient_id,
                created_at=now.isoformat(),
                expires_at=expires_at.isoformat(),
                status=HoldStatus.ACTIVE
            )
            self.holds[hold_id] = hold
            slot.status = SlotStatus.HELD
            return {
                "success": True,
                "hold_id": hold_id,
                "slot_id": slot_id,
                "patient_id": patient_id,
                "expires_at": expires_at.isoformat(),
                "ttl_seconds": ttl_seconds
            }

    def confirm_booking(self, hold_id: str, patient_id: str, reason: str) -> Dict[str, Any]:
        with self._lock:
            self._expire_stale_holds()
            hold = self.holds.get(hold_id)
            if not hold:
                return {"success": False, "error": f"Hold '{hold_id}' not found."}
            if hold.status == HoldStatus.EXPIRED:
                return {"success": False, "error": f"Hold '{hold_id}' has expired. Please select a new slot."}
            if hold.status != HoldStatus.ACTIVE:
                return {"success": False, "error": f"Hold '{hold_id}' is not active (status: {hold.status.value})."}
            if hold.patient_id != patient_id:
                return {"success": False, "error": "Hold patient ID does not match requesting patient."}

            slot = self.slots.get(hold.slot_id)
            if not slot or slot.status != SlotStatus.HELD:
                return {"success": False, "error": f"Slot '{hold.slot_id}' is not in held status."}

            # Atomically convert hold to appointment
            appt_id = f"APT-{uuid.uuid4().hex[:8].upper()}"
            now_str = self._now_str()
            appointment = Appointment(
                id=appt_id,
                slot_id=slot.id,
                patient_id=patient_id,
                provider_id=slot.provider_id,
                reason=reason,
                status=AppointmentStatus.CONFIRMED,
                created_at=now_str
            )
            self.appointments[appt_id] = appointment
            slot.status = SlotStatus.BOOKED
            hold.status = HoldStatus.CONVERTED

            provider = self.providers.get(slot.provider_id)
            return {
                "success": True,
                "appointment_id": appt_id,
                "slot_id": slot.id,
                "provider_name": provider.name if provider else slot.provider_id,
                "start_time": slot.start_time,
                "location": provider.clinic_location if provider else "Clinic",
                "patient_id": patient_id,
                "reason": reason
            }

    def get_patient_appointments(self, patient_id: str) -> List[Dict[str, Any]]:
        with self._lock:
            results = []
            for appt in self.appointments.values():
                if appt.patient_id == patient_id and appt.status == AppointmentStatus.CONFIRMED:
                    slot = self.slots.get(appt.slot_id)
                    provider = self.providers.get(appt.provider_id)
                    results.append({
                        "appointment_id": appt.id,
                        "slot_id": appt.slot_id,
                        "provider_name": provider.name if provider else appt.provider_id,
                        "specialty": provider.specialty if provider else "General",
                        "start_time": slot.start_time if slot else "Unknown",
                        "reason": appt.reason,
                        "location": provider.clinic_location if provider else "Clinic"
                    })
            return results

    def reschedule_appointment(self, appointment_id: str, new_slot_id: str, patient_id: str) -> Dict[str, Any]:
        with self._lock:
            self._expire_stale_holds()
            appt = self.appointments.get(appointment_id)
            if not appt:
                return {"success": False, "error": f"Appointment '{appointment_id}' not found."}
            if appt.patient_id != patient_id:
                return {"success": False, "error": "Appointment does not belong to verified patient."}
            if appt.status != AppointmentStatus.CONFIRMED:
                return {"success": False, "error": f"Appointment is not in confirmed status (current: {appt.status.value})."}

            new_slot = self.slots.get(new_slot_id)
            if not new_slot:
                return {"success": False, "error": f"New slot '{new_slot_id}' not found."}
            if new_slot.status != SlotStatus.AVAILABLE:
                return {"success": False, "error": f"New slot '{new_slot_id}' is not available."}

            # Release old slot
            old_slot = self.slots.get(appt.slot_id)
            if old_slot:
                old_slot.status = SlotStatus.AVAILABLE

            # Assign new slot
            new_slot.status = SlotStatus.BOOKED
            appt.slot_id = new_slot.id
            appt.provider_id = new_slot.provider_id
            appt.status = AppointmentStatus.CONFIRMED
            appt.updated_at = self._now_str()

            provider = self.providers.get(new_slot.provider_id)
            return {
                "success": True,
                "appointment_id": appt.id,
                "old_slot_id": old_slot.id if old_slot else None,
                "new_slot_id": new_slot.id,
                "new_start_time": new_slot.start_time,
                "provider_name": provider.name if provider else new_slot.provider_id,
                "location": provider.clinic_location if provider else "Clinic"
            }

    def cancel_appointment(self, appointment_id: str, patient_id: str, reason: str = "Patient request") -> Dict[str, Any]:
        with self._lock:
            appt = self.appointments.get(appointment_id)
            if not appt:
                return {"success": False, "error": f"Appointment '{appointment_id}' not found."}
            if appt.patient_id != patient_id:
                return {"success": False, "error": "Appointment does not belong to verified patient."}
            if appt.status != AppointmentStatus.CONFIRMED:
                return {"success": False, "error": f"Appointment is already {appt.status.value}."}

            # Release slot
            slot = self.slots.get(appt.slot_id)
            if slot:
                slot.status = SlotStatus.AVAILABLE

            appt.status = AppointmentStatus.CANCELLED
            appt.updated_at = self._now_str()

            return {
                "success": True,
                "appointment_id": appt.id,
                "status": "CANCELLED",
                "freed_slot_id": appt.slot_id,
                "reason": reason
            }

    # Simulation / Fault injection methods for testing scenarios
    def simulate_slot_taken(self, slot_id: str):
        """Simulate concurrent booking by another user."""
        with self._lock:
            if slot_id in self.slots:
                self.slots[slot_id].status = SlotStatus.BOOKED

    def simulate_hold_expired(self, hold_id: str):
        """Manually expire a hold for testing hold expiration."""
        with self._lock:
            if hold_id in self.holds:
                self.holds[hold_id].status = HoldStatus.EXPIRED
                slot_id = self.holds[hold_id].slot_id
                if slot_id in self.slots and self.slots[slot_id].status == SlotStatus.HELD:
                    self.slots[slot_id].status = SlotStatus.AVAILABLE

    def set_service_outage(self, tool_name: str, outage: bool = True):
        """Inject 503 outage on a specific tool (e.g., search_available_slots)."""
        with self._lock:
            if outage:
                self.simulated_outages.add(tool_name)
            else:
                self.simulated_outages.discard(tool_name)
