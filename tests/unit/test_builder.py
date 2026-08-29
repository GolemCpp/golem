import os
from types import SimpleNamespace

from golemcpp.golem import advertisement_store
from golemcpp.golem import builder
from golemcpp.golem import network


def make_recording_context(observed, directory=""):
    """
    A context recording what a step was allowed to do: reach a remote, and read
    what a remote already advertised.
    """

    def record(step):
        observed.append(
            (step, network.is_allowed(), bool(advertisement_store.directory_in_use()))
        )

    context = SimpleNamespace(
        deps_to_resolve=None,
        deps_resolve=False,
        deps_build=False,
        build_on=False,
        context=SimpleNamespace(targets=["ignored"]),
        make_golem_path=lambda path: os.path.join(directory, path),
    )
    context.environment = lambda resolve_dependencies=False: record("environment")
    context.resolve_recursively = lambda: record("resolve_recursively")
    context.save_resolved_dependencies = lambda: record("save_resolved_dependencies")
    context.build = lambda: record("build")
    context.dependencies = lambda: record("dependencies")
    return context


def test_resolve_is_the_command_that_may_reach_a_remote(monkeypatch, tmp_path):
    observed = []
    monkeypatch.setattr(
        builder,
        "get_context",
        lambda context: make_recording_context(observed, str(tmp_path)),
    )

    builder.resolve(SimpleNamespace())

    assert observed == [
        ("environment", True, True),
        ("resolve_recursively", True, True),
        ("save_resolved_dependencies", True, True),
    ]
    assert network.is_allowed() is False
    assert advertisement_store.directory_in_use() == ""


def test_resolve_keeps_the_advertisements_under_the_build_directory(
    monkeypatch, tmp_path
):
    observed = []
    context = make_recording_context(observed, str(tmp_path))
    monkeypatch.setattr(builder, "get_context", lambda _: context)

    builder.resolve(SimpleNamespace())

    assert os.path.isdir(
        os.path.join(str(tmp_path), advertisement_store.DIRECTORY_NAME)
    )


def test_build_and_dependencies_read_what_resolve_put_in_the_cache(monkeypatch):
    observed = []
    monkeypatch.setattr(
        builder, "get_context", lambda context: make_recording_context(observed)
    )

    builder.build(SimpleNamespace())
    builder.dependencies(SimpleNamespace())

    assert observed == [
        ("environment", False, False),
        ("build", False, False),
        ("environment", False, False),
        ("dependencies", False, False),
    ]
