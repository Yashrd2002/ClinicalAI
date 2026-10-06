import json
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field

from src.ehr.database import EHRDatabase


class ToolPermissionError(Exception):
    pass


class ToolConfirmationRequiredError(Exception):
    pass


class EHRToolRegistry:
    """
    Scoped EHR and Triage Tool Registry with explicit permission matrix,
    mandatory confirmation gating, outage simulation, and audit logging.
    """
    def __init__(self, db: EHRDatabase):
        self.db = db

    def get_tool_definitions(self, policy_store: Optional[Any] = None) -> List[Dict[str, Any]]:
        """Return OpenAI-compatible function definitions, filtered by active policies."""
        all_tools = [
            {
                "type": "function",
                "function": {
                    "name": "escalate_emergency_triage",
                    "description": "CRITICAL: Call immediately when patient reports acute or life-threatening symptoms (e.g. crushing chest pain, severe shortness of breath, sudden numbness, heavy bleeding). Halts routine scheduling and provides immediate emergency guidance.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "symptom_summary": {
                                "type": "string",
                                "description": "Concise summary of reported acute symptoms."
                            },
                            "urgency_level": {
                                "type": "string",
                                "enum": ["IMMEDIATE_911", "URGENT_CARE"],
                                "description": "Clinical urgency level."
                            }
                        },
                        "required": ["symptom_summary", "urgency_level"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "verify_patient_identity",
                    "description": "Authenticate an existing patient or register a new patient using two identifiers (First & Last Name, plus Date of Birth in YYYY-MM-DD format or Phone Number). MUST be called whenever a patient introduces themselves with their name and DOB/phone before searching or holding slots.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "first_name": {"type": "string", "description": "Patient legal first name"},
                            "last_name": {"type": "string", "description": "Patient legal last name"},
                            "dob": {"type": "string", "description": "Date of Birth in YYYY-MM-DD format (convert natural language dates like '9th october, 2002' to '2002-10-09')"},
                            "phone": {"type": "string", "description": "Contact phone number"}
                        },
                        "required": ["first_name", "last_name"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "search_available_slots",
                    "description": "Query available public appointment slots by specialty, provider ID, or date. Never discloses patient identity or medical records.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "specialty": {
                                "type": "string",
                                "description": "Medical specialty (e.g. Cardiology, Primary Care, Orthopedics)"
                            },
                            "provider_id": {
                                "type": "string",
                                "description": "Specific provider ID (optional)"
                            },
                            "date_str": {
                                "type": "string",
                                "description": "Date to filter in YYYY-MM-DD format (optional)"
                            }
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "hold_appointment_slot",
                    "description": "Reserve a slot temporarily (with TTL expiration) for a verified patient while finalizing booking details. Prevents double-booking.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "slot_id": {"type": "string", "description": "ID of slot to hold"},
                            "patient_id": {"type": "string", "description": "Verified patient ID"}
                        },
                        "required": ["slot_id", "patient_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "confirm_booking",
                    "description": "Convert an active held slot into a confirmed clinic appointment. Requires verified patient ID and explicit patient confirmation.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "hold_id": {"type": "string", "description": "Active hold ID from hold_appointment_slot"},
                            "patient_id": {"type": "string", "description": "Verified patient ID"},
                            "reason": {"type": "string", "description": "Reason for clinical visit"}
                        },
                        "required": ["hold_id", "patient_id", "reason"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_patient_appointments",
                    "description": "Retrieve existing scheduled appointments for the verified patient. Strictly requires verified identity.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "patient_id": {"type": "string", "description": "Verified patient ID"}
                        },
                        "required": ["patient_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "reschedule_appointment",
                    "description": "Atomically reschedule an existing appointment to a new available slot. Requires verified patient and explicit confirmation.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "appointment_id": {"type": "string", "description": "ID of existing appointment to reschedule"},
                            "new_slot_id": {"type": "string", "description": "ID of new slot"},
                            "patient_id": {"type": "string", "description": "Verified patient ID"}
                        },
                        "required": ["appointment_id", "new_slot_id", "patient_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "cancel_appointment",
                    "description": "Cancel an existing scheduled appointment and release slot back to availability. Requires verified patient and explicit confirmation.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "appointment_id": {"type": "string", "description": "ID of appointment to cancel"},
                            "patient_id": {"type": "string", "description": "Verified patient ID"},
                            "reason": {"type": "string", "description": "Reason for cancellation"}
                        },
                        "required": ["appointment_id", "patient_id"]
                    }
                }
            }
        ]

        if policy_store is not None:
            triage_enabled = getattr(policy_store, "tunable_policies", {}).get("triage_screening", {}).get("enabled", False)
            if not triage_enabled:
                all_tools = [t for t in all_tools if t["function"]["name"] != "escalate_emergency_triage"]

        return all_tools

    def execute_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        is_verified: bool,
        verified_patient_id: Optional[str] = None,
        is_confirmed_by_user: bool = False
    ) -> Dict[str, Any]:
        """
        Execute tool with permission gating, explicit confirmation enforcement,
        simulated outage checking, and audit logging.
        """
        # 1. Check for simulated service outages (e.g. S7)
        if tool_name in self.db.simulated_outages:
            err_msg = "SERVICE_UNAVAILABLE: The clinic scheduling service is temporarily unreachable (503)."
            self.db.log_audit(tool_name, arguments, {"status": 503, "error": err_msg}, success=False, error_message=err_msg)
            return {"success": False, "status": 503, "error": err_msg}

        # 2. Permission & Confirmation Matrix Enforcement
        try:
            if tool_name == "escalate_emergency_triage":
                result = self._execute_escalate_emergency_triage(arguments, verified_patient_id)
            elif tool_name == "verify_patient_identity":
                result = self._execute_verify_patient_identity(arguments)
            elif tool_name == "search_available_slots":
                result = self._execute_search_available_slots(arguments)
            elif tool_name == "hold_appointment_slot":
                if not is_verified:
                    raise ToolPermissionError("Permission Denied: Patient identity must be verified before holding a slot.")
                req_patient_id = arguments.get("patient_id")
                if req_patient_id != verified_patient_id:
                    raise ToolPermissionError("Permission Denied: Patient ID mismatch with verified identity.")
                result = self.db.create_hold(arguments["slot_id"], req_patient_id)
            elif tool_name == "confirm_booking":
                if not is_verified:
                    raise ToolPermissionError("Permission Denied: Patient identity must be verified before booking an appointment.")
                req_patient_id = arguments.get("patient_id")
                if req_patient_id != verified_patient_id:
                    raise ToolPermissionError("Permission Denied: Patient ID mismatch with verified identity.")
                if not is_confirmed_by_user:
                    raise ToolConfirmationRequiredError("Confirmation Required: Explicit confirmation is required from the patient before confirming the appointment.")
                result = self.db.confirm_booking(arguments["hold_id"], req_patient_id, arguments.get("reason", "Consultation"))
            elif tool_name == "get_patient_appointments":
                if not is_verified:
                    raise ToolPermissionError("Permission Denied: Patient identity must be verified before accessing appointment records.")
                req_patient_id = arguments.get("patient_id")
                if req_patient_id != verified_patient_id:
                    raise ToolPermissionError("Permission Denied: Patient ID mismatch with verified identity.")
                appts = self.db.get_patient_appointments(req_patient_id)
                result = {"success": True, "appointments": appts}
            elif tool_name == "reschedule_appointment":
                if not is_verified:
                    raise ToolPermissionError("Permission Denied: Patient identity must be verified before rescheduling.")
                req_patient_id = arguments.get("patient_id")
                if req_patient_id != verified_patient_id:
                    raise ToolPermissionError("Permission Denied: Patient ID mismatch with verified identity.")
                if not is_confirmed_by_user:
                    raise ToolConfirmationRequiredError("Confirmation Required: Explicit confirmation is required before rescheduling.")
                result = self.db.reschedule_appointment(arguments["appointment_id"], arguments["new_slot_id"], req_patient_id)
            elif tool_name == "cancel_appointment":
                if not is_verified:
                    raise ToolPermissionError("Permission Denied: Patient identity must be verified before cancelling.")
                req_patient_id = arguments.get("patient_id")
                if req_patient_id != verified_patient_id:
                    raise ToolPermissionError("Permission Denied: Patient ID mismatch with verified identity.")
                if not is_confirmed_by_user:
                    raise ToolConfirmationRequiredError("Confirmation Required: Explicit confirmation is required before cancelling the appointment.")
                result = self.db.cancel_appointment(arguments["appointment_id"], req_patient_id, arguments.get("reason", "Patient request"))
            else:
                result = {"success": False, "error": f"Unknown tool: {tool_name}"}

            success = result.get("success", True)
            self.db.log_audit(
                tool_name=tool_name,
                parameters=arguments,
                result=result,
                success=success,
                patient_id=verified_patient_id,
                error_message=result.get("error") if not success else None
            )
            return result

        except ToolPermissionError as e:
            err_dict = {"success": False, "error": str(e), "code": "PERMISSION_DENIED"}
            self.db.log_audit(tool_name, arguments, err_dict, success=False, patient_id=verified_patient_id, error_message=str(e))
            return err_dict
        except ToolConfirmationRequiredError as e:
            err_dict = {"success": False, "error": str(e), "code": "CONFIRMATION_REQUIRED"}
            self.db.log_audit(tool_name, arguments, err_dict, success=False, patient_id=verified_patient_id, error_message=str(e))
            return err_dict
        except Exception as e:
            err_dict = {"success": False, "error": f"Internal tool execution error: {str(e)}"}
            self.db.log_audit(tool_name, arguments, err_dict, success=False, patient_id=verified_patient_id, error_message=str(e))
            return err_dict

    def _execute_escalate_emergency_triage(self, args: Dict[str, Any], patient_id: Optional[str]) -> Dict[str, Any]:
        return {
            "success": True,
            "action": "EMERGENCY_ESCALATION",
            "symptom_summary": args.get("symptom_summary"),
            "urgency_level": args.get("urgency_level", "IMMEDIATE_911"),
            "guidance": "EMERGENCY DIRECTIVE: Direct patient immediately to hang up and call 911 or proceed to the nearest emergency department. DO NOT schedule routine clinic appointment."
        }

    def _execute_verify_patient_identity(self, args: Dict[str, Any]) -> Dict[str, Any]:
        f_name = args.get("first_name", "")
        l_name = args.get("last_name", "")
        dob = args.get("dob")
        phone = args.get("phone")

        if not f_name or not l_name:
            return {"success": False, "verified": False, "error": "Both first name and last name are required."}
        if not dob and not phone:
            return {"success": False, "verified": False, "error": "A second identifier (Date of Birth or Phone Number) is required."}

        # 1. Check if patient exists by name
        existing_by_name = any(
            p.first_name.lower() == f_name.strip().lower() and p.last_name.lower() == l_name.strip().lower()
            for p in self.db.patients.values()
        )

        patient = self.db.verify_patient(f_name, l_name, dob, phone)
        if patient:
            return {
                "success": True,
                "verified": True,
                "patient_id": patient.id,
                "patient_name": f"{patient.first_name} {patient.last_name}",
                "message": "Patient identity successfully verified."
            }
        elif existing_by_name:
            # Existing patient name matched, but DOB / phone was incorrect -> Authentication failed
            return {
                "success": False,
                "verified": False,
                "error": "Authentication failed. The provided date of birth or phone number does not match our clinic records."
            }
        else:
            # Completely new patient with valid 2 identifiers -> Register new patient profile
            new_patient = self.db.register_patient(f_name, l_name, dob, phone)
            return {
                "success": True,
                "verified": True,
                "is_new_patient": True,
                "patient_id": new_patient.id,
                "patient_name": f"{new_patient.first_name} {new_patient.last_name}",
                "message": f"New patient intake verified and registered ({new_patient.id})."
            }

    def _execute_search_available_slots(self, args: Dict[str, Any]) -> Dict[str, Any]:
        specialty = args.get("specialty")
        provider_id = args.get("provider_id")
        date_str = args.get("date_str")
        slots = self.db.search_available_slots(specialty, provider_id, date_str)
        return {
            "success": True,
            "count": len(slots),
            "slots": slots
        }
