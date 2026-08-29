import pytest

from golemcpp.golem.resource_manager import ResourceManager
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

    def resolve(requested):
        asked.append((str(requested.locator), requested.version))
        return ResolvedVersion(reference='v1.2.0', revision='deadbeef')

    monkeypatch.setattr(VersionResolver, 'resolve', staticmethod(resolve))
    return asked


def make_source(version=''):
    return RequestedSource.for_repository('https://host/recipes.git', version=version)


def test_a_cookbook_asks_for_exactly_what_its_location_names():
    # Nothing of its own to reconcile: the location said it in full, and
    # naming no version is a question the resolver puts to the remote.
    assert Cookbook(
        source=make_source(version='v1.2.0')
    ).requested_source() == make_source(version='v1.2.0')
    assert Cookbook(source=make_source()).requested_source().version == ''


def test_a_cookbook_resolves_the_way_every_other_kind_does(resolutions):
    # No resolution of its own: what a cookbook is pinned to decides which half
    # of the answer names its root, not how the answer is arrived at.
    cookbook = Cookbook(source=make_source(version='^1.2.0'))

    assert cookbook.resolve() == ResolvedVersion(
        reference='v1.2.0', revision='deadbeef'
    )
    assert resolutions == [('https://host/recipes.git', '^1.2.0')]


def test_a_resolved_cookbook_is_not_resolved_again(resolutions):
    cookbook = Cookbook(source=make_source(version='^1.2.0'))
    cookbook.resolve()

    assert cookbook.resolve() == ResolvedVersion(
        reference='v1.2.0', revision='deadbeef'
    )
    assert len(resolutions) == 1


def test_the_source_carries_the_resolved_reference(resolutions):
    cookbook = Cookbook(source=make_source(version='^1.2.0'))
    cookbook.resolve()

    source = ResourceManager.source_for(cookbook)

    assert source.locator == Locator('https://host/recipes.git')
    assert source.resolved.reference == 'v1.2.0'


def test_a_cookbook_is_named_the_same_before_and_after_being_resolved(resolutions):
    # A cookbook root is named after the request, so `golem configure` finds what
    # `golem resolve` built without resolving anything itself.
    cookbook = Cookbook(source=make_source(version='^1.2.0'))
    unresolved = CookbookManager.cache_key_for(cookbook)

    cookbook.resolve()

    assert CookbookManager.cache_key_for(cookbook) == unresolved
    assert ResourceManager.source_for(cookbook).locator == Locator(
        'https://host/recipes.git'
    )


def test_a_directory_cookbook_keeps_its_empty_reference(resolutions):
    requested = RequestedSource.for_directory('file:///cookbooks/local')
    cookbook = Cookbook(source=requested)

    cookbook.resolve()

    # A copied directory has no version, so there is nothing to ask a remote --
    # which for a `file://` locator would be asking git to ls-remote a path.
    assert resolutions == []
    # No default branch to fall back on: a copied directory is what it holds.
    assert cookbook.requested_source().version == ''
    source = ResourceManager.source_for(cookbook)
    assert source.type == 'directory'
    assert source.locator == requested.locator
    assert not source.resolved
    # And with no version to name, the key is the source id alone.
    assert CookbookManager.cache_key_for(cookbook) == requested.get_id()


def test_a_cookbook_is_named_after_its_source():
    assert Cookbook(source=make_source()).name == make_source().get_id()
