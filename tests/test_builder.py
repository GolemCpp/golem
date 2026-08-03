from types import SimpleNamespace

from golemcpp.golem import builder
from golemcpp.golem import network


def make_recording_context(observed):
    '''A context that records whether a remote was reachable at each step.'''
    context = SimpleNamespace(
        deps_to_resolve=None,
        deps_resolve=False,
        deps_build=False,
        build_on=False,
        context=SimpleNamespace(targets=['ignored']),
    )
    context.environment = lambda resolve_dependencies=False: observed.append(
        ('environment', network.is_allowed()))
    context.resolve_recursively = lambda: observed.append(
        ('resolve_recursively', network.is_allowed()))
    context.build = lambda: observed.append(('build', network.is_allowed()))
    context.dependencies = lambda: observed.append(
        ('dependencies', network.is_allowed()))
    return context


def test_resolve_is_the_command_that_may_reach_a_remote(monkeypatch):
    observed = []
    monkeypatch.setattr(
        builder, 'get_context', lambda context: make_recording_context(observed))

    builder.resolve(SimpleNamespace())

    assert observed == [('environment', True), ('resolve_recursively', True)]
    assert network.is_allowed() is False


def test_build_and_dependencies_read_what_resolve_put_in_the_cache(monkeypatch):
    observed = []
    monkeypatch.setattr(
        builder, 'get_context', lambda context: make_recording_context(observed))

    builder.build(SimpleNamespace())
    builder.dependencies(SimpleNamespace())

    assert observed == [
        ('environment', False), ('build', False),
        ('environment', False), ('dependencies', False),
    ]
