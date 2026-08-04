import os

import pytest

from golemcpp.golem import cache_directory
from golemcpp.golem import helpers
from golemcpp.golem import network
from golemcpp.golem import resource_manifest
from golemcpp.golem.cache_manager import get_cache_manager
from golemcpp.golem.cookbook import Cookbook
from golemcpp.golem.cookbook_manager import get_cookbook_manager
from golemcpp.golem.fetch_policy import FetchMode
from golemcpp.golem.fetched import Fetched
from golemcpp.golem.directory_fetcher import DirectoryFetcher
from golemcpp.golem.git_fetcher import GitFetcher
from golemcpp.golem.resource_manager import ResourceManager
from golemcpp.golem.source import Source
from conftest import make_cache_configuration
from conftest import stub_git_probes
from conftest import STUB_HEAD


@pytest.fixture
def git_calls(monkeypatch):
    '''Every git invocation the mechanism makes, in order.'''
    calls = []
    monkeypatch.setattr(
        helpers, 'run_git',
        lambda args, cwd=None, quiet=False: calls.append(args))
    stub_git_probes(monkeypatch)
    return calls


def make_resource_manager(tmp_path):
    '''The base manager over a real cache, since it reads the configured mode.'''
    return ResourceManager(get_cache_manager(make_cache_configuration(
        cache_directory.CacheDirectory(location=str(tmp_path / 'cache')))))


def make_manager(tmp_path, **configuration):
    return get_cookbook_manager(make_cache_configuration(
        cache_directory.CacheDirectory(location=str(tmp_path / 'cache')),
        minimization_enabled=False, **configuration))


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


# -- the kind decides what to fetch; a fetcher decides how ------------------


def test_a_repository_source_is_handed_to_a_git_fetcher(tmp_path):
    manager = make_resource_manager(tmp_path)

    assert isinstance(
        manager.fetcher_for('/cache/r', Source.for_repository('https://host/r.git')),
        GitFetcher)


def test_a_directory_source_is_handed_to_a_directory_fetcher(tmp_path):
    manager = make_resource_manager(tmp_path)

    assert isinstance(
        manager.fetcher_for('/cache/r', Source.for_directory(tmp_path.resolve().as_uri())),
        DirectoryFetcher)


def test_the_fetcher_works_where_the_manager_sends_it_under_the_kind_policy(tmp_path):
    manager = make_resource_manager(tmp_path)
    source = Source.for_repository('https://host/r.git', reference='main')

    fetcher = manager.fetcher_for('/cache/r', source)

    assert fetcher.path == '/cache/r'
    assert fetcher.source is source
    assert fetcher.policy == manager.policy_for(source)


def test_populate_and_refresh_hand_back_what_the_fetch_left(tmp_path, monkeypatch):
    # The manager keeps no opinion about the fetch beyond passing its result on.
    manager = make_resource_manager(tmp_path)
    source = Source.for_repository('https://host/r.git', reference='main')
    monkeypatch.setattr(GitFetcher, 'populate', lambda self: Fetched(head='c10ned'))
    monkeypatch.setattr(GitFetcher, 'refresh', lambda self: Fetched(head='refre5hed'))

    assert manager.populate('/cache/r', source) == Fetched(head='c10ned')
    assert manager.refresh_source('/cache/r', source) == Fetched(head='refre5hed')


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


def install_on_disk(manager, cached_resource, mode=FetchMode.BLOBLESS):
    '''A resource already in a cache: its fetched source, and the manifest naming it.'''
    os.makedirs(manager.source_path(cached_resource.path), exist_ok=True)
    manager.cache_manager.write_manifest(
        cached_resource, fetched=Fetched(head=STUB_HEAD, mode=mode))
    return cached_resource


def record_the_fetch(monkeypatch, recorded):
    '''
    The whole fetch as one entry in the lifecycle: what these tests watch is where
    it lands between the hooks, not how many git commands it takes.
    '''
    def run_git(args, cwd=None, quiet=False):
        if recorded[-1:] != ['fetch']:
            recorded.append('fetch')

    monkeypatch.setattr(helpers, 'run_git', run_git)
    stub_git_probes(monkeypatch)


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
    record_the_fetch(monkeypatch, recorded)

    manager.install(cookbook)

    # The fetch is guarded, so what it makes can only run once the source is in
    # place -- and pre_install runs before anything is written.
    assert recorded == ['pre_install', 'fetch', 'post_install']


def test_a_refresh_discards_then_fetches_then_makes(tmp_path, monkeypatch):
    recorded = []
    manager = make_recording_manager(tmp_path, recorded)
    cookbook = make_cookbook()
    install_on_disk(manager, manager.resolve_cached_resource(cookbook))
    record_the_fetch(monkeypatch, recorded)

    manager.install(cookbook)

    # Nothing made from the previous source outlives it, and pre_install belongs
    # to a fresh fetch alone.
    assert recorded == ['pre_install_refresh', 'fetch', 'post_install']


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
        lambda args, cwd=None, quiet=False: open(
            os.path.join(cwd, 'fetched.txt'), 'w').close())
    stub_git_probes(monkeypatch)

    installed = manager.install(cookbook)

    assert installed.path == cached.path
    # The content sits under source/; the root holds it and the manifest naming it.
    assert os.path.isfile(os.path.join(installed.source_path, 'fetched.txt'))
    assert not os.path.exists(installed.path + '.tmp')
    manifest = resource_manifest.ResourceManifest.read_from_root(installed.path)
    assert manifest is not None
    # The manifest names what the fetch landed on, not just what was asked for.
    assert Fetched.from_manifest(manifest) == Fetched(head=STUB_HEAD, mode=FetchMode.BLOBLESS)


def test_a_refresh_records_the_commit_even_when_the_source_is_unchanged(
        tmp_path, monkeypatch, git_calls):
    # A resource following a branch keeps naming the same reference while landing
    # somewhere new every time the branch moves, so the source alone cannot say
    # whether the manifest is still true.
    manager = make_manager(tmp_path)
    cookbook = make_cookbook()
    cached = install_on_disk(manager, manager.resolve_cached_resource(cookbook))
    manager.cache_manager.write_manifest(cached, fetched=Fetched(head='0ldc0mmit', mode=FetchMode.BLOBLESS))
    stub_git_probes(monkeypatch, head='newc0mmit')

    manager.install(cookbook)

    assert Fetched.from_manifest(
        resource_manifest.ResourceManifest.read_from_root(cached.path)) == \
        Fetched(head='newc0mmit', mode=FetchMode.BLOBLESS)


def test_install_refreshes_an_existing_resource_in_place(tmp_path, git_calls):
    manager = make_manager(tmp_path)
    cookbook = make_cookbook()
    install_on_disk(manager, manager.resolve_cached_resource(cookbook))

    manager.install(cookbook)

    # Refreshed, not re-cloned: the cache root is kept.
    assert git_calls == [
        ['clean', '-ffxd'],
        ['submodule', 'foreach', '--recursive', 'git', 'clean', '-ffxd'],
        ['fetch', '--prune', '--prune-tags', '--tags', 'origin'],
        ['reset', '--hard', 'origin/main'],
        ['submodule', 'foreach', '--recursive', 'git', 'reset', '--hard'],
        ['submodule', 'sync', '--recursive'],
        ['submodule', 'update', '--init', '--recursive', '--filter=blob:none'],
    ]


def test_install_can_leave_an_existing_resource_alone(tmp_path, git_calls, monkeypatch):
    recorded = []
    manager = make_recording_manager(tmp_path, recorded)
    cookbook = make_cookbook()
    cached = install_on_disk(manager, manager.resolve_cached_resource(cookbook))
    touched = []
    monkeypatch.setattr(
        resource_manifest.ResourceManifest, 'touch',
        staticmethod(touched.append))

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
    assert git_calls == [['clone', '--filter=blob:none', '--', 'https://host/r.git', '.'],
                         ['reset', '--hard', 'origin/main'],
                         ['submodule', 'update', '--init', '--recursive', '--filter=blob:none']]


def test_install_reuses_a_cached_resource_the_caller_already_resolved(tmp_path, git_calls):
    manager = make_manager(tmp_path)
    cookbook = make_cookbook()
    cached = manager.resolve_cached_resource(cookbook)

    resolutions = []
    manager.cache_manager.resolve_cached_resource = \
        lambda *args, **kwargs: resolutions.append(1)

    assert manager.install(cookbook, cached_resource=cached).path == cached.path
    assert resolutions == []


# -- changing what a root holds belongs to resolve --------------------------


def install_in_another_mode(manager, cookbook):
    '''A cached resource holding a full clone, where blobless is now configured.'''
    return install_on_disk(
        manager, manager.resolve_cached_resource(cookbook), mode=FetchMode.FULL)


def recorded_fetched(cached):
    return Fetched.from_manifest(
        resource_manifest.ResourceManifest.read_from_root(cached.path))


def test_a_root_in_another_mode_is_converted_where_a_remote_may_be_reached(
        tmp_path, git_calls):
    manager = make_manager(tmp_path)
    cookbook = make_cookbook()
    cached = install_in_another_mode(manager, cookbook)

    with network.allowed():
        manager.install(cookbook, refresh=False)

    assert git_calls == [
        ['config', 'remote.origin.promisor', 'true'],
        ['config', 'remote.origin.partialclonefilter', 'blob:none'],
    ]
    # Written back, so the conversion is done once rather than on every resolve.
    assert recorded_fetched(cached) == Fetched(head=STUB_HEAD, mode=FetchMode.BLOBLESS)


def test_a_root_in_another_mode_is_used_as_it_stands_anywhere_else(
        tmp_path, git_calls, monkeypatch):
    # A build refreshes without being allowed to reach a remote, and converting a
    # root may have to. It keeps the mode it has until the next resolve, and the
    # manifest keeps saying so.
    manager = make_manager(tmp_path)
    cookbook = make_cookbook()
    cached = install_in_another_mode(manager, cookbook)
    stub_git_probes(monkeypatch, mode=FetchMode.FULL)

    manager.install(cookbook)

    assert ['config', 'remote.origin.promisor', 'true'] not in git_calls
    assert recorded_fetched(cached) == Fetched(head=STUB_HEAD, mode=FetchMode.FULL)


def test_a_root_that_cannot_be_converted_is_obtained_again(tmp_path, git_calls):
    # Nothing asked for a refresh, but what is there cannot serve: becoming
    # shallow is the one conversion that is not worth doing in place.
    manager = make_manager(tmp_path, fetch_mode=FetchMode.SHALLOW)
    cookbook = make_cookbook()
    install_in_another_mode(manager, cookbook)

    with network.allowed():
        manager.install(cookbook, refresh=False)

    assert git_calls[:2] == [['init'], ['remote', 'add', 'origin', 'https://host/r.git']]


def test_a_read_only_root_is_never_converted(tmp_path, git_calls):
    # Converting writes, and that location is not ours to write into.
    manager = make_read_only_manager(tmp_path)
    cookbook = make_cookbook()
    cached = install_in_another_mode(manager, cookbook)

    with network.allowed():
        assert manager.install(cookbook, refresh=False).path == cached.path

    assert git_calls == []
    assert recorded_fetched(cached) == Fetched(head=STUB_HEAD, mode=FetchMode.FULL)


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
    assert git_calls == [['clone', '--filter=blob:none', '--', 'https://host/r.git', '.'],
                         ['reset', '--hard', 'origin/main'],
                         ['submodule', 'update', '--init', '--recursive', '--filter=blob:none']]


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


# -- fetching is a resolve step ---------------------------------------------
# These run the real helpers.run_git, so they see the rule the way a command
# does. Nothing is spawned: the refusal comes before git is called.


def test_fetching_a_resource_outside_a_network_scope_is_refused(tmp_path):
    manager = make_manager(tmp_path)

    with pytest.raises(RuntimeError, match='Run golem resolve first'):
        manager.install(make_cookbook())


def test_the_staging_directory_is_removed_when_the_fetch_is_refused(tmp_path):
    manager = make_manager(tmp_path)
    cached = manager.resolve_cached_resource(make_cookbook())

    with pytest.raises(RuntimeError):
        manager.install(make_cookbook())

    assert not os.path.exists(cached.staging_path)
