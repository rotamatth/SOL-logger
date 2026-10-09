"""Create or rotate the research password hash without putting a password in shell history."""
import argparse
import getpass
import os
from pathlib import Path
import tempfile

from werkzeug.security import generate_password_hash


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="Private server-side password.hash destination")
    args = parser.parse_args()
    password = getpass.getpass("New shared research password (at least 12 characters): ")
    if len(password) < 12:
        parser.error("Use at least 12 characters.")
    if password != getpass.getpass("Repeat password: "):
        parser.error("Passwords do not match.")
    digest = generate_password_hash(password, method="scrypt")
    args.output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(prefix=".password-", dir=args.output.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as target:
            target.write(digest + "\n")
            target.flush()
            os.fsync(target.fileno())
        os.replace(temporary, args.output)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    print("Research password hash saved. Existing research logins will expire on their next request.")


if __name__ == "__main__":
    main()
