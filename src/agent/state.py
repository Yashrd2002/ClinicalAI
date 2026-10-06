from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class SchedulingState(BaseModel):
    """
    Structured dialogue and clinical scheduling state across multi-turn interactions.
    Explicitly tracks clinical triage urgency, verification status, and slot hold lifecycle.
    """
    # Patient & Authentication
    patient_id: Optional[str] = None
    patient_name: Optional[str] = None
    identity_verified: bool = False

    # Clinical Intent & Specialty Matching
    intent: Optional[str] = None  # "BOOK_NEW", "RESCHEDULE", "CANCEL", "INQUIRY", "EMERGENCY"
    provider: Optional[str] = None
    specialty: Optional[str] = None
    requested_date: Optional[str] = None
    requested_time: Optional[str] = None

    # Slot Lifecycle & Transactional State
    candidate_slots: List[Dict[str, Any]] = Field(default_factory=list)
    selected_slot: Optional[str] = None
    hold_id: Optional[str] = None
    hold_expires_at: Optional[str] = None
    confirmation_status: str = "PENDING"  # "PENDING", "REQUESTED", "CONFIRMED", "DECLINED"
    appointment_id: Optional[str] = None

    # Critical Clinical Triage & Safety
    emergency_status: str = "NONE"  # "NONE", "SUSPECTED", "ESCALATED"
    emergency_summary: Optional[str] = None

    # Audit & Tool Execution Trace
    last_tool_call: Optional[str] = None
    last_tool_result: Optional[Dict[str, Any]] = None
    conversation_turn: int = 0
    messages: List[Dict[str, Any]] = Field(default_factory=list)
    executed_tools_history: List[str] = Field(default_factory=list)

    def record_turn(self, role: str, content: str):
        if role == "user":
            self.conversation_turn += 1
        self.messages.append({"role": role, "content": content})

    def record_tool_execution(self, tool_name: str, result: Dict[str, Any]):
        self.last_tool_call = tool_name
        self.last_tool_result = result
        self.executed_tools_history.append(tool_name)
