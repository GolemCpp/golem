"""
What this machine can run, and the guards that skip a test it cannot.

A `require_` function skips rather than fails: a missing compiler, Qt or
packaging tool says nothing about the code under test. Which runner provides
what is a CI concern, expressed there by marker.
"""

import os
import shutil
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

import pytest


def command_exists(command: str) -> bool:
    return shutil.which(command) is not None


def has_windows_msvc_toolchain() -> bool:
    installer_root = Path(
        os.environ.get(
            "ProgramFiles(x86)",
            os.environ.get("ProgramFiles", "C:\\Program Files (x86)"),
        )
    )
    vswhere_path = (
        installer_root / "Microsoft Visual Studio" / "Installer" / "vswhere.exe"
    )
    return command_exists("cl") or vswhere_path.is_file()


def run_tool_query(command: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [command, *args],
        capture_output=True,
        text=True,
        check=False,
    )


def require_cxx_compiler() -> None:
    if sys.platform.startswith("win32") and has_windows_msvc_toolchain():
        return
    if any(command_exists(candidate) for candidate in ("c++", "g++", "clang++")):
        return
    pytest.skip("No C++ compiler available for example integration tests")


@lru_cache(maxsize=None)
def can_access_git_remote(repository: str) -> bool:
    result = subprocess.run(
        ["git", "ls-remote", "--heads", repository, "HEAD"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    return result.returncode == 0


def require_git_remote_access(*repositories: str) -> None:
    for repository in repositories:
        if not can_access_git_remote(repository):
            pytest.skip(f"Git remote not reachable for integration test: {repository}")


@lru_cache(maxsize=1)
def find_qt_dir() -> str | None:
    for env_name in ("QTDIR", "QT_DIR", "QT6_DIR"):
        value = os.environ.get(env_name)
        if value and Path(value).exists():
            return value

    for command in ("qmake6", "qmake"):
        if not command_exists(command):
            continue

        version_result = run_tool_query(command, "-query", "QT_VERSION")
        if version_result.returncode != 0:
            continue

        version = version_result.stdout.strip()
        if not version.startswith("6."):
            continue

        prefix_result = run_tool_query(command, "-query", "QT_INSTALL_PREFIX")
        if prefix_result.returncode != 0:
            continue

        prefix = prefix_result.stdout.strip()
        if prefix and Path(prefix).exists():
            return prefix

    return None


def require_qt_dir() -> str:
    qt_dir = find_qt_dir()
    if qt_dir is None:
        pytest.skip("Qt 6 was not found for the Qt example integration tests")
    return qt_dir


def require_packaging_tool() -> None:
    if sys.platform.startswith("linux"):
        if (
            command_exists("fakeroot")
            and command_exists("strip")
            and command_exists("linuxdeployqt")
        ):
            return
        pytest.skip(
            "fakeroot, strip, and linuxdeployqt are required for the package"
            " example on Linux"
        )

    if sys.platform.startswith("darwin"):
        if command_exists("hdiutil"):
            return
        pytest.skip("hdiutil is required for the package example on macOS")

    if sys.platform.startswith("win32"):
        if command_exists("candle") and command_exists("light"):
            return
        pytest.skip("WiX candle/light are required for the package example on Windows")
