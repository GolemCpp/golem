import hashlib
import os

from golemcpp.golem.resolved_version import ResolvedVersion
from golemcpp.golem import cache_configuration
from golemcpp.golem import cache_directory
from golemcpp.golem import helpers
from golemcpp.golem.dependency import Dependency
from golemcpp.golem.dependency_manager import DependencyManager, get_dependency_manager
from golemcpp.golem.resource_manifest import ResourceKind
from golemcpp.golem.source import Source
from golemcpp.golem.version_resolver import VersionResolver
from golemcpp.golem.fetch_policy import FetchMode
from support import default_setting
from support import make_cache_configuration
from support import stub_git_probes
from golemcpp.golem.locator import Locator


DEPENDENCIES_SUBDIR = cache_configuration.DEPENDENCIES_SUBDIR


def make_manager(tmp_path, minimization_enabled=False):
    return get_dependency_manager(make_cache_configuration(
        cache_directory.CacheDirectory(location=str(tmp_path / 'cache')),
        minimization_enabled=minimization_enabled))


def make_dependency():
    dep = Dependency(
        repository='https://github.com/nlohmann/json.git',
        version='^3.0.0')
    dep.resolved = ResolvedVersion(revision='1234567890abcdef')
    return dep


def expected_cache_key(dep):
    return DependencyManager.cache_key_for(dep)


def test_resource_for_uses_the_dependency_source():
    dep = Dependency(name='json', repository='https://example.com/json.git')
    resource = DependencyManager.resource_for(dep)

    assert resource.kind == ResourceKind.DEPENDENCY
    assert resource.source.type == 'git'
    assert resource.source.locator == Locator('https://example.com/json.git')
    assert resource.locator == resource.source.locator
    assert resource.cache_key == DependencyManager.cache_key_for(dep)


def make_resolved_dependency():
    # Locating a dependency resolves it, and a unit test has no remote to resolve
    # against: these come pre-resolved.
    dep = Dependency(name='json', repository='https://example.com/json.git')
    dep.resolved = ResolvedVersion(revision='1234567890abcdef')
    return dep


def test_resolve_and_write(tmp_path):
    manager = make_manager(tmp_path)
    dep = make_resolved_dependency()

    cached = manager.resolve_cached_resource(dep)
    os.makedirs(cached.path)
    manager.cache_manager.write_manifest(cached)

    source = manager.cache_manager.read_manifest_source(cached)
    assert source.locator == Locator('https://example.com/json.git')


def test_guard_install_swaps_source_and_manifest(tmp_path):
    manager = make_manager(tmp_path)
    dep = make_resolved_dependency()

    def populate(staging_root):
        source_dir = os.path.join(staging_root, cache_configuration.SOURCE_DIRNAME)
        os.makedirs(source_dir)
        with open(os.path.join(source_dir, 'CMakeLists.txt'), 'w') as fileout:
            fileout.write('project(json)')

    cached = manager.resolve_cached_resource(dep)
    resource_root = manager.guard_install(cached, populate)

    assert os.path.isfile(
        os.path.join(resource_root, cache_configuration.SOURCE_DIRNAME, 'CMakeLists.txt'))
    assert not os.path.exists(cached.staging_path)
    source = manager.cache_manager.read_manifest_source(cached)
    assert source.locator == Locator('https://example.com/json.git')


def test_resolved_location_reuses_the_repository_cache_key(tmp_path):
    manager = make_manager(tmp_path)
    dep = make_dependency()

    cached_dep = manager.resolve_cached_resource(dep)

    assert cached_dep.path == os.path.join(
        cached_dep.cache_root, DEPENDENCIES_SUBDIR, expected_cache_key(dep))


def test_resolved_location_is_minimized_flat_when_enabled(tmp_path):
    manager = make_manager(tmp_path, minimization_enabled=True)
    dep = make_dependency()

    expected_name = hashlib.sha256(
        '{}/{}'.format(DEPENDENCIES_SUBDIR, expected_cache_key(dep)).encode('utf-8')
    ).hexdigest()[:8]

    cached_dep = manager.resolve_cached_resource(dep)

    assert cached_dep.path == os.path.join(cached_dep.cache_root, expected_name)
    # Flat: no per-kind subdirectory in the path.
    assert DEPENDENCIES_SUBDIR not in os.path.relpath(
        cached_dep.path, cached_dep.cache_root)


# -- what a dependency asks of the shared fetch mechanism -------------------


def test_the_source_tree_sits_under_the_resource_root():
    # The root also holds what was built from the source, so the source itself
    # gets a subdirectory of its own.
    assert DependencyManager.source_path('/cache/json@x') == os.path.join(
        '/cache/json@x', cache_configuration.SOURCE_DIRNAME)


def test_the_policy_pins_to_the_resolved_commit(tmp_path):
    dep = Dependency(repository='https://example.com/json.git', version='^3.0.0')
    dep.resolved = ResolvedVersion(reference='v3.12.0', revision='cafebabecafebabe')

    policy = make_manager(tmp_path).policy_for(dep)

    assert policy.revision == 'cafebabecafebabe'
    # Pinned to a commit, so a refresh has nothing to fetch.
    assert policy.fetch_remote is False
    # Nothing of its own to say about how much to fetch.
    assert policy.fetch_mode == default_setting('GOLEM_GIT_FETCH_MODE')


def test_the_policy_carries_the_shallow_request(tmp_path):
    # The one resource that departs from the configured mode, because a golemfile
    # said so about a repository too heavy to clone whole.
    dep = Dependency(repository='https://example.com/json.git', shallow=True)
    dep.resolved = ResolvedVersion(revision='cafebabe')

    assert make_manager(tmp_path).policy_for(dep).fetch_mode == FetchMode.SHALLOW


def test_locating_a_dependency_resolves_its_version(monkeypatch, resolving):
    dep = Dependency(repository='https://example.com/json.git', version='^3.0.0')
    resolved = []
    monkeypatch.setattr(Dependency, 'resolve', lambda self: resolved.append(self))

    assert DependencyManager.resolve_version(dep) is dep
    assert resolved == [dep]


def test_a_refresh_keeps_what_was_built_from_the_dependency(tmp_path):
    # A dependency is built by a later command, so its include/ and its artifacts
    # have to survive a refresh: only a kind that says so throws anything away.
    manager = make_manager(tmp_path)
    dep = make_dependency()
    root = manager.resolve_cached_resource(dep).path
    os.makedirs(os.path.join(root, 'include'))

    DependencyManager.pre_install_refresh(root, dep)

    assert os.path.isdir(os.path.join(root, 'include'))


def test_a_dependency_produces_the_expected_clone_sequence(tmp_path, monkeypatch):
    dep = Dependency(repository='https://example.com/json.git', version='^3.0.0')
    dep.resolved = ResolvedVersion(reference='v3.12.0', revision='cafebabecafebabe')
    calls = []
    monkeypatch.setattr(
        helpers, 'run_git', lambda args, cwd=None, quiet=False: calls.append(args))
    stub_git_probes(monkeypatch)

    # A root under the temporary tree: the clone creates the directory it works
    # in, and a hard-coded one would be a real directory outside the run.
    make_manager(tmp_path).fetcher_for(str(tmp_path / 'json' / 'source'), dep).populate()

    assert calls == [
        ['clone', '--filter=blob:none', '--', 'https://example.com/json.git', '.'],
        ['reset', '--hard', 'cafebabecafebabe'],
        ['submodule', 'update', '--init', '--recursive', '--filter=blob:none'],
    ]


def test_resolved_location_prefers_an_existing_non_minimized_layout(tmp_path):
    manager = make_manager(tmp_path, minimization_enabled=True)
    dep = make_dependency()

    non_minimized = os.path.join(
        str(tmp_path / 'cache'), DEPENDENCIES_SUBDIR, expected_cache_key(dep))
    os.makedirs(non_minimized, exist_ok=True)

    # A resource already present under the classic layout keeps its location even
    # though minimization is enabled.
    assert manager.resolve_cached_resource(dep).path == non_minimized


def test_a_cached_resource_is_resolved_once_and_kept_on_the_dependency(tmp_path):
    manager = make_manager(tmp_path)
    dep = make_dependency()

    cached = manager.get_cached_resource(dep)

    assert cached is dep.cached_resource
    assert manager.get_cached_resource(dep) is cached


def test_locating_a_dependency_resolves_its_version_first(tmp_path, monkeypatch, resolving):
    # The cache key comes from the resolved reference, so a location worked out
    # before resolution would name another resource. There is no way to obtain
    # one: asking where a dependency lives resolves it on the way.
    manager = make_manager(tmp_path)
    dep = Dependency(name='json', repository='https://example.com/json.git')
    monkeypatch.setattr(
        VersionResolver, 'resolve',
        staticmethod(lambda *args, **kwargs: ResolvedVersion(
            reference='3.11.3', revision='1234567890abcdef')))

    cached = manager.get_cached_resource(dep)

    assert dep.resolved.revision == '1234567890abcdef'
    assert cached.cache_key == DependencyManager.cache_key_for(dep)


def test_updating_a_cached_resource_replaces_the_one_kept(tmp_path):
    manager = make_manager(tmp_path)
    dep = make_dependency()
    first = manager.get_cached_resource(dep)

    second = manager.update_cached_resource(dep)

    assert second is not first
    assert second is dep.cached_resource
