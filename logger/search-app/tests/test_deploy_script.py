"""The deploy runs over ssh with its script on standard input, so no step may read the rest of it."""
import os
from pathlib import Path
import re
import stat
import subprocess

ROOT = Path(__file__).resolve().parents[3]
FAKE_DOCKER = """#!/bin/sh
echo "docker $*" >> "$HOME/calls"
case "$*" in
  "compose ps -aq search_app") echo old-container ;;
  "inspect "*) echo old-image ;;
  # A real run attaches standard input to the container and drains it.
  "compose run "*) cat > /dev/null ;;
esac
"""


def remote_script():
    text = (ROOT / "scripts" / "deploy.sh").read_text()
    return re.search(r"<<'REMOTE'\n(.*?)\nREMOTE\n", text, re.S).group(1)


def fake(folder, name, body):
    path = folder / name
    path.write_text(body)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def test_the_release_starts_after_the_backup_when_the_script_comes_from_standard_input(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake(bin_dir, "docker", FAKE_DOCKER)
    fake(bin_dir, "git", "#!/bin/sh\nexit 0\n")
    fake(bin_dir, "python3", "#!/bin/sh\nexit 0\n")
    logger = tmp_path / "SOL-logger" / "logger"
    (logger / "search-app").mkdir(parents=True)
    (logger / "research-secrets").mkdir()
    for path in (logger / "search-app" / "API_keys.json", logger / "search-app" / "service_account.json",
                 logger / "research-secrets" / "password.hash"):
        path.write_text("synthetic")
    done = subprocess.run(["bash", "-s"], input=remote_script(), text=True, capture_output=True, timeout=30,
                          env={**os.environ, "HOME": str(tmp_path), "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
                               "DEPLOY_BRANCH": "main", "SERVER_REPO": "SOL-logger"})
    assert done.returncode == 0, done.stderr
    assert "Verified backup: backups/study-" in done.stdout
    calls = (tmp_path / "calls").read_text().splitlines()
    backup = next(number for number, call in enumerate(calls) if call.startswith("docker compose run "))
    assert any(call.startswith("docker compose up -d") for call in calls[backup:])
