#!/usr/bin/env python3
"""
Aegis Clinical - Server & Web UI Launcher
Launches the FastAPI backend serving both REST API endpoints and the Interactive UI Dashboard.
"""

import sys
import os

# Automatically use project virtual environment if running outside of it
venv_python = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".venv", "bin", "python")
if os.path.exists(venv_python) and sys.executable != venv_python:
    os.execv(venv_python, [venv_python] + sys.argv)

import uvicorn
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich import box
from dotenv import load_dotenv

load_dotenv()
console = Console()


def print_server_banner(host: str, port: int):
    banner = Text()
    banner.append("🏥 AEGIS CLINICAL WEB APPLICATION & REST API\n", style="bold cyan")
    banner.append("Safe Multi-Turn Scheduling • Dual State Evaluation • Closed-Loop Optimizer\n\n", style="dim")
    banner.append("🌐 Web Dashboard:  ", style="bold white")
    banner.append(f"http://{host}:{port}\n", style="bold green underline")
    banner.append("📚 Interactive API: ", style="bold white")
    banner.append(f"http://{host}:{port}/docs\n", style="bold cyan underline")
    banner.append("⚡ Health Check:    ", style="bold white")
    banner.append(f"http://{host}:{port}/api/health\n\n", style="bold yellow")
    banner.append("Press Ctrl+C to stop the server.", style="dim italic")

    console.print(Panel(banner, box=box.ROUNDED, border_style="cyan"))


import socket


def is_port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex((host, port)) == 0


def find_available_port(start_port: int = 8000, host: str = "127.0.0.1") -> int:
    port = start_port
    while is_port_in_use(port, host):
        port += 1
    return port


if __name__ == "__main__":
    host = os.getenv("HOST", "127.0.0.1")
    requested_port = int(os.getenv("PORT", 8000))
    port = find_available_port(requested_port, host)

    if port != requested_port:
        console.print(f"[yellow]Notice: Port {requested_port} is already in use. Switched to available port {port}.[/yellow]\n")

    print_server_banner(host, port)
    uvicorn.run("src.server.app:app", host=host, port=port, reload=True)

