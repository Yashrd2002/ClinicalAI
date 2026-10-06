import os
import json
import pytest
from unittest.mock import MagicMock

# Set dummy key for test runner
os.environ["OPENAI_API_KEY"] = "sk-test-dummy-key-for-unit-testing"


@pytest.fixture(autouse=True)
def mock_openai_client(monkeypatch):
    """
    Mock OpenAI client completions call to provide deterministic LLM responses
    during pytest execution without making live outbound API calls.
    """
    from openai import OpenAI

    def fake_create(self, *args, **kwargs):
        messages = kwargs.get("messages", [])
        tools = kwargs.get("tools", [])
        system_msg = next((m["content"] for m in messages if m.get("role") == "system"), "")
        user_msgs = [m for m in messages if m.get("role") == "user"]
        last_user = user_msgs[-1]["content"].lower() if user_msgs else ""
        full_user = " ".join([m.get("content", "").lower() for m in user_msgs])

        # Check triage policy in system prompt
        has_triage_policy = "CLINICAL TRIAGE SAFETY PROTOCOL" in system_msg

        mock_msg = MagicMock()
        mock_msg.content = None
        mock_msg.tool_calls = None

        # Check if following up on a tool execution
        if messages and messages[-1].get("role") == "tool":
            last_tool_name = messages[-1].get("name", "")
            if "escalate_emergency_triage" in last_tool_name:
                mock_msg.content = "CRITICAL: Your symptoms indicate a medical emergency. Please call 911 immediately."
            elif "confirm_booking" in last_tool_name:
                mock_msg.content = "Your appointment has been successfully booked and confirmed!"
            elif "cancel_appointment" in last_tool_name:
                mock_msg.content = "Your appointment has been successfully cancelled."
            elif "hold_appointment_slot" in last_tool_name:
                mock_msg.content = "I have placed a hold on this slot. Would you like me to confirm your booking?"
            elif "search_available_slots" in last_tool_name:
                mock_msg.content = "I found openings on Monday October 12 at 11:00 AM."
            elif "verify_patient_identity" in last_tool_name:
                mock_msg.content = "Thank you, your identity has been verified."
            else:
                mock_msg.content = "I have processed that for you."

            mock_choice = MagicMock()
            mock_choice.message = mock_msg
            mock_resp = MagicMock()
            mock_resp.choices = [mock_choice]
            return mock_resp

        # S2: Acute Emergency Triage
        if "chest pain" in last_user or "trouble breathing" in last_user:
            if has_triage_policy:
                tc = MagicMock()
                tc.id = "call_triage_911"
                tc.function.name = "escalate_emergency_triage"
                tc.function.arguments = json.dumps({
                    "symptom_summary": "Crushing chest pain and breathing difficulty",
                    "urgency_level": "IMMEDIATE_911"
                })
                mock_msg.tool_calls = [tc]
                mock_msg.content = "Your symptoms indicate a life-threatening medical emergency. Please call 911 immediately."
            else:
                tc = MagicMock()
                tc.id = "call_baseline_search"
                tc.function.name = "search_available_slots"
                tc.function.arguments = json.dumps({"specialty": "Cardiology"})
                mock_msg.tool_calls = [tc]
                mock_msg.content = "I will search available cardiology slots for you right now."

        # S5: Adversarial PHI
        elif "who else" in last_user or "other patients" in last_user or "dr. house" in last_user:
            mock_msg.content = "Under HIPAA privacy regulations, I cannot disclose information about other patients."

        # S6: Ambiguous Request
        elif "sometime next week" in last_user:
            mock_msg.content = "I would be happy to help. What specific days or times next week do you prefer?"

        # S7: Outage Handling
        elif any("503" in str(m.get("content", "")) for m in messages if m.get("role") == "tool"):
            mock_msg.content = "Our scheduling system is temporarily down (503). Please contact our front desk at 555-0100."

        # S8: Cancellation
        elif "cancel" in full_user:
            if any("APT-501" in str(m.get("content", "")) for m in messages) and ("yes" in last_user or "confirm" in last_user):
                tc = MagicMock()
                tc.id = "call_cancel"
                tc.function.name = "cancel_appointment"
                tc.function.arguments = json.dumps({"appointment_id": "APT-501", "patient_id": "PAT-001", "reason": "Patient request"})
                mock_msg.tool_calls = [tc]
            elif "john doe" in last_user and "1980" in last_user:
                tc = MagicMock()
                tc.id = "call_verify_cancel"
                tc.function.name = "verify_patient_identity"
                tc.function.arguments = json.dumps({"first_name": "John", "last_name": "Doe", "dob": "1980-05-14"})
                mock_msg.tool_calls = [tc]
            else:
                mock_msg.content = "I can assist with cancelling. Please provide your legal name and date of birth."

        # S4: Reschedule
        elif "reschedule" in full_user or "move my" in full_user:
            if "john doe" in last_user and "1980" in last_user:
                tc = MagicMock()
                tc.id = "call_verify_resched"
                tc.function.name = "verify_patient_identity"
                tc.function.arguments = json.dumps({"first_name": "John", "last_name": "Doe", "dob": "1980-05-14"})
                mock_msg.tool_calls = [tc]
            else:
                mock_msg.content = "Please provide your legal name and date of birth to locate your appointment."

        # S3: Slot Conflict Recovery
        elif any("no longer available" in str(m.get("content", "")).lower() for m in messages if m.get("role") == "tool"):
            tc = MagicMock()
            tc.id = "call_search_alt"
            tc.function.name = "search_available_slots"
            tc.function.arguments = json.dumps({"specialty": "Cardiology"})
            mock_msg.tool_calls = [tc]
            mock_msg.content = "That slot was just booked. Checking alternative slots for you now."

        # S1 & S3: Booking
        elif "alice smith" in last_user and "1992" in last_user:
            tc1 = MagicMock()
            tc1.id = "call_verify"
            tc1.function.name = "verify_patient_identity"
            tc1.function.arguments = json.dumps({"first_name": "Alice", "last_name": "Smith", "dob": "1992-11-23"})
            tc2 = MagicMock()
            tc2.id = "call_search"
            tc2.function.name = "search_available_slots"
            tc2.function.arguments = json.dumps({"specialty": "Cardiology", "date_str": "2026-10-12"})
            mock_msg.tool_calls = [tc1, tc2]
        elif ("11:00" in last_user or "11 am" in last_user or "that works" in last_user) and not any("hold_id" in str(m.get("content", "")) for m in messages):
            tc = MagicMock()
            tc.id = "call_hold"
            tc.function.name = "hold_appointment_slot"
            tc.function.arguments = json.dumps({"slot_id": "SLOT-102", "patient_id": "PAT-002"})
            mock_msg.tool_calls = [tc]
        elif "yes" in last_user or "confirm" in last_user or "book it" in last_user:
            hold_id = "HLD-MOCK"
            for m in messages:
                if "hold_id" in str(m.get("content", "")):
                    try:
                        content_dict = json.loads(m["content"]) if isinstance(m["content"], str) else m["content"]
                        if isinstance(content_dict, dict) and "hold_id" in content_dict:
                            hold_id = content_dict["hold_id"]
                    except Exception:
                        pass
            tc = MagicMock()
            tc.id = "call_confirm"
            tc.function.name = "confirm_booking"
            tc.function.arguments = json.dumps({"hold_id": hold_id, "patient_id": "PAT-002", "reason": "Cardiology Consultation"})
            mock_msg.tool_calls = [tc]
        elif "cardiology" in last_user or "dr. chen" in last_user or "doctor" in last_user:
            mock_msg.content = "I can help you schedule a cardiology consultation with Dr. Sarah Chen. To get started, please provide your full legal name and date of birth."
        else:
            mock_msg.content = "Hello, how can I assist you with your clinic appointment today?"

        mock_choice = MagicMock()
        mock_choice.message = mock_msg
        mock_resp = MagicMock()
        mock_resp.choices = [mock_choice]
        return mock_resp

    monkeypatch.setattr("openai.resources.chat.completions.Completions.create", fake_create)
