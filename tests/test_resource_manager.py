import os
import subprocess

import pytest

from golemcpp.golem import cache_directory
from golemcpp.golem import helpers
from golemcpp.golem import resource_manifest
from golemcpp.golem.cache_manager import get_cache_manager
from golemcpp.golem.cookbook import Cookbook
from golemcpp.golem.cookbook_manager import get_cookbook_manager
from golemcpp.golem.resource_manager import FetchPolicy
from golemcpp.golem.resource_manager import ResourceManager
from golemcpp.golem.resource_manager import ORIGIN_FILENAME
from golemcpp.golem.source import Source
from conftest import make_cache_configuration


@pytest.fixture
def git_calls(monkeypatch):
    '''Every git invocation the mechanism makes, in order.'''
    calls = []
    monkeypatch.setattr(
        helpers, 'run_git',
        lambda args, cwd=None, stdout=None: calls.append(args))
    return calls


def make_manager(tmp_path):
    return get_cookbook_manager(make_cache_configuration(
        cache_directory.CacheDirectory(location=str(tmp_path / 'cache')),
        minimization_enabled=False))


def test_a_manager_holds_its_cache_manager_and_exposes_its_locations(tmp_path):
    cache_dir = cache_directory.CacheDirectory(location=str(tmp_path / 'cache'))
    cache_manager = get_cache_manager(make_cache_configuration(cache_dir))

    manager = ResourceManager(cache_manager)

    assert manager.cache_manager is cache_manager
    assert manager.locations == cache_manager.locations


def test_every_kind_keeps_its_content_under_source():
    # The root is the resource: it holds the manifest naming it and whatever gets
    # built from the source, so no kind may fetch straight into it.
    from golemcpp.golem.cache_configuration import SOURCE_DIRNAME
    from golemcpp.golem.dependency_manager import DependencyManager
    from golemcpp.golem.cookbook_manager import CookbookManager
    from golemcpp.golem.overlay_manager import OverlayManager
    from golemcpp.golem.tool_manager import ToolManager

    for kind in (ResourceManager, DependencyManager, CookbookManager,
                 OverlayManager, ToolManager):
        assert kind.source_path('/cache/r') == os.path.join('/cache/r', SOURCE_DIRNAME), \
            '{} fetches outside source/'.format(kind.__name__)


# -- the git sequence a policy produces -------------------------------------


def test_the_default_policy_clones_and_tracks_the_branch(git_calls):
    source = Source.for_repository('https://host/r.git', reference='main')

    ResourceManager.clone_source('/cache/r', source, ResourceManager.policy_for(source))

    assert git_calls == [
        ['clone', '--', 'https://host/r.git', '.'],
        ['reset', '--hard', 'origin/main'],
    ]


def test_the_default_policy_refreshes_by_fetching_the_branch(git_calls):
    source = Source.for_repository('https://host/r.git', reference='main')

    ResourceManager.update_source('/cache/r', source, ResourceManager.policy_for(source))

    assert git_calls == [
        ['fetch', 'origin'],
        ['reset', '--hard', 'origin/main'],
    ]


def test_a_checkout_lands_between_the_clone_and_the_reset(git_calls):
    source = Source.for_repository('https://host/r.git')
    policy = FetchPolicy(checkout='v3.12.0', reference='cafebabe', submodules=True)

    ResourceManager.clone_source('/cache/r', source, policy)

    assert git_calls == [
        ['clone', '--', 'https://host/r.git', '.'],
        ['checkout', 'v3.12.0'],
        ['reset', '--hard', 'cafebabe'],
        ['submodule', 'update', '--init', '--recursive', '--depth=1'],
    ]


def test_a_shallow_policy_fetches_only_the_requested_commit(git_calls):
    source = Source.for_repository('https://host/r.git')
    policy = FetchPolicy(shallow=True, checkout='v3.12.0', reference='cafebabe',
                         submodules=True)

    ResourceManager.clone_source('/cache/r', source, policy)

    assert git_calls == [
        ['init'],
        ['remote', 'add', 'origin', 'https://host/r.git'],
        ['fetch', '--depth=1', 'origin', 'cafebabe'],
        ['reset', '--hard', 'FETCH_HEAD'],
        ['submodule', 'update', '--init', '--recursive', '--depth=1'],
    ]


def test_a_cleaning_policy_discards_local_changes_without_fetching(git_calls):
    source = Source.for_repository('https://host/r.git')
    policy = FetchPolicy(reference='', submodules=True, clean=True, fetch_remote=False)

    ResourceManager.update_source('/cache/r', source, policy)

    assert git_calls == [
        ['clean', '-ffxd'],
        ['submodule', 'foreach', '--recursive', 'git', 'clean', '-ffxd'],
        ['reset', '--hard'],
        ['submodule', 'foreach', '--recursive', 'git', 'reset', '--hard'],
        ['submodule', 'update', '--init', '--recursive'],
    ]


def test_cleaning_stays_quiet(monkeypatch):
    stdouts = []
    monkeypatch.setattr(
        helpers, 'run_git',
        lambda args, cwd=None, stdout=None: stdouts.append(stdout))

    ResourceManager.update_source(
        '/cache/r', Source.for_repository('https://host/r.git'),
        FetchPolicy(clean=True, fetch_remote=False))

    assert set(stdouts) == {subprocess.DEVNULL}


# -- kind dispatch ----------------------------------------------------------


def test_populate_copies_a_directory_source_and_records_its_origin(tmp_path, git_calls):
    origin = tmp_path / 'mylib'
    origin.mkdir()
    (origin / 'marker.txt').write_text('copied\n', encoding='utf-8')
    destination = tmp_path / 'cache' / 'mylib'

    ResourceManager(cache_manager=None).populate(
        str(destination), Source.for_directory(origin.resolve().as_uri()))

    assert (destination / 'marker.txt').read_text(encoding='utf-8') == 'copied\n'
    assert (destination / ORIGIN_FILENAME).read_text(encoding='utf-8') == \
        origin.resolve().as_uri()
    # A copied source has no remote to talk to.
    assert git_calls == []


def test_populate_clones_a_git_source(tmp_path, git_calls):
    destination = tmp_path / 'cache' / 'r'

    ResourceManager(cache_manager=None).populate(
        str(destination), Source.for_repository('https://host/r.git', reference='main'))

    assert git_calls == [
        ['clone', '--', 'https://host/r.git', '.'],
        ['reset', '--hard', 'origin/main'],
    ]
    assert destination.is_dir()


def test_refresh_recopies_a_directory_source(tmp_path, git_calls):
    origin = tmp_path / 'mylib'
    origin.mkdir()
    (origin / 'marker.txt').write_text('fresh\n', encoding='utf-8')
    destination = tmp_path / 'cache' / 'mylib'
    destination.mkdir(parents=True)
    (destination / 'marker.txt').write_text('stale\n', encoding='utf-8')

    ResourceManager(cache_manager=None).refresh_source(
        str(destination), Source.for_directory(origin.resolve().as_uri()))

    assert (destination / 'marker.txt').read_text(encoding='utf-8') == 'fresh\n'
    assert git_calls == []


# -- the local source is checked before anything touches it -----------------


def test_a_missing_local_source_is_named(tmp_path):
    source = Source.for_directory((tmp_path / 'absent').resolve().as_uri())

    with pytest.raises(RuntimeError, match="Can't find local source directory"):
        ResourceManager.validate_local_source(source)


def test_a_local_source_that_is_a_file_is_named(tmp_path):
    a_file = tmp_path / 'mylib'
    a_file.write_text('not a directory', encoding='utf-8')
    source = Source.for_directory(a_file.resolve().as_uri())

    with pytest.raises(RuntimeError, match='not a directory'):
        ResourceManager.validate_local_source(source)


def test_a_remote_source_has_no_local_path_to_check():
    assert ResourceManager.validate_local_source(
        Source.for_repository('https://host/r.git')) is None


# -- install: what happens around the fetch ---------------------------------


def make_cookbook():
    return Cookbook(
        source=Source.for_repository('https://host/r.git', reference='main'))


def make_recording_manager(tmp_path, recorded):
    '''A cookbook manager whose whole lifecycle is recorded, in order.'''
    manager = make_manager(tmp_path)
    manager.pre_install = lambda item: recorded.append('pre_install')
    manager.pre_install_refresh = \
        lambda root, item: recorded.append('pre_install_refresh')
    manager.post_install = lambda root, item: recorded.append('post_install')
    return manager


def make_read_only_manager(tmp_path):
    return get_cookbook_manager(make_cache_configuration(
        cache_directory.CacheDirectory(
            location=str(tmp_path / 'cache'), is_read_only=True),
        minimization_enabled=False))


def install_on_disk(manager, cached_resource):
    '''A resource already in a cache: its fetched source, and the manifest naming it.'''
    os.makedirs(manager.source_path(cached_resource.path), exist_ok=True)
    manager.cache_manager.write_manifest(
        cached_resource.path, cached_resource.resource)
    return cached_resource


def test_a_kind_with_nothing_to_resolve_hands_its_item_back():
    # The base hands its item straight back, which is what a kind that has no
    # version of its own inherits.
    item = Source.for_repository('https://host/r.git', reference='main')

    assert ResourceManager.resolve_version(item) is item


def test_locating_a_resource_resolves_its_version_first(tmp_path):
    # The resolved reference is part of what identifies a resource, so a location
    # worked out before it would name a different one.
    manager = make_manager(tmp_path)
    manager.resolve_version = lambda cookbook: Cookbook(
        source=cookbook.source, version='v3.12.0')

    cached = manager.resolve_cached_resource(make_cookbook())

    assert cached.cache_key == Source.for_repository(
        'https://host/r.git', reference='v3.12.0').get_cache_key()


def test_the_lifecycle_hooks_do_nothing_by_default():
    # Every kind gets them; only the ones that make something from their source
    # fill them in.
    assert ResourceManager.pre_install('item') is None
    assert ResourceManager.pre_install_refresh('/cache/r', 'item') is None
    assert ResourceManager.post_install('/cache/r', 'item') is None


def test_a_fresh_install_prepares_then_fetches_then_makes(tmp_path, monkeypatch):
    recorded = []
    manager = make_recording_manager(tmp_path, recorded)
    cookbook = make_cookbook()
    monkeypatch.setattr(
        helpers, 'run_git',
        lambda args, cwd=None, stdout=None: recorded.append('fetch'))

    manager.install(cookbook)

    # The fetch is guarded, so what it makes can only run once the source is in
    # place -- and pre_install runs before anything is written.
    assert recorded == ['pre_install', 'fetch', 'fetch', 'post_install']


def test_a_refresh_discards_then_fetches_then_makes(tmp_path, monkeypatch):
    recorded = []
    manager = make_recording_manager(tmp_path, recorded)
    cookbook = make_cookbook()
    install_on_disk(manager, manager.resolve_cached_resource(cookbook))
    monkeypatch.setattr(
        helpers, 'run_git',
        lambda args, cwd=None, stdout=None: recorded.append('fetch'))

    manager.install(cookbook)

    # Nothing made from the previous source outlives it, and pre_install belongs
    # to a fresh fetch alone.
    assert recorded == ['pre_install_refresh', 'fetch', 'fetch', 'post_install']


def test_a_resource_is_installed_once_its_source_is_there(tmp_path):
    # The fetched source is what a consumer reads, so that is what says the
    # resource is installed. The root existing only says which cache holds it.
    manager = make_manager(tmp_path)
    cached = manager.resolve_cached_resource(make_cookbook())
    os.makedirs(cached.path)

    assert cached.exists() is True
    assert manager.is_installed(cached) is False

    os.makedirs(manager.source_path(cached.path))

    assert manager.is_installed(cached) is True


def test_install_stages_a_fresh_resource_with_its_manifest(tmp_path, monkeypatch):
    manager = make_manager(tmp_path)
    cookbook = make_cookbook()
    cached = manager.resolve_cached_resource(cookbook)

    # Stand in for the clone: the staging root is what populate is handed.
    monkeypatch.setattr(
        helpers, 'run_git',
        lambda args, cwd=None, stdout=None: open(
            os.path.join(cwd, 'fetched.txt'), 'w').close())

    installed = manager.install(cookbook)

    assert installed.path == cached.path
    # The content sits under source/; the root holds it and the manifest naming it.
    assert os.path.isfile(os.path.join(installed.source_path, 'fetched.txt'))
    assert not os.path.exists(installed.path + '.tmp')
    assert resource_manifest.ResourceManifest.read_from_root(installed.path) is not None


def test_install_refreshes_an_existing_resource_in_place(tmp_path, git_calls):
    manager = make_manager(tmp_path)
    cookbook = make_cookbook()
    install_on_disk(manager, manager.resolve_cached_resource(cookbook))

    manager.install(cookbook)

    # Refreshed, not re-cloned: the cache root is kept.
    assert git_calls == [
        ['fetch', 'origin'],
        ['reset', '--hard', 'origin/main'],
    ]


def test_install_can_leave_an_existing_resource_alone(tmp_path, git_calls, monkeypatch):
    recorded = []
    manager = make_recording_manager(tmp_path, recorded)
    cookbook = make_cookbook()
    cached = install_on_disk(manager, manager.resolve_cached_resource(cookbook))
    touched = []
    monkeypatch.setattr(resource_manifest, 'touch_last_used', touched.append)

    manager.install(cookbook, refresh=False)

    assert git_calls == []
    assert recorded == []
    # Resolving it counts as using it, which is what keeps it from being pruned.
    assert touched == [cached.path]


def test_install_clones_a_resource_that_is_not_there(tmp_path, git_calls):
    manager = make_manager(tmp_path)
    cookbook = make_cookbook()

    installed = manager.install(cookbook)

    assert manager.is_installed(installed)
    assert git_calls == [['clone', '--', 'https://host/r.git', '.'],
                         ['reset', '--hard', 'origin/main']]


def test_install_reuses_a_cached_resource_the_caller_already_resolved(tmp_path, git_calls):
    manager = make_manager(tmp_path)
    cookbook = make_cookbook()
    cached = manager.resolve_cached_resource(cookbook)

    resolutions = []
    manager.cache_manager.resolve_cached_resource = \
        lambda *args, **kwargs: resolutions.append(1)

    assert manager.install(cookbook, cached_resource=cached).path == cached.path
    assert resolutions == []


# -- install writes, so a read-only location is refused ---------------------


def test_populating_a_read_only_cache_is_refused(tmp_path):
    manager = make_read_only_manager(tmp_path)

    with pytest.raises(RuntimeError, match='read-only cache location'):
        manager.install(make_cookbook())


def test_refreshing_a_read_only_cache_is_refused(tmp_path, git_calls):
    # The resource is there, but refreshing it writes just as populating does.
    manager = make_read_only_manager(tmp_path)
    cookbook = make_cookbook()
    install_on_disk(manager, manager.resolve_cached_resource(cookbook))

    with pytest.raises(RuntimeError, match='read-only cache location'):
        manager.install(cookbook)

    assert git_calls == []


def test_a_read_only_resource_is_handed_back_when_nothing_is_refreshed(tmp_path, git_calls):
    manager = make_read_only_manager(tmp_path)
    cookbook = make_cookbook()
    cached = install_on_disk(manager, manager.resolve_cached_resource(cookbook))

    # Nothing is written, so there is nothing to refuse.
    assert manager.install(cookbook, refresh=False).path == cached.path
    assert git_calls == []


# -- make_available reads, so a populated read-only location is kept as is --


def test_make_available_installs_into_a_writable_cache(tmp_path, git_calls):
    manager = make_manager(tmp_path)

    available = manager.make_available(make_cookbook())

    assert manager.is_installed(available)
    assert available.is_read_only is False
    assert git_calls == [['clone', '--', 'https://host/r.git', '.'],
                         ['reset', '--hard', 'origin/main']]


def test_make_available_keeps_a_read_only_resource_as_it_stands(tmp_path, git_calls):
    manager = make_read_only_manager(tmp_path)
    cookbook = make_cookbook()
    cached = install_on_disk(manager, manager.resolve_cached_resource(cookbook))

    available = manager.make_available(cookbook)

    assert available.path == cached.path
    assert available.is_read_only is True
    assert git_calls == []


def test_make_available_refuses_an_empty_read_only_cache(tmp_path):
    # Nothing to serve there, and nothing may be written.
    manager = make_read_only_manager(tmp_path)

    with pytest.raises(RuntimeError, match='read-only cache location'):
        manager.make_available(make_cookbook())


def test_make_available_does_not_touch_the_cache_when_not_fetching(tmp_path, git_calls):
    manager = make_read_only_manager(tmp_path)
    cookbook = make_cookbook()
    cached = manager.resolve_cached_resource(cookbook)

    # Not even the empty read-only cache is refused: nothing is asked of it.
    assert manager.make_available(cookbook, fetch=False).path == cached.path
    assert git_calls == []
    assert not os.path.exists(cached.path)


def test_make_available_all_hands_back_a_resource_per_item_in_order(tmp_path, git_calls):
    manager = make_manager(tmp_path)
    items = [
        Cookbook(source=Source.for_repository(
            'https://host/{}.git'.format(name), reference='main'))
        for name in ('first', 'second')
    ]

    cached_resources = manager.make_available_all(items, fetch=False)

    assert [cached.path for cached in cached_resources] == \
        [manager.resolve_cached_resource(item).path for item in items]
    assert git_calls == []
