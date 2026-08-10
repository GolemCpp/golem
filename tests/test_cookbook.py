import pytest

from golemcpp.golem.resolved_version import ResolvedVersion
from golemcpp.golem.cookbook import Cookbook
from golemcpp.golem.source import Source
from golemcpp.golem.version_resolver import VersionResolver


@pytest.fixture
def resolutions(monkeypatch):
    '''Every version resolution asked of a remote, in order.'''
    asked = []

    def resolve(url, version, version_regex=''):
        asked.append((url, version))
        return ResolvedVersion(reference='v1.2.0', revision='deadbeef')

    monkeypatch.setattr(VersionResolver, 'resolve', staticmethod(resolve))
    return asked


def make_source(reference='main'):
    return Source.for_repository('https://host/recipes.git', reference=reference)


def test_a_cookbook_asked_for_without_a_version_takes_its_sources_reference():
    assert Cookbook(source=make_source()).version == 'main'
    assert Cookbook(source=make_source(), version='v1.2.0').version == 'v1.2.0'


def test_resolving_follows_the_configured_reference_without_asking_a_remote(resolutions):
    cookbook = Cookbook(source=make_source(reference='develop'))

    assert cookbook.resolve() == ResolvedVersion(reference='develop', revision='develop')
    assert cookbook.resolved.reference == 'develop'
    # Nothing to ask for: a cookbook names no version of its own yet.
    assert resolutions == []


def test_the_source_carries_the_resolved_reference():
    cookbook = Cookbook(source=make_source(), version='v1.2.0')
    cookbook.resolve()

    source = cookbook.to_source()

    assert source.location == 'https://host/recipes.git'
    assert source.reference == 'v1.2.0'


def test_the_source_is_readable_before_the_cookbook_is_resolved():
    # Locating a resource resolves it first, but nothing should depend on that to
    # read the identity a cookbook already carries.
    assert Cookbook(source=make_source()).to_source() == make_source()


def test_a_directory_cookbook_keeps_its_empty_reference():
    source = Source.for_directory('file:///cookbooks/local')
    cookbook = Cookbook(source=source)

    cookbook.resolve()

    assert cookbook.version == ''
    assert cookbook.to_source() == source
    assert cookbook.to_source().get_cache_key() == source.get_cache_key()


def test_a_cookbook_is_named_after_its_source():
    assert Cookbook(source=make_source()).name == make_source().get_id()
