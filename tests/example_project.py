"""
Driving golem against a copy of one of the projects under `examples`.

Every test works on a copy in a temporary directory, so a run leaves the checkout
as it found it and two runs never share a build.
"""

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from support import ROOT as REPO_ROOT

EXAMPLES_DIR = REPO_ROOT / "examples"

# The cookbook some examples name in their own `.golem/config.json`.
COOKBOOK_DIR = EXAMPLES_DIR / "cookbook"

# What a copy may leave behind: build output, and the cache directories the
# `cache` example writes.
NOT_COPIED = ("build", "__pycache__", "cache-*")

# The architecture every configure in this suite asks for. Empty means none is
# asked for, which is the normal case: the compiler's own answer stands.
REQUESTED_ARCH = os.environ.get("GOLEM_TEST_ARCH", "")

# What configure reports having settled on, in waf's aligned message format.
TARGET_LINE = re.compile(r"^Target architecture\s*:\s*(\S+)\s*$", re.MULTILINE)


def get_examples_tmp_dir() -> Path:
    return REPO_ROOT / ".pytest-examples"


def make_golem_env(cache_dir: Path) -> dict[str, str]:
    env = os.environ.copy()

    pythonpath_entries = [str(REPO_ROOT / "src"), str(REPO_ROOT / "waflib" / "waf")]
    if env.get("PYTHONPATH"):
        pythonpath_entries.append(env["PYTHONPATH"])

    env["PYTHONPATH"] = os.pathsep.join(pythonpath_entries)
    # The default cache is the one a machine shares between projects, so leaving
    # it unset ran every example against whatever the developer or the runner had
    # already built. A test then passed or failed on what ran before it.
    env["GOLEM_CACHE_DIRECTORY"] = f"{cache_dir}-default"
    env["GOLEM_ADDITIONAL_CACHE_DIRECTORIES"] = f"{cache_dir}=^.*$"
    # Nothing sets GOLEM_COOKBOOKS_LOCATIONS: certain examples sets it through
    # `.golem/config.json` and an environment variable would outrank it.
    env["GOLEM_OVERLAYS_LOCATIONS"] = ""

    return env


def copy_example_project(example_name: str, destination_root: Path) -> Path:
    source = EXAMPLES_DIR / example_name
    destination = destination_root / example_name

    shutil.copytree(source, destination, ignore=shutil.ignore_patterns(*NOT_COPIED))
    copy_cookbook(destination_root)

    return destination


def copy_cookbook(destination_root: Path) -> Path:
    """
    Copy the example cookbook beside wherever the examples are copied.

    Copied for every example rather than the three that name it, so this does not
    have to know which ones do.
    """
    destination = destination_root / COOKBOOK_DIR.name

    if not destination.exists():
        shutil.copytree(
            COOKBOOK_DIR, destination, ignore=shutil.ignore_patterns("__pycache__")
        )

    return destination


def prepare_example_project(
    example_name: str, destination_root: Path, project_variant: str = "python"
) -> Path:
    project_dir = copy_example_project(example_name, destination_root)
    if project_variant == "json":
        use_json_project_file(project_dir)
    return project_dir


def use_json_project_file(project_dir: Path) -> None:
    python_project_file = project_dir / "golemfile.py"
    json_project_file = project_dir / "golemfile.json"

    assert json_project_file.exists()
    if python_project_file.exists():
        python_project_file.unlink()


def run_golem(
    project_dir: Path, cache_dir: Path, *args: str
) -> subprocess.CompletedProcess[str]:
    # One CI leg builds for a target the runner is not: 32-bit Windows on a
    # 64-bit host. Threading --arch through here rather than through every
    # call site keeps the suite one suite.
    if REQUESTED_ARCH and args and args[0] == "configure":
        args = (*args, "--arch=" + REQUESTED_ARCH)

    result = subprocess.run(
        [sys.executable, "-m", "golemcpp.golem", *args],
        cwd=project_dir,
        env=make_golem_env(cache_dir),
        capture_output=True,
        text=True,
        check=False,
    )

    if result.returncode != 0:
        raise AssertionError(
            "Command failed: {}\nstdout:\n{}\nstderr:\n{}".format(
                " ".join(args), result.stdout, result.stderr
            )
        )

    return result


def program_path(project_dir: Path, program_name: str) -> Path:
    suffix = ".exe" if sys.platform.startswith("win32") else ""
    return project_dir / "build" / "bin" / f"{program_name}{suffix}"


def run_binary(binary: Path, project_dir: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(binary)],
        cwd=project_dir,
        capture_output=True,
        text=True,
        check=False,
    )


def read_dependencies_json(project_dir: Path) -> list[dict[str, object]]:
    """What the resolve recorded, from the build directory golem writes it in."""
    path = project_dir / "build" / "golem" / "obj" / "dependencies.json"
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def assert_package_artifact_exists(project_dir: Path) -> None:
    if sys.platform.startswith("linux"):
        assert any(project_dir.joinpath("build").rglob("*.deb"))
    elif sys.platform.startswith("darwin"):
        assert any(project_dir.joinpath("build").rglob("*.dmg"))
    elif sys.platform.startswith("win32"):
        assert any(project_dir.joinpath("build").rglob("*.msi"))
