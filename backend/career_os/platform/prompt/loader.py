from pathlib import Path


def load_prompt(worker_id: str, name: str = "default") -> str:
    repo_root = Path(__file__).resolve().parents[4]
    path = repo_root / "backend" / "career_os" / "platform" / "prompt" / worker_id / f"{name}.tmpl"
    if not path.exists():
        return f"You are the {worker_id} worker."
    return path.read_text(encoding="utf-8")
