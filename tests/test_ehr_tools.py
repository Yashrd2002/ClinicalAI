import pytest
from src.ehr.database import EHRDatabase
from src.ehr.models import SlotStatus, AppointmentStatus, HoldStatus
from src.tools.ehr_tools import EHRToolRegistry, ToolPermissionError, ToolConfirmationRequiredError


def test_ehr_seed_and_verify():
    db = EHRDatabase()
    # 2 identifiers: First+Last and DOB
    p = db.verify_patient("John", "Doe", dob="1980-05-14")
    assert p is not None
    assert p.id == "PAT-001"

    # Failing verification (wrong DOB)
    p_fail = db.verify_patient("John", "Doe", dob="1999-01-01")
    assert p_fail is None

    # Missing second identifier
    p_missing = db.verify_patient("John", "Doe")
    assert p_missing is None


def test_search_and_hold():
    db = EHRDatabase()
    registry = EHRToolRegistry(db)

    # Search cardiology slots
    res = registry.execute_tool("search_available_slots", {"specialty": "Cardiology"}, is_verified=False)
    assert res["success"] is True
    assert len(res["slots"]) > 0
    slot_id = res["slots"][0]["slot_id"]

    # Holding without verification must fail with PERMISSION_DENIED
    hold_unverified = registry.execute_tool(
        "hold_appointment_slot",
        {"slot_id": slot_id, "patient_id": "PAT-001"},
        is_verified=False
    )
    assert hold_unverified["success"] is False
    assert hold_unverified["code"] == "PERMISSION_DENIED"

    # Holding with verification succeeds
    hold_verified = registry.execute_tool(
        "hold_appointment_slot",
        {"slot_id": slot_id, "patient_id": "PAT-001"},
        is_verified=True,
        verified_patient_id="PAT-001"
    )
    assert hold_verified["success"] is True
    assert "hold_id" in hold_verified
    assert db.slots[slot_id].status == SlotStatus.HELD


def test_booking_confirmation_and_db_parity():
    db = EHRDatabase()
    registry = EHRToolRegistry(db)

    # Verify patient
    v_res = registry.execute_tool("verify_patient_identity", {"first_name": "Alice", "last_name": "Smith", "dob": "1992-11-23"}, is_verified=False)
    assert v_res["verified"] is True
    pid = v_res["patient_id"]

    # Hold slot
    slots = registry.execute_tool("search_available_slots", {"specialty": "Primary Care"}, is_verified=True, verified_patient_id=pid)
    slot_id = slots["slots"][0]["slot_id"]
    h_res = registry.execute_tool("hold_appointment_slot", {"slot_id": slot_id, "patient_id": pid}, is_verified=True, verified_patient_id=pid)
    hold_id = h_res["hold_id"]

    # Booking without explicit user confirmation should fail
    unconfirmed = registry.execute_tool("confirm_booking", {"hold_id": hold_id, "patient_id": pid, "reason": "Checkup"}, is_verified=True, verified_patient_id=pid, is_confirmed_by_user=False)
    assert unconfirmed["success"] is False
    assert unconfirmed["code"] == "CONFIRMATION_REQUIRED"

    # Confirm booking with user confirmation
    book_res = registry.execute_tool("confirm_booking", {"hold_id": hold_id, "patient_id": pid, "reason": "Annual checkup"}, is_verified=True, verified_patient_id=pid, is_confirmed_by_user=True)
    assert book_res["success"] is True
    appt_id = book_res["appointment_id"]

    # Check DB state parity
    assert appt_id in db.appointments
    assert db.appointments[appt_id].status == AppointmentStatus.CONFIRMED
    assert db.slots[slot_id].status == SlotStatus.BOOKED
    assert db.holds[hold_id].status == HoldStatus.CONVERTED


def test_emergency_triage_tool():
    db = EHRDatabase()
    registry = EHRToolRegistry(db)
    res = registry.execute_tool(
        "escalate_emergency_triage",
        {"symptom_summary": "crushing chest pain and difficulty breathing", "urgency_level": "IMMEDIATE_911"},
        is_verified=False
    )
    assert res["success"] is True
    assert res["action"] == "EMERGENCY_ESCALATION"
    assert "call 911" in res["guidance"]


def test_simulated_service_outage():
    db = EHRDatabase()
    registry = EHRToolRegistry(db)
    db.set_service_outage("search_available_slots", True)

    res = registry.execute_tool("search_available_slots", {"specialty": "Cardiology"}, is_verified=False)
    assert res["success"] is False
    assert res["status"] == 503
    assert "SERVICE_UNAVAILABLE" in res["error"]
