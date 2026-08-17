import json
import os

from golemcpp.golem.requested_source import RequestedSource
from golemcpp.golem import cache_configuration
from golemcpp.golem import cache_directory
from golemcpp.golem.overlay import Overlay
from golemcpp.golem.overlay_manager import (
    OverlayManager, get_overlay_manager)
from golemcpp.golem.resource_manifest import ResourceKind, ResourceManifest
from golemcpp.golem.source import Source
from golemcpp.golem.resolved_version import ResolvedVersion
from conftest import STUB_HEAD
from conftest import make_cache_configuration


def make_manager(tmp_path):
    return get_overlay_manager(make_cache_configuration(
        cache_directory.CacheDirectory(location=str(tmp_path / 'cache')),
        minimization_enabled=False))


def make_source():
    return RequestedSource.for_repository('https://example.com/overrides.git', version='main')


def test_resource_for_bakes_in_the_overrides_kind():
    source = make_source()
    resource = OverlayManager.resource_for(Overlay(source=source))

    assert resource.kind == ResourceKind.OVERLAY
    assert resource.subdir == cache_configuration.OVERLAYS_SUBDIR
    # Nothing resolved it, so it names no version -- which the key does not
    # need, since a overlay root is named after the request.
    assert resource.source == source.resolved_at(ResolvedVersion())
    assert resource.cache_key == OverlayManager.cache_key_for(Overlay(source=source))


def test_an_overlay_lands_where_it_did_before_being_resolved():
    # An overlay follows the version it was configured with, so resolving one may
    # never move what is already cached.
    source = make_source()

    unresolved = OverlayManager.resource_for(Overlay(source=source))
    resolved = OverlayManager.resource_for(
        OverlayManager.resolve_version(Overlay(source=source)))

    assert resolved.cache_key == unresolved.cache_key


def test_resolve_and_locate(tmp_path):
    manager = make_manager(tmp_path)
    source = make_source()

    cached_repository = manager.resolve_cached_resource(Overlay(source=source))

    assert cached_repository.cache_root == str(tmp_path / 'cache')
    assert cached_repository.path == os.path.join(
        str(tmp_path / 'cache'), cache_configuration.OVERLAYS_SUBDIR,
        OverlayManager.cache_key_for(Overlay(source=source)))


def test_guard_install_swaps_source_and_manifest(tmp_path):
    manager = make_manager(tmp_path)
    source = make_source()

    def populate(staging_root):
        source_dir = manager.source_path(staging_root)
        os.makedirs(source_dir)
        with open(os.path.join(source_dir, 'overrides.json'), 'w') as fileout:
            fileout.write('[]')

    item = Overlay(source=source)
    item.resolved = ResolvedVersion(reference='main', revision=STUB_HEAD)
    cached = manager.resolve_cached_resource(item)
    resource_root = manager.guard_install(cached, populate)

    assert os.path.isfile(
        os.path.join(manager.source_path(resource_root), 'overrides.json'))
    assert not os.path.exists(cached.staging_path)
    manifest = ResourceManifest.read_from_root(resource_root)
    assert manifest.kind == ResourceKind.OVERLAY.value
    assert manager.cache_manager.read_manifest_source(cached).resolved.reference == 'main'


# -- what an overlay carries ------------------------------------------------


def make_overlay(tmp_path, name, entries):
    '''An overlay directory carrying an overrides.json, as a directory source.'''
    overlay_dir = tmp_path / name
    overlay_dir.mkdir(parents=True)
    (overlay_dir / 'overrides.json').write_text(json.dumps(entries), encoding='utf-8')
    return RequestedSource.for_directory(overlay_dir.resolve().as_uri())


def load_overrides(tmp_path, sources):
    '''The layered result, read back from where the manager wrote it.'''
    manager = make_manager(tmp_path)
    cached_overlays = manager.make_available_all(
        [manager.get_overlay(source) for source in sources])
    merged_path = manager.load_overrides(
        cached_overlays,
        project_dir=str(tmp_path / 'project'),
        merged_path=str(tmp_path / 'build' / 'overrides.json'))

    if not merged_path:
        return merged_path, []

    with open(merged_path) as fp:
        return merged_path, json.load(fp)


def test_making_overlays_available_keeps_the_configured_order(tmp_path):
    manager = make_manager(tmp_path)
    sources = [make_overlay(tmp_path, name, []) for name in ('first', 'second')]

    cached_overlays = manager.make_available_all(
        [manager.get_overlay(source) for source in sources], fetch=False)

    assert len(cached_overlays) == 2
    # What an overlay carries is its content, reached from the resource root.
    assert [cached.source_path for cached in cached_overlays] == [
        manager.source_path(
            manager.resolve_cached_resource(Overlay(source=source)).path)
        for source in sources
    ]


def test_a_later_overlay_overwrites_only_the_members_it_sets(tmp_path):
    sources = [
        make_overlay(tmp_path, 'first', [
            {'repository': 'https://host/json.git', 'version': '^3.0.0', 'shallow': True}]),
        make_overlay(tmp_path, 'second', [
            {'repository': 'https://host/json.git', 'version': '^4.0.0'}]),
    ]

    _, entries = load_overrides(tmp_path, sources)

    assert len(entries) == 1
    assert entries[0]['version'] == '^4.0.0'
    # Untouched by the second overlay, so the first one still carries it.
    assert entries[0]['shallow'] is True


def test_layering_keeps_an_entry_only_one_overlay_defines(tmp_path):
    sources = [
        make_overlay(tmp_path, 'first', [
            {'repository': 'https://host/json.git', 'version': '^3.0.0'}]),
        make_overlay(tmp_path, 'second', [
            {'repository': 'https://host/fmt.git', 'version': '^10.0.0'}]),
    ]

    _, entries = load_overrides(tmp_path, sources)

    assert [entry['repository'] for entry in entries] == \
        ['https://host/json.git', 'https://host/fmt.git']


def test_an_overlay_carrying_nothing_contributes_nothing(tmp_path):
    empty = tmp_path / 'empty'
    empty.mkdir()

    merged_path, entries = load_overrides(
        tmp_path, [RequestedSource.for_directory(empty.resolve().as_uri())])

    # Nothing to write, so nothing to point at.
    assert merged_path == ''
    assert entries == []


def test_no_overlay_at_all_contributes_nothing(tmp_path):
    assert load_overrides(tmp_path, [])[0] == ''


def test_the_two_repository_kinds_do_not_share_a_cache_location(tmp_path):
    # Recipes and overrides repositories from the same URL land in different
    # subdirectories, which is the whole reason the managers are separate.
    from golemcpp.golem.cookbook import Cookbook
    from golemcpp.golem.cookbook_manager import CookbookManager

    source = make_source()

    assert (OverlayManager.resource_for(Overlay(source=source)).subdir
            != CookbookManager.resource_for(Cookbook(source=source)).subdir)
