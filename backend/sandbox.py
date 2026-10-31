import subprocess
import uuid
from pathlib import Path

IMAGE = "codewarden-sandbox"
TIMEOUT = 60 

def run_in_sandbox(workdir: Path, command: list[str]) -> tuple[int, str]:
    """Mount workdir read-only at /work, run command, return (exit_code, output)."""
    name = f"codewarden-{uuid.uuid4().hex[:8]}"
    docker_cmd = [
        "docker", "run", "--rm", "--name", name,
        "--network", "none",                 
        "--cpus", "1", "--memory", "512m", "--pids-limit", "128",
        "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
        "--read-only", "--tmpfs", "/tmp",   
        "--user", "1000:1000",               
        "-e", "PYTHONDONTWRITEBYTECODE=1",
        "-v", f"{workdir.resolve()}:/work:ro",
        "-w", "/work",
        IMAGE, "timeout", str(TIMEOUT), *command,
    ]
    try:
        proc = subprocess.run(docker_cmd, capture_output=True, text=True, timeout=TIMEOUT + 30)
    except subprocess.TimeoutExpired:
        subprocess.run(["docker", "kill", name], capture_output=True)
        return 124, "Sandbox timed out."
    return proc.returncode, proc.stdout + proc.stderr

def pytest_in_sandbox(workdir: Path, *args: str) -> tuple[int, str]:
    return run_in_sandbox(workdir, ["python", "-m", "pytest", "-q", "-p", "no:cacheprovider", *args])