import os
import subprocess

import pytest

from golemcpp.golem import cache_directory
from golemcpp.golem import helpers
from golemcpp.golem import resource_manifest
from golemcpp.golem.cache_manager import get_cache_manager
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


def test_install_does_not_touch_the_cache_when_not_fetching(tmp_path, git_calls):
    manager = make_manager(tmp_path)
    source = Source.for_repository('https://host/r.git', reference='main')
    cached = manager.resolve_cached_resource(source)

    assert manager.install(cached, source, fetch=False) == cached.path
    assert git_calls == []
    assert not os.path.exists(cached.path)


def test_install_stages_a_fresh_resource_with_its_manifest(tmp_path, monkeypatch):
    manager = make_manager(tmp_path)
    source = Source.for_repository('https://host/r.git', reference='main')
    cached = manager.resolve_cached_resource(source)

    # Stand in for the clone: the staging root is what populate is handed.
    monkeypatch.setattr(
        helpers, 'run_git',
        lambda args, cwd=None, stdout=None: open(
            os.path.join(cwd, 'fetched.txt'), 'w').close())

    root = manager.install(cached, source)

    assert root == cached.path
    # The content sits under source/; the root holds it and the manifest naming it.
    assert os.path.isfile(os.path.join(manager.source_path(root), 'fetched.txt'))
    assert not os.path.exists(root + '.tmp')
    assert resource_manifest.ResourceManifest.read_from_root(root) is not None


def test_install_refreshes_an_existing_resource_in_place(tmp_path, git_calls):
    manager = make_manager(tmp_path)
    source = Source.for_repository('https://host/r.git', reference='main')
    cached = manager.resolve_cached_resource(source)
    os.makedirs(manager.source_path(cached.path))

    manager.install(cached, source)

    # Refreshed, not re-cloned: the cache root is kept.
    assert git_calls == [
        ['fetch', 'origin'],
        ['reset', '--hard', 'origin/main'],
    ]


def test_install_can_leave_an_existing_resource_alone(tmp_path, git_calls, monkeypatch):
    manager = make_manager(tmp_path)
    source = Source.for_repository('https://host/r.git', reference='main')
    cached = manager.resolve_cached_resource(source)
    os.makedirs(manager.source_path(cached.path))
    touched = []
    monkeypatch.setattr(resource_manifest, 'touch_last_used', touched.append)

    manager.install(cached, source, refresh=False)

    assert git_calls == []
    # Still counts as used, which is what keeps it from being pruned.
    assert touched == [cached.path]
