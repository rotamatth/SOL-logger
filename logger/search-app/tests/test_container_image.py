"""The image copies named files and folders only, and installs requirements.lock by hash.

Without `COPY . .`, a new module that is not added to the Dockerfile would be missing on the server
while every test here still passes. These tests fail first, in CI, and say what to do.
"""
import fnmatch
import importlib.util
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]

# Kept out of the image on purpose.
LEFT_OUT = {".dockerignore", "Dockerfile", "tests", "requirements.txt", "requirements-test.txt",
            "requirements-quality.txt", "requirements-browser-test.txt"}


def copied_sources():
    sources = set()
    for line in (APP_ROOT / "Dockerfile").read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if parts and parts[0].upper() in ("COPY", "ADD"):
            sources.update(part.rstrip("/") or "/" for part in parts[1:-1] if not part.startswith("--"))
    return sources


def ignored_by_docker(name):
    patterns = [line.strip().rstrip("/") for line in
                (APP_ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
                if line.strip() and not line.startswith("#")]
    return any(fnmatch.fnmatch(name, pattern) for pattern in patterns)


def present_entries():
    """Files and folders the build could copy: hidden local files and .dockerignore matches excluded."""
    return {entry.name for entry in APP_ROOT.iterdir()
            if not ignored_by_docker(entry.name) and (entry.name == ".dockerignore" or not entry.name.startswith("."))}


def test_the_image_never_copies_the_whole_build_folder():
    assert not copied_sources() & {".", "/", "*"}


def test_every_file_and_folder_is_copied_or_deliberately_left_out():
    missing = present_entries() - copied_sources() - LEFT_OUT
    assert not missing, f"{sorted(missing)}: add to a COPY line in the Dockerfile, or to LEFT_OUT in this test"
    assert copied_sources() <= present_entries() | {"requirements.lock"}, "the Dockerfile copies a path that does not exist"
    assert not copied_sources() & LEFT_OUT


def load_hash_tool():
    spec = importlib.util.spec_from_file_location("hash_requirements_lock", APP_ROOT / "tools" / "hash_requirements_lock.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_every_pin_in_the_lock_carries_its_hashes():
    tool = load_hash_tool()
    pins = [line for line in tool.logical_lines((APP_ROOT / "requirements.lock").read_text(encoding="utf-8"))
            if line.strip() and not line.lstrip().startswith("#")]
    assert pins
    unhashed = [line.split()[0] for line in pins if "--hash=sha256:" not in line]
    assert not unhashed, f"{unhashed}: run python tools/hash_requirements_lock.py from logger/search-app"


def test_the_hash_tool_keeps_comments_and_replaces_old_hashes():
    tool = load_hash_tool()
    text = "# header\nflask==3.1.3 \\\n    --hash=sha256:old\n\nWerkzeug==3.1.9\n"
    fetched = {"flask": ["b" * 64, "a" * 64], "Werkzeug": ["c" * 64]}
    result = tool.rewrite(text, fetch=lambda name, version: sorted(fetched[name]))
    assert result == ("# header\n"
                      f"flask==3.1.3 \\\n    --hash=sha256:{'a' * 64} \\\n    --hash=sha256:{'b' * 64}\n"
                      "\n"
                      f"Werkzeug==3.1.9 \\\n    --hash=sha256:{'c' * 64}\n")
    assert "old" not in result
