#!/usr/bin/env python3
"""Read, verify or rewrite the version shared by golemcpp and golemcpp-waflib.

The two packages are always released together at the identical version, and
golemcpp pins ``golemcpp-waflib==<exact>``, so a version lives in three places:

  1. pyproject.toml         -> [project].version
  2. waflib/pyproject.toml  -> [project].version
  3. pyproject.toml         -> the golemcpp-waflib== pin in [project].dependencies

Missing any one of them produces an artifact that cannot resolve its own
dependency, so all three are always handled together.

Only the CI checkout is ever mutated; the repository keeps a static version.
Neither build backend in use (uv_build for golemcpp, setuptools for
golemcpp-waflib) can derive a version from git, which is why this rewrites the
files rather than relying on the backend.

Usage:
    set-version.py --get              print the current version
    set-version.py --check VERSION    fail unless all three sites say VERSION
    set-version.py VERSION            rewrite all three sites to VERSION
"""

import argparse
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GOLEMCPP_PYPROJECT = ROOT / "pyproject.toml"
WAFLIB_PYPROJECT = ROOT / "waflib" / "pyproject.toml"

WAFLIB_DISTRIBUTION = "golemcpp-waflib"


def read_version(pyproject: Path) -> str:
    with pyproject.open("rb") as stream:
        return tomllib.load(stream)["project"]["version"]


def read_pin(pyproject: Path) -> str:
    """Return the version golemcpp pins golemcpp-waflib to."""
    with pyproject.open("rb") as stream:
        dependencies = tomllib.load(stream)["project"]["dependencies"]

    for dependency in dependencies:
        if dependency.replace(" ", "").startswith(f"{WAFLIB_DISTRIBUTION}=="):
            return dependency.split("==", 1)[1].strip()

    raise SystemExit(
        f"{pyproject}: no '{WAFLIB_DISTRIBUTION}==' pin in [project].dependencies"
    )


def project_table_span(text: str) -> tuple[int, int]:
    """Locate the [project] table so edits cannot stray into another table."""
    start = re.search(r"^\[project\]\s*$", text, flags=re.MULTILINE)
    if start is None:
        raise SystemExit("no [project] table found")

    following = re.search(r"^\[", text[start.end():], flags=re.MULTILINE)
    end = len(text) if following is None else start.end() + following.start()
    return start.end(), end


def set_version(pyproject: Path, version: str) -> None:
    text = pyproject.read_text(encoding="utf-8")
    start, end = project_table_span(text)

    table, count = re.subn(
        r'^version\s*=\s*"[^"]*"',
        f'version = "{version}"',
        text[start:end],
        count=1,
        flags=re.MULTILINE,
    )
    if count != 1:
        raise SystemExit(f"{pyproject}: no version key in [project]")

    pyproject.write_text(text[:start] + table + text[end:], encoding="utf-8")


def set_pin(pyproject: Path, version: str) -> None:
    text = pyproject.read_text(encoding="utf-8")

    updated, count = re.subn(
        rf'"{re.escape(WAFLIB_DISTRIBUTION)}\s*==\s*[^"]*"',
        f'"{WAFLIB_DISTRIBUTION}=={version}"',
        text,
        count=1,
    )
    if count != 1:
        raise SystemExit(f"{pyproject}: no '{WAFLIB_DISTRIBUTION}==' pin to rewrite")

    pyproject.write_text(updated, encoding="utf-8")


def check(version: str) -> None:
    """Guard against tagging a commit whose declared version is something else."""
    sites = {
        f"{GOLEMCPP_PYPROJECT.name} [project].version": read_version(GOLEMCPP_PYPROJECT),
        "waflib/pyproject.toml [project].version": read_version(WAFLIB_PYPROJECT),
        f"{WAFLIB_DISTRIBUTION}== pin": read_pin(GOLEMCPP_PYPROJECT),
    }

    mismatched = {site: found for site, found in sites.items() if found != version}
    if mismatched:
        print(f"version mismatch: expected {version!r}", file=sys.stderr)
        for site, found in mismatched.items():
            print(f"  {site}: {found!r}", file=sys.stderr)
        raise SystemExit(1)

    print(f"all three version sites agree on {version}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--get", action="store_true", help="print the current version")
    group.add_argument("--check", metavar="VERSION", help="fail unless all sites match")
    group.add_argument("version", nargs="?", help="version to write to all three sites")
    arguments = parser.parse_args()

    if arguments.get:
        print(read_version(GOLEMCPP_PYPROJECT))
        return

    if arguments.check:
        check(arguments.check)
        return

    set_version(GOLEMCPP_PYPROJECT, arguments.version)
    set_version(WAFLIB_PYPROJECT, arguments.version)
    set_pin(GOLEMCPP_PYPROJECT, arguments.version)
    print(f"set golemcpp and {WAFLIB_DISTRIBUTION} to {arguments.version}")


if __name__ == "__main__":
    main()
