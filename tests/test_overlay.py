import pytest

from golemcpp.golem.requested_source import DEFAULT_GIT_VERSION
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

    def resolve(url, version, version_regex=''):
        asked.append((url, version))
        return ResolvedVersion(reference='v1.2.0', revision='deadbeef')

    monkeypatch.setattr(VersionResolver, 'resolve', staticmethod(resolve))
    return asked


def make_source(version=''):
    return RequestedSource.for_repository('https://host/overrides.git', version=version)


def test_an_overlay_asked_for_without_a_version_takes_its_sources_reference():
    assert Overlay(source=make_source()).version == 'main'
    assert Overlay(source=make_source(), version='v1.2.0').version == 'v1.2.0'


def test_resolving_follows_the_configured_reference_without_asking_a_remote(resolutions):
    overlay = Overlay(source=make_source(version='develop'))

    assert overlay.resolve() == ResolvedVersion(reference='develop', revision='develop')
    assert overlay.resolved.reference == 'develop'
    # Nothing to ask for: an overlay names no version of its own yet.
    assert resolutions == []


def test_the_source_carries_the_resolved_reference():
    overlay = Overlay(source=make_source(), version='v1.2.0')
    overlay.resolve()

    source = overlay.to_source()

    assert source.locator == Locator('https://host/overrides.git')
    assert source.resolved.reference == 'v1.2.0'


def test_the_source_is_readable_before_the_overlay_is_resolved():
    # Locating a resource resolves it first, but nothing should depend on that to
    # read the identity an overlay already carries.
    source = Overlay(source=make_source()).to_source()

    assert source.locator == Locator('https://host/overrides.git')
    assert source.resolved.reference == DEFAULT_GIT_VERSION


def test_a_directory_overlay_keeps_its_empty_reference():
    requested = RequestedSource.for_directory('file:///overlays/local')
    overlay = Overlay(source=requested)

    overlay.resolve()

    # No default branch to fall back on: a copied directory is what it holds.
    assert overlay.version == ''
    source = overlay.to_source()
    assert source.type == 'directory'
    assert source.locator == requested.locator
    assert not source.resolved
    # And with no version to name, the key is the source id alone.
    assert OverlayManager.cache_key_for(overlay) == requested.get_id()


def test_an_overlay_is_named_after_its_source():
    assert Overlay(source=make_source()).name == make_source().get_id()
