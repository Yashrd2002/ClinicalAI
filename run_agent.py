#!/usr/bin/env python3
"""
Clinical Appointment Scheduling Agent - Interactive Terminal Dialogue
Run an interactive multi-turn conversation with the clinical scheduling agent.
Powered by LLM via OpenAI API / .env configuration.
Supports state inspection (/state), policy inspection (/policy), and /reset.
"""

import sys
import os

# Automatically use project virtual environment if running outside of it
venv_python = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".venv", "bin", "python")
if os.path.exists(venv_python) and sys.executable != venv_python:
    os.execv(venv_python, [venv_python] + sys.argv)

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table
from rich.text import Text
from rich import box
from dotenv import load_dotenv

from src.ehr.database import EHRDatabase
from src.agent.dialogue_manager import DialogueManager
from src.agent.policies import PolicyStore
from src.llm.client import LLMClient

load_dotenv()
console = Console()


def print_banner(model_name: str):
    banner = Text()
    banner.append("🩺 CLINICAL APPOINTMENT SCHEDULING ASSISTANT\n", style="bold cyan")
    banner.append("Cardiology • Primary Care • Orthopedics | Safe, Grounded Multi-Turn Dialogue\n", style="dim")
    banner.append(f"Active LLM Engine: [bold green]{model_name}[/bold green]\n", style="italic")
    banner.append("Commands: '/state' to view state, '/policy' to view rules, '/reset' to start over, 'exit' to quit.", style="dim cyan")
    console.print(Panel(banner, box=box.ROUNDED, border_style="cyan"))


def display_state(dm: DialogueManager):
    table = Table(title="🔍 CURRENT STRUCTURED SCHEDULING STATE", box=box.ROUNDED)
    table.add_column("State Field", style="bold yellow", width=26)
    table.add_column("Current Value", style="white", width=46)

    s = dm.state
    table.add_row("Conversation Turn", str(s.conversation_turn))
    table.add_row("Patient ID", str(s.patient_id or "Unverified"))
    table.add_row("Patient Name", str(s.patient_name or "Unverified"))
    table.add_row("Identity Verified?", "[bold green]YES[/bold green]" if s.identity_verified else "[bold red]NO[/bold red]")
    table.add_row("Emergency Status", f"[{'bold red' if s.emergency_status == 'ESCALATED' else 'green'}]{s.emergency_status}[/]")
    table.add_row("Selected Slot ID", str(s.selected_slot or "None"))
    table.add_row("Active Hold ID", str(s.hold_id or "None"))
    table.add_row("Confirmation Status", str(s.confirmation_status))
    table.add_row("Confirmed Appointment ID", str(s.appointment_id or "None"))
    table.add_row("Last Executed Tool", str(s.last_tool_call or "None"))
    table.add_row("Total Tools History", ", ".join(s.executed_tools_history) if s.executed_tools_history else "None")

    console.print(table)


def display_policies(policy_store: PolicyStore):
    table = Table(title="📜 ACTIVE CLINICAL POLICIES & GUARDRAILS", box=box.ROUNDED)
    table.add_column("Policy / Invariant", style="bold cyan", width=30)
    table.add_column("Status / Guidance", style="white", width=46)

    table.add_row("Core Invariant: Emergency Routing", "[bold red]IMMUTABLE - Halts booking on red flags[/bold red]")
    table.add_row("Core Invariant: PHI Auth", "[bold red]IMMUTABLE - 2-ID authentication required[/bold red]")
    table.add_row("Core Invariant: DB Parity", "[bold red]IMMUTABLE - Zero hallucinated bookings[/bold red]")
    
    triage = policy_store.tunable_policies.get("triage_screening", {})
    triage_status = "[bold green]ACTIVE (Screening enabled)[/bold green]" if triage.get("enabled") else "[yellow]BASELINE (Screening disabled)[/yellow]"
    table.add_row("Tunable: Triage Screening", triage_status)
    
    table.add_row("Applied Patches Count", str(len(policy_store.applied_patches)))
    console.print(table)


def main():
    try:
        llm = LLMClient()
    except ValueError as e:
        console.print(Panel(f"[bold red]Configuration Error:[/bold red]\n{str(e)}", title="Missing API Key", border_style="red"))
        sys.exit(1)

    print_banner(llm.model)

    db = EHRDatabase()
    policy_store = PolicyStore()
    dm = DialogueManager(db=db, llm_client=llm, policy_store=policy_store)

    console.print("[dim]Patient interaction session started. Type a greeting or inquiry (e.g. 'Hi, I need an appointment with Dr. Chen').[/dim]\n")

    while True:
        try:
            user_input = Prompt.ask("[bold green]Patient[/bold green]").strip()
            if not user_input:
                continue

            if user_input.lower() in ["exit", "quit", "q"]:
                console.print("\n[dim]Session terminated. Goodbye![/dim]")
                break

            if user_input.lower() == "/state":
                display_state(dm)
                continue

            if user_input.lower() == "/policy":
                display_policies(policy_store)
                continue

            if user_input.lower() == "/reset":
                db.seed_database()
                dm.reset_state()
                console.print("[yellow]System state reset to initial clean baseline.[/yellow]\n")
                continue

            # Process turn through DialogueManager
            agent_reply = dm.process_turn(user_input)

            # Display tool execution log if tools were invoked
            if dm.state.last_tool_call:
                console.print(f"[dim cyan]  ⚡ [Tool Executed: {dm.state.last_tool_call}][/dim cyan]")

            # Display agent response
            console.print(f"[bold blue]Clinical Agent[/bold blue]: {agent_reply}\n")

        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Session interrupted. Goodbye![/dim]")
            break


if __name__ == "__main__":
    main()
