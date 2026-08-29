import os

import pytest

from golemcpp.golem import cppfront_tool


def test_find_cppfront_cache_uses_cache_directory(tmp_path):
    cache_directory = tmp_path / "tools-cache"
    cache_dir = cache_directory / cppfront_tool.CPPFRONT_NAME
    repository_dir = cache_dir / "source" / "include"
    executable_path = cache_dir / "bin" / cppfront_tool.get_cppfront_binary_name()

    repository_dir.mkdir(parents=True)
    executable_path.parent.mkdir(parents=True)
    executable_path.write_text("", encoding="utf-8")

    found = cppfront_tool.find_cppfront_cache_root(
        cached_tool_root=str(cache_dir),
    )

    assert found is not None
    assert found.resource_root == str(cache_directory / cppfront_tool.CPPFRONT_NAME)


def test_build_cppfront_builds_from_the_fetched_source(monkeypatch, tmp_path):
    resource_root = tmp_path / "tools-cache" / cppfront_tool.CPPFRONT_NAME
    source_dir = resource_root / "source"
    build_dir = source_dir / "build-golem-cppfront"
    (source_dir / "include").mkdir(parents=True)
    commands = []

    def fake_run_task(command, cwd=None, **kwargs):
        commands.append((command[2], cwd))
        # Stand in for the build: Golem drops the executable in the build dir.
        built = build_dir / "bin" / cppfront_tool.get_cppfront_binary_name()
        os.makedirs(built.parent, exist_ok=True)
        built.write_text("", encoding="utf-8")

    def refuse_git(params, cwd=None, **kwargs):
        raise AssertionError(
            "the source is fetched by the resource manager: {}".format(params)
        )

    monkeypatch.setattr(cppfront_tool.helpers, "run_git", refuse_git)
    monkeypatch.setattr(cppfront_tool.helpers, "run_task", fake_run_task)

    assert cppfront_tool.build_cppfront(resource_root=str(resource_root)) is None

    # Golem builds cppfront like any other project, from the golemfile written
    # into the fetched source.
    assert commands == [("configure", str(source_dir)), ("build", str(source_dir))]
    assert (source_dir / "golemfile.py").is_file()
    # And the result is copied where the tool is looked up.
    assert (resource_root / "bin" / cppfront_tool.get_cppfront_binary_name()).is_file()


def test_build_cppfront_reports_a_build_that_produced_nothing(monkeypatch, tmp_path):
    resource_root = tmp_path / "tools-cache" / cppfront_tool.CPPFRONT_NAME
    (resource_root / "source").mkdir(parents=True)

    monkeypatch.setattr(cppfront_tool.helpers, "run_task", lambda *a, **k: None)

    with pytest.raises(RuntimeError, match="executable was not found"):
        cppfront_tool.build_cppfront(resource_root=str(resource_root))
