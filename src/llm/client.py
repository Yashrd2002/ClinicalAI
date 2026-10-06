import os
import json
import time
import random
from typing import Dict, Any, List, Optional
from pydantic import BaseModel
from dotenv import load_dotenv

# Automatically load environment variables from .env
load_dotenv()


class ToolCall(BaseModel):
    id: str
    name: str
    arguments: Dict[str, Any]


class LLMResponse(BaseModel):
    content: Optional[str] = None
    tool_calls: List[ToolCall] = []


class LLMClient:
    """
    Production LLM Client utilizing OpenAI Chat Completions API with structured tool calling,
    resilient exponential backoff retry with jitter, and clinical emergency circuit breaker.
    Configurable via .env or environment variables (OPENAI_API_KEY, LLM_MODEL, OPENAI_BASE_URL).
    """
    def __init__(self, model: Optional[str] = None, base_url: Optional[str] = None):
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.base_url = base_url or os.getenv("OPENAI_BASE_URL")
        self.model = model or os.getenv("LLM_MODEL", "gpt-4o-mini")

        if not self.api_key or self.api_key.strip() in ["your_openai_api_key_here", "sk-..."]:
            raise ValueError(
                "OPENAI_API_KEY is not configured. Please add your OpenAI API key to the .env file:\n"
                "  OPENAI_API_KEY=sk-...\n"
                "or export it in your shell environment."
            )

        from openai import OpenAI
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url if self.base_url else None
        )

    def generate_reply(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        system_instruction: str,
        max_retries: int = 3
    ) -> LLMResponse:
        """
        Generate completion and structured tool calls with exponential backoff retry.
        Fails safe if a downstream OpenAI outage occurs during an acute clinical emergency.
        """
        formatted_messages = [{"role": "system", "content": system_instruction}] + messages
        kwargs = {
            "model": self.model,
            "messages": formatted_messages,
            "temperature": 0.0
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        last_error = None
        for attempt in range(1, max_retries + 1):
            try:
                response = self.client.chat.completions.create(**kwargs)
                msg = response.choices[0].message

                tool_calls = []
                if msg.tool_calls:
                    for tc in msg.tool_calls:
                        try:
                            args = json.loads(tc.function.arguments) if tc.function.arguments else {}
                        except json.JSONDecodeError:
                            args = {}
                        tool_calls.append(ToolCall(
                            id=tc.id,
                            name=tc.function.name,
                            arguments=args
                        ))

                return LLMResponse(content=msg.content, tool_calls=tool_calls)

            except Exception as e:
                last_error = e
                # Check for rate limit or transient connection errors
                if attempt < max_retries:
                    backoff = (0.5 * (2 ** (attempt - 1))) + random.uniform(0.05, 0.25)
                    time.sleep(backoff)
                else:
                    break

        # Emergency Fail-Safe Circuit Breaker:
        # If the LLM service is completely unavailable, check if the patient is experiencing an acute emergency
        latest_user_text = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                latest_user_text = str(m.get("content", "")).lower()
                break

        emergency_triggers = [
            "chest pain", "shortness of breath", "cannot breathe", "can't breathe",
            "heart attack", "stroke", "unconscious", "severe bleeding", "passing out",
            "fainting", "severe chest pressure"
        ]
        if any(trig in latest_user_text for trig in emergency_triggers):
            # Deterministically trigger emergency escalation tool call without crashing
            return LLMResponse(
                content="EMERGENCY ALERT: You are describing symptoms of a potential medical emergency. Please hang up and immediately call 911 or proceed to the nearest emergency room. I am alerting the triage desk immediately.",
                tool_calls=[
                    ToolCall(
                        id="fail_safe_emergency_call",
                        name="escalate_emergency_triage",
                        arguments={
                            "symptom_summary": f"Automated fail-safe emergency triage escalation: {latest_user_text[:120]}",
                            "severity": "CRITICAL"
                        }
                    )
                ]
            )

        raise RuntimeError(f"LLM API execution failed after {max_retries} attempts: {str(last_error)}") from last_error
