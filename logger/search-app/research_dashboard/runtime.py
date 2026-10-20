"""Persistent runtime configuration shared by production and local workers."""
from pathlib import Path
import os
import secrets
import tempfile


def sync_directory(directory):
    fd = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def create_secret(path):
    """Publish a complete private secret once; never replace an existing key."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(prefix=".secret-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as target:
            target.write(secrets.token_urlsafe(48) + "\n")
            target.flush()
            os.fsync(target.fileno())
        try:
            os.link(temporary, path)
            sync_directory(path.parent)
        except FileExistsError:
            pass
    finally:
        os.unlink(temporary)


def configure_runtime(app):
    session_dir = Path(os.getenv("SOL_SESSION_DIR", "flask_session"))
    session_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    production = os.getenv("SOL_ENV", "development") == "production"
    secret = os.getenv("FLASK_SECRET_KEY", "")
    if not secret:
        configured_file = os.getenv("FLASK_SECRET_KEY_FILE", "")
        if production and not configured_file:
            raise RuntimeError("Configure FLASK_SECRET_KEY or FLASK_SECRET_KEY_FILE in production")
        path = Path(configured_file) if configured_file else session_dir / "signing-secret"
        if not production and not path.exists():
            create_secret(path)
        try:
            secret = path.read_text().strip()
        except OSError as exc:
            raise RuntimeError("Student signing secret is unavailable") from exc
    if len(secret) < 32:
        raise RuntimeError("Student signing secret must contain at least 32 characters")
    app.config.update(SECRET_KEY=secret, SESSION_FILE_DIR=str(session_dir),
                      SESSION_FILE_THRESHOLD=0)
