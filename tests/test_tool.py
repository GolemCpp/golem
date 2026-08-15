import pytest

from golemcpp.golem.resolved_version import ResolvedVersion
from golemcpp.golem import tool_registry
from golemcpp.golem.tool import Tool
from golemcpp.golem.version_resolver import VersionResolver
from golemcpp.golem.locator import Locator


@pytest.fixture
def resolutions(monkeypatch):
    '''Every version resolution asked of the remote, in order.'''
    asked = []

    def resolve(url, version, version_regex=''):
        asked.append((url, version))
        return ResolvedVersion(reference='v0.8.1', revision='deadbeef')

    monkeypatch.setattr(VersionResolver, 'resolve', staticmethod(resolve))
    return asked


def make_definition(default_version='v0.8.1'):
    return tool_registry.ToolDefinition(
        name='cppfront',
        description='',
        repository='https://host/cppfront.git',
        default_version=default_version,
        build_handler=lambda resource_root: None)


def test_a_tool_asked_for_without_a_version_takes_its_definitions_default():
    assert Tool(definition=make_definition()).version == 'v0.8.1'
    assert Tool(definition=make_definition(), version='v0.8.0').version == 'v0.8.0'


def test_a_definition_naming_no_default_leaves_the_version_empty():
    assert Tool(definition=make_definition(default_version=None)).version == ''


def test_resolving_asks_the_remote_for_the_requested_version(resolutions):
    tool = Tool(definition=make_definition(), version='^0.8.0')

    assert tool.resolve() == ResolvedVersion(reference='v0.8.1', revision='deadbeef')
    assert resolutions == [('https://host/cppfront.git', '^0.8.0')]
    assert tool.resolved.reference == 'v0.8.1'


def test_resolving_twice_asks_once(resolutions):
    tool = Tool(definition=make_definition())

    tool.resolve()
    tool.resolve()

    assert len(resolutions) == 1


def test_the_source_carries_the_resolved_version(resolutions):
    tool = Tool(definition=make_definition(), version='^0.8.0')
    tool.resolve()

    source = tool.to_source()

    assert source.locator == Locator('https://host/cppfront.git')
    # What was resolved, not what was asked for.
    assert source.reference == 'v0.8.1'
