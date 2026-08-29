"""
What a test builds its inputs with: a stubbed remote, a seeded manifest, a cache
configuration. Each fills its own defaults, so a test states only the setting it
is about.
"""

import os
from pathlib import Path

from golemcpp.golem import helpers
from golemcpp.golem.cache_configuration import CacheConfiguration
from golemcpp.golem.fetch_policy import FetchMode
from golemcpp.golem.git_fetcher import GitFetcher
from golemcpp.golem.resolved_version import ResolvedVersion
from golemcpp.golem.settings import get_settings

ROOT = Path(__file__).resolve().parents[1]

# The commit a stubbed fetch reports having landed on.
STUB_HEAD = "cafebabecafebabecafebabecafebabecafebabe"


def stub_git_probes(
    monkeypatch,
    head=STUB_HEAD,
    holds_revision=True,
    has_submodules=True,
    mode=FetchMode.BLOBLESS,
    branches=("main",),
    tags=(),
):
    """
    Stub what a fetch reads about a repository, so a test drives the mechanism
    without one being there.

    None of these answers goes through `run_git`, therefore none of them shows up
    in a recorded command sequence.
    """
    # What a root answers about its own shape, which is how a fetch tells what it
    # is refreshing rather than what a fresh one would be asked for.
    shape = {
        "--is-shallow-repository": mode == FetchMode.SHALLOW,
        "remote.origin.promisor": mode == FetchMode.BLOBLESS,
    }

    def advertisement():
        """
        Build what the remote publishes, shaped the way `ls-remote --symref`
        answers. HEAD points at the first branch, which is what a repository
        with one branch means.
        """
        lines = []
        if branches:
            lines.append("ref: refs/heads/{}\tHEAD".format(branches[0]))
        lines.append("{}\tHEAD".format(head))
        lines += ["{}\trefs/heads/{}".format(head, branch) for branch in branches]
        lines += ["{}\trefs/tags/{}".format(head, tag) for tag in tags]
        return "\n".join(lines) + "\n"

    def read_git(params, cwd=None, **kwargs):
        for question, answer in shape.items():
            if question in params:
                return ("true" if answer else "false") + "\n"
        if params[0] == "ls-remote":
            return advertisement()
        return head + "\n"

    def try_git(params, cwd=None, **kwargs):
        if params[:3] != ["rev-parse", "--verify", "--quiet"]:
            # Housekeeping, where nothing is made of the answer.
            return True
        if not holds_revision:
            return False

        # What the probe order asks for, one ref at a time. Anything else is a
        # commit, which a repository asked about its own revision holds.
        wanted = params[3].removesuffix("^{commit}")
        if wanted.startswith("refs/tags/"):
            return wanted[len("refs/tags/") :] in tags
        if wanted.startswith("refs/remotes/origin/"):
            return wanted[len("refs/remotes/origin/") :] in branches
        return True

    monkeypatch.setattr(helpers, "try_git", try_git)
    monkeypatch.setattr(helpers, "read_git", read_git)
    monkeypatch.setattr(GitFetcher, "has_submodules", lambda self: has_submodules)


def absolute_path(*parts):
    """
    Make a path that is absolute on every platform. A leading separator is enough
    on POSIX, but Windows also needs a drive, therefore `/opt/cache` is still
    resolved there against the current directory.
    """
    return os.path.join(os.path.abspath(os.sep), *parts)


def default_setting(name):
    """Read the built-in default of a setting, processed as a resolved value is."""
    return get_settings().get_default(name)


def make_source(
    locator="https://github.com/golemcpp/example.git",
    reference="v1.0.0",
    revision=STUB_HEAD,
    source_type="git",
):
    """
    Make the source a seeded manifest records. A manifest naming no locator
    identifies nothing, therefore the default is one a `Locator` accepts.
    """
    return {
        "type": source_type,
        "locator": locator,
        "resolved": {"reference": reference, "revision": revision},
    }


def make_cache_configuration(
    *locations,
    resolution_policy=default_setting("GOLEM_CACHE_RESOLUTION_POLICY"),
    minimization_enabled=default_setting("GOLEM_CACHE_MINIMIZATION_ENABLED"),
    minimization_length=default_setting("GOLEM_CACHE_MINIMIZATION_LENGTH"),
    fetch_mode=default_setting("GOLEM_GIT_FETCH_MODE"),
    fetch_jobs=1,
):
    """
    Make a CacheConfiguration for a test that cares about one of its settings.
    The constructor requires them all, therefore the defaults are filled here.

    `fetch_jobs` is the exception: its own default counts the processors, and a
    recorded command sequence must not read differently on another machine.
    """
    return CacheConfiguration(
        locations=locations,
        resolution_policy=resolution_policy,
        minimization_enabled=minimization_enabled,
        minimization_length=minimization_length,
        fetch_mode=fetch_mode,
        fetch_jobs=fetch_jobs,
    )


def resolved_dependency(dependency, project_dir="", **version):
    """
    Read a dependency's declaration, then stand in for a remote nobody reached.

    Reading settles where it comes from and what kind it is; a unit test has no
    remote to ask for a version, so it says one here instead.
    """
    dependency.update_source(project_dir)
    dependency.resolved = dependency.resolved.settle_version(ResolvedVersion(**version))

    return dependency
