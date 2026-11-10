"""Write the sha256 hashes of every pinned package into requirements.lock.

The image installs requirements.lock with ``--require-hashes``, so pip refuses any file whose hash
is not listed. Run this after changing a version in the lock, from ``logger/search-app``:

    python tools/hash_requirements_lock.py

It keeps the comments and the order of the pins, drops any hashes already there and lists the hashes
of every file PyPI publishes for each pinned version (all platforms, so the same lock works on the
server, in CI and on a Mac). It needs network access to pypi.org and changes nothing else.
"""
import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path

PYPI_JSON = "https://pypi.org/pypi/{name}/{version}/json"
PIN = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)(\[[^\]]*\])?==([^\s;]+)$")


def logical_lines(text):
    """Lines with backslash continuations joined, as pip reads them."""
    joined, current = [], ""
    for line in text.splitlines():
        if line.rstrip().endswith("\\"):
            current += line.rstrip()[:-1] + " "
            continue
        joined.append(current + line)
        current = ""
    if current:
        joined.append(current)
    return joined


def pypi_hashes(name, version):
    with urllib.request.urlopen(PYPI_JSON.format(name=name, version=version), timeout=30) as response:
        release = json.load(response)
    hashes = sorted({file["digests"]["sha256"] for file in release["urls"]})
    if not hashes:
        raise SystemExit(f"PyPI lists no files for {name}=={version}")
    return hashes


def rewrite(text, fetch=pypi_hashes):
    out = []
    for line in logical_lines(text):
        requirement = line.split("--hash=")[0].strip()
        if not requirement or requirement.startswith("#"):
            out.append(line.rstrip())
            continue
        match = PIN.match(requirement)
        if not match:
            raise SystemExit(f"Not an exact pin (name==version): {requirement}")
        name, extras, version = match.groups()
        hashes = fetch(name, version)
        out.append(f"{name}{extras or ''}=={version} \\")
        out.extend(f"    --hash=sha256:{digest}" + (" \\" if i < len(hashes) - 1 else "")
                   for i, digest in enumerate(hashes))
    return "\n".join(out) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("lock", nargs="?", default="requirements.lock", type=Path)
    args = parser.parse_args(argv)
    original = args.lock.read_text(encoding="utf-8")
    updated = rewrite(original)
    args.lock.write_text(updated, encoding="utf-8")
    pins = sum(1 for line in logical_lines(updated) if PIN.match(line.split("--hash=")[0].strip()))
    print(f"{args.lock}: {pins} pins hashed" + ("" if updated != original else " (unchanged)"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
