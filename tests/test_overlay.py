import pytest

from golemcpp.golem.resource_manager import ResourceManager
from golemcpp.golem.requested_source import RequestedSource
from golemcpp.golem.resolved_version import ResolvedVersion
from golemcpp.golem.overlay import Overlay
from golemcpp.golem.source import Source
from golemcpp.golem.version_resolver import VersionResolver
from golemcpp.golem.locator import Locator
from golemcpp.golem.overlay_manager import OverlayManager


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
    return RequestedSource.for_repository('https://host/overrides.git', version=version)


def test_an_overlay_asked_for_without_a_version_takes_its_sources_reference():
    assert Overlay(source=make_source(version='v1.2.0')).version == 'v1.2.0'
    assert Overlay(source=make_source(), version='v1.2.0').version == 'v1.2.0'


def test_an_overlay_naming_no_version_anywhere_leaves_it_to_the_remote():
    # Not `main`: which branch a remote defaults to is the remote's to say,
    # and the resolver asks it rather than guessing a name here.
    assert Overlay(source=make_source()).version == ''


def test_an_overlay_resolves_the_way_every_other_kind_does(resolutions):
    # No resolution of its own: what an overlay is pinned to decides which half
    # of the answer names its root, not how the answer is arrived at.
    overlay = Overlay(source=make_source(version='^1.2.0'))

    assert overlay.resolve() == ResolvedVersion(reference='v1.2.0', revision='deadbeef')
    assert resolutions == [('https://host/overrides.git', '^1.2.0')]


def test_a_resolved_overlay_is_not_resolved_again(resolutions):
    overlay = Overlay(source=make_source(version='^1.2.0'))
    overlay.resolve()

    assert overlay.resolve() == ResolvedVersion(reference='v1.2.0', revision='deadbeef')
    assert len(resolutions) == 1


def test_the_source_carries_the_resolved_reference(resolutions):
    overlay = Overlay(source=make_source(), version='^1.2.0')
    overlay.resolve()

    source = ResourceManager.source_for(overlay)

    assert source.locator == Locator('https://host/overrides.git')
    assert source.resolved.reference == 'v1.2.0'


def test_an_overlay_is_named_the_same_before_and_after_being_resolved(resolutions):
    # An overlay root is named after the request. It matters more here than for a
    # cookbook: overlays are located on every run, not only inside a resolve.
    overlay = Overlay(source=make_source(version='^1.2.0'))
    unresolved = OverlayManager.cache_key_for(overlay)

    overlay.resolve()

    assert OverlayManager.cache_key_for(overlay) == unresolved
    assert ResourceManager.source_for(overlay).locator == Locator('https://host/overrides.git')


def test_a_directory_overlay_keeps_its_empty_reference(resolutions):
    requested = RequestedSource.for_directory('file:///overlays/local')
    overlay = Overlay(source=requested)

    overlay.resolve()

    # A copied directory has no version, so there is nothing to ask a remote --
    # which for a `file://` locator would be asking git to ls-remote a path.
    assert resolutions == []
    # No default branch to fall back on: a copied directory is what it holds.
    assert overlay.version == ''
    source = ResourceManager.source_for(overlay)
    assert source.type == 'directory'
    assert source.locator == requested.locator
    assert not source.resolved
    # And with no version to name, the key is the source id alone.
    assert OverlayManager.cache_key_for(overlay) == requested.get_id()


def test_an_overlay_is_named_after_its_source():
    assert Overlay(source=make_source()).name == make_source().get_id()
