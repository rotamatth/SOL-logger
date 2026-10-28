"""Offline, verified study backups. Stop collection before create or restore.

Uses only the Python standard library so recovery does not depend on a working
application image. Restores only into a new directory; never replaces live data.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import sqlite3
import zipfile

DIRECTORIES = ("logs", "logs-v2", "research-state", "research-secrets", "student-sessions")


def sync_directory(path):
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def check_databases(root):
    for directory in ("logs-v2", "research-state"):
        for path in (root / directory).glob("*.sqlite3"):
            if path.name == "index.sqlite3":
                continue  # Disposable index can be rebuilt after restoration.
            db = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
            try:
                if db.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
                    raise ValueError("Database integrity check failed: " + path.name)
            finally:
                db.close()


def create(root, destination):
    root, destination = Path(root), Path(destination)
    check_databases(root)
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    manifest = {"version": 1, "directories": list(DIRECTORIES), "files": []}
    fd = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "w+b") as target:
        with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
            for directory in DIRECTORIES:
                source_root = root / directory
                if source_root.is_symlink():
                    raise ValueError("Backup directory must not be a symlink")
                for path in sorted(source_root.rglob("*")):
                    if path.is_symlink():
                        raise ValueError("Backup sources must not contain symlinks")
                    if not path.is_file():
                        continue
                    name = path.relative_to(root).as_posix()
                    digest, size = hashlib.sha256(), 0
                    with path.open("rb") as source, archive.open(name, "w", force_zip64=True) as output:
                        while block := source.read(1024 * 1024):
                            digest.update(block)
                            size += len(block)
                            output.write(block)
                    manifest["files"].append({"name": name, "sha256": digest.hexdigest(), "size": size})
            archive.writestr("backup-manifest.json", json.dumps(manifest, indent=2))
        target.flush()
        os.fsync(target.fileno())
    sync_directory(destination.parent)
    verify(destination)


def verify(source):
    with zipfile.ZipFile(source) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError("Duplicate backup member")
        manifest = json.loads(archive.read("backup-manifest.json"))
        if manifest.get("version") != 1 or manifest.get("directories") != list(DIRECTORIES):
            raise ValueError("Unsupported backup format")
        expected = {item["name"] for item in manifest["files"]}
        if len(expected) != len(manifest["files"]) or set(names) != expected | {"backup-manifest.json"}:
            raise ValueError("Backup manifest mismatch")
        for item in manifest["files"]:
            path = PurePosixPath(item["name"])
            if path.is_absolute() or ".." in path.parts or not path.parts or path.parts[0] not in DIRECTORIES:
                raise ValueError("Unsafe backup member")
            digest, size = hashlib.sha256(), 0
            with archive.open(item["name"]) as entry:
                while block := entry.read(1024 * 1024):
                    digest.update(block)
                    size += len(block)
            if digest.hexdigest() != item["sha256"] or size != item["size"]:
                raise ValueError("Backup checksum mismatch")
        return manifest


def restore(source, destination):
    manifest = verify(source)
    destination = Path(destination)
    destination.mkdir(mode=0o700)  # An existing directory is deliberately refused.
    for directory in DIRECTORIES:
        (destination / directory).mkdir(mode=0o700)
    with zipfile.ZipFile(source) as archive:
        for item in manifest["files"]:
            path = destination / item["name"]
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(fd, "wb") as target, archive.open(item["name"]) as entry:
                while block := entry.read(1024 * 1024):
                    target.write(block)
                target.flush()
                os.fsync(target.fileno())
    check_databases(destination)
    for directory in sorted((p for p in destination.rglob("*") if p.is_dir()),
                            key=lambda p: len(p.parts), reverse=True):
        sync_directory(directory)
    sync_directory(destination)
    sync_directory(destination.parent)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("create", "verify", "restore"))
    parser.add_argument("archive", type=Path)
    parser.add_argument("--root", type=Path, help="Stopped logger data directory (create) or new destination (restore)")
    args = parser.parse_args()
    if args.operation != "verify" and args.root is None:
        parser.error("--root is required")
    if args.operation == "create":
        create(args.root, args.archive)
    elif args.operation == "restore":
        restore(args.archive, args.root)
    else:
        verify(args.archive)
    print("Backup " + args.operation + " completed and verified.")
