import json
from pathlib import Path


def find_project_root(start: Path) -> Path:
    """
    Walk upwards until a project root marker is found.
    """
    markers = {"pyproject.toml", "requirements.txt", ".git"}

    current = start
    while current != current.parent:
        if any((current / marker).exists() for marker in markers):
            return current
        current = current.parent

    raise RuntimeError("Project root could not be determined")


def bootstrap_env_from_json(
    json_filename: str = "creds.json",
    env_filename: str = ".env",
    overwrite: bool = False,
    verbose: bool = True,
    root_override: Path | None = None,
) -> None:
    """
    Bootstrap a .env file from a JSON creds file located at project root.
    """

    root_dir = root_override or find_project_root(Path(__file__).resolve())

    json_path = root_dir / json_filename
    env_path = root_dir / env_filename

    if env_path.exists() and not overwrite:
        if verbose:
            print("[env-bootstrap] .env already exists -> skipping")
        return

    if not json_path.exists():
        if verbose:
            print(f"[env-bootstrap] No creds JSON found at {json_path}")
        return

    with json_path.open("r") as f:
        creds: dict[str, str] = json.load(f)

    if not isinstance(creds, dict):
        raise ValueError("Credentials JSON must be a dictionary")

    lines = []

    if verbose:
        print("[env-bootstrap] Writing environment variables:")

    for key, value in creds.items():
        if value is None:
            continue

        value = str(value)
        lines.append(f"{key}={value}")

        if verbose:
            print(f"  {key}={value}")

    env_path.write_text("\n".join(lines) + "\n")

    if verbose:
        print(f"[env-bootstrap] .env created at {env_path}")
