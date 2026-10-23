"""Create a private persistent student signing key without printing its contents."""
from pathlib import Path
import sys
import runpy

create_secret = runpy.run_path(str(Path(__file__).resolve().parents[1] / "research_dashboard" / "runtime.py"))["create_secret"]

if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: setup_runtime_secret.py PRIVATE_FILE")
    create_secret(sys.argv[1])
    print("Student signing key is present; existing keys are preserved.")
