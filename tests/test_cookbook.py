import pytest

from golemcpp.golem.requested_source import DEFAULT_GIT_VERSION
from golemcpp.golem.requested_source import RequestedSource
from golemcpp.golem.resolved_version import ResolvedVersion
from golemcpp.golem.cookbook import Cookbook
from golemcpp.golem.source import Source
from golemcpp.golem.version_resolver import VersionResolver
from golemcpp.golem.locator import Locator
from golemcpp.golem.cookbook_manager import CookbookManager


@pytest.fixture
def resolutions(monkeypatch):
    '''Every version resolution asked of a remote, in order.'''
    asked = []

    def resolve(url, version, version_regex=''):
        asked.append((url, version))
        return ResolvedVersion(reference='v1.2.0', revision='deadbeef')

    monkeypatch.setattr(VersionResolver, 'resolve', staticmethod(resolve))
    return asked


def make_source(version=''):
    return RequestedSource.for_repository('https://host/recipes.git', version=version)


def test_a_cookbook_asked_for_without_a_version_takes_its_sources_reference():
    assert Cookbook(source=make_source()).version == 'main'
    assert Cookbook(source=make_source(), version='v1.2.0').version == 'v1.2.0'


def test_resolving_follows_the_configured_reference_without_asking_a_remote(resolutions):
    cookbook = Cookbook(source=make_source(version='develop'))

    assert cookbook.resolve() == ResolvedVersion(reference='develop', revision='develop')
    assert cookbook.resolved.reference == 'develop'
    # Nothing to ask for: a cookbook names no version of its own yet.
    assert resolutions == []


def test_the_source_carries_the_resolved_reference():
    cookbook = Cookbook(source=make_source(), version='v1.2.0')
    cookbook.resolve()

    source = cookbook.to_source()

    assert source.locator == Locator('https://host/recipes.git')
    assert source.resolved.reference == 'v1.2.0'


def test_the_source_is_readable_before_the_cookbook_is_resolved():
    # Locating a resource resolves it first, but nothing should depend on that to
    # read the identity a cookbook already carries.
    source = Cookbook(source=make_source()).to_source()

    assert source.locator == Locator('https://host/recipes.git')
    assert source.resolved.reference == DEFAULT_GIT_VERSION


def test_a_directory_cookbook_keeps_its_empty_reference():
    requested = RequestedSource.for_directory('file:///cookbooks/local')
    cookbook = Cookbook(source=requested)

    cookbook.resolve()

    # No default branch to fall back on: a copied directory is what it holds.
    assert cookbook.version == ''
    source = cookbook.to_source()
    assert source.type == 'directory'
    assert source.locator == requested.locator
    assert not source.resolved
    # And with no version to name, the key is the source id alone.
    assert CookbookManager.cache_key_for(cookbook) == requested.get_id()


def test_a_cookbook_is_named_after_its_source():
    assert Cookbook(source=make_source()).name == make_source().get_id()
