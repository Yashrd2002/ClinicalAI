import os
import sys
import time
from typing import Dict, Any, List, Optional
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

from src.ehr.database import EHRDatabase
from src.agent.dialogue_manager import DialogueManager
from src.agent.policies import PolicyStore
from src.llm.client import LLMClient
from src.optimizer.loop import ClosedLoopOptimizer, ClosedLoopResult
from src.evals.runner import EvaluationRunner

app = FastAPI(title="Clinical Scheduling Agent & Evaluation Dashboard", version="1.0.0")

# Global in-memory clinic system and agent
ehr_db = EHRDatabase()
policy_store = PolicyStore()
policy_store.tunable_policies["triage_screening"]["enabled"] = False
policy_store.applied_patches = []

server_start_time = time.time()
metrics_tracker = {
    "total_requests": 0,
    "successful_turns": 0,
    "failed_turns": 0,
    "total_latency_ms": 0.0,
    "emergency_escalations": 0,
    "verified_sessions": 0
}

try:
    llm_client = LLMClient()
except Exception:
    llm_client = None

dialogue_manager = DialogueManager(db=ehr_db, llm_client=llm_client, policy_store=policy_store)


class ChatRequest(BaseModel):
    message: str


@app.get("/api/health")
def health_check():
    return {
        "status": "healthy",
        "llm_configured": llm_client is not None,
        "model": llm_client.model if llm_client else "NOT_CONFIGURED"
    }


@app.get("/api/metrics")
def get_metrics():
    avg_latency = (
        round(metrics_tracker["total_latency_ms"] / max(1, metrics_tracker["successful_turns"]), 2)
    )
    uptime_sec = round(time.time() - server_start_time, 1)
    return {
        "uptime_seconds": uptime_sec,
        "total_requests": metrics_tracker["total_requests"],
        "successful_turns": metrics_tracker["successful_turns"],
        "failed_turns": metrics_tracker["failed_turns"],
        "average_latency_ms": avg_latency,
        "emergency_escalations": metrics_tracker["emergency_escalations"],
        "verified_sessions": metrics_tracker["verified_sessions"],
        "active_appointments": len(ehr_db.appointments),
        "active_holds": sum(1 for h in ehr_db.holds.values() if h.status.value == "ACTIVE"),
        "ehr_audit_entries": len(ehr_db.audit_log),
        "llm_model": llm_client.model if llm_client else "N/A"
    }


@app.post("/api/chat")
def chat_turn(req: ChatRequest):
    global dialogue_manager, llm_client
    metrics_tracker["total_requests"] += 1
    t0 = time.time()

    if not llm_client:
        try:
            llm_client = LLMClient()
            dialogue_manager.llm = llm_client
        except ValueError as e:
            metrics_tracker["failed_turns"] += 1
            raise HTTPException(status_code=400, detail=str(e))

    user_msg = req.message.strip()
    if not user_msg:
        metrics_tracker["failed_turns"] += 1
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    try:
        reply = dialogue_manager.process_turn(user_msg)
        elapsed_ms = (time.time() - t0) * 1000.0
        metrics_tracker["successful_turns"] += 1
        metrics_tracker["total_latency_ms"] += elapsed_ms

        if dialogue_manager.state.emergency_status in ["ESCALATED", "EMERGENCY"]:
            metrics_tracker["emergency_escalations"] += 1
        if dialogue_manager.state.identity_verified:
            metrics_tracker["verified_sessions"] += 1

        return {
            "reply": reply,
            "latency_ms": round(elapsed_ms, 2),
            "state": dialogue_manager.state.model_dump(),
            "last_tool": dialogue_manager.state.last_tool_call,
            "last_tool_result": dialogue_manager.state.last_tool_result,
            "emergency_status": dialogue_manager.state.emergency_status,
            "identity_verified": dialogue_manager.state.identity_verified,
            "confirmation_status": dialogue_manager.state.confirmation_status
        }
    except Exception as e:
        metrics_tracker["failed_turns"] += 1
        raise HTTPException(status_code=500, detail=f"Dialogue processing failed: {str(e)}")


@app.get("/api/state")
def get_state():
    return {
        "state": dialogue_manager.state.model_dump(),
        "stats": {
            "total_patients": len(ehr_db.patients),
            "total_slots": len(ehr_db.slots),
            "total_appointments": len(ehr_db.appointments),
            "total_audit_logs": len(ehr_db.audit_log),
            "active_holds": sum(1 for h in ehr_db.holds.values() if h.status.value == "ACTIVE")
        }
    }


@app.post("/api/reset")
def reset_system():
    global ehr_db, dialogue_manager
    ehr_db.seed_database()
    dialogue_manager.reset_state()
    return {"success": True, "message": "EHR database and dialogue state reset to clean baseline."}


@app.get("/api/ehr")
def get_ehr_data():
    return {
        "providers": [p.model_dump() for p in ehr_db.providers.values()],
        "patients": [p.model_dump() for p in ehr_db.patients.values()],
        "slots": [s.model_dump() for s in ehr_db.slots.values()],
        "appointments": [a.model_dump() for a in ehr_db.appointments.values()],
        "holds": [h.model_dump() for h in ehr_db.holds.values()],
        "audit_log": [log.model_dump() for log in reversed(ehr_db.audit_log[-50:])]
    }


@app.get("/api/policies")
def get_policies():
    return {
        "tunable_policies": policy_store.tunable_policies,
        "applied_patches": policy_store.applied_patches,
        "prompt_instructions": policy_store.get_prompt_policy_instructions()
    }


@app.post("/api/eval/run")
def run_evaluation_loop():
    global llm_client
    if not llm_client:
        try:
            llm_client = LLMClient()
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    try:
        # Create dedicated clean baseline policy store for reproducibility
        eval_policy_store = PolicyStore(config_path="/tmp/clinical_eval_policies.json")
        eval_policy_store.tunable_policies["triage_screening"]["enabled"] = False
        eval_policy_store.applied_patches = []

        optimizer = ClosedLoopOptimizer(llm_client=llm_client, policy_store=eval_policy_store)
        loop_result: ClosedLoopResult = optimizer.run_optimization_cycle()

        # If patch was accepted, also sync to server's live policy store
        if loop_result.decision == "ACCEPTED" and loop_result.candidate_patch:
            try:
                policy_store.apply_patch(loop_result.candidate_patch)
            except Exception:
                pass

        return {
            "decision": loop_result.decision,
            "decision_reason": loop_result.decision_reason,
            "target_scenario_id": loop_result.target_scenario_id,
            "candidate_patch": loop_result.candidate_patch.model_dump() if loop_result.candidate_patch else None,
            "score_delta": loop_result.score_delta,
            "pass_rate_delta": loop_result.pass_rate_delta,
            "critical_failures_delta": loop_result.critical_failures_delta,
            "regressions": loop_result.regressions,
            "baseline_summary": loop_result.baseline_summary.model_dump(),
            "shadow_summary": loop_result.shadow_summary.model_dump() if loop_result.shadow_summary else None
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Closed-loop optimization failed: {str(e)}")


# Mount static assets
static_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static")
os.makedirs(static_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/")
def serve_index():
    index_path = os.path.join(static_dir, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return JSONResponse({"message": "Clinical Agent API is running. Static UI not yet created."})
