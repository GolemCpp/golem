import os
from dataclasses import replace

import pytest

from golemcpp.golem import cache_configuration
from golemcpp.golem import cache_directory
from golemcpp.golem import cache_resolution_policy
from golemcpp.golem import helpers
from golemcpp.golem import tool
from golemcpp.golem import tool_manager
from golemcpp.golem import tool_registry
from golemcpp.golem import resource_manifest
from conftest import default_setting
from conftest import make_cache_configuration


@pytest.fixture(autouse=True)
def stub_version_resolver(monkeypatch):
    # Tool install now resolves the version like a dependency (git ls-remote);
    # stub it so unit tests neither touch the network nor depend on live tags.
    monkeypatch.setattr(
        tool.VersionResolver, 'resolve',
        staticmethod(lambda url, version, version_regex='': (version, 'deadbeef')))


@pytest.fixture(autouse=True)
def git_calls(monkeypatch):
    '''Every git invocation installing a tool makes, in order.'''
    calls = []

    def run_git(args, cwd=None, stdout=None):
        calls.append(args)
        if args[0] == 'clone':
            os.makedirs(cwd, exist_ok=True)

    monkeypatch.setattr(helpers, 'run_git', run_git)
    return calls


def write_tool_manifest(resource_root, *, name='cppfront', version='v0.8.1'):
    resource_manifest.ResourceManifest.create(
        kind=resource_manifest.ResourceKind.TOOL,
        cache_key=name,
        source={'type': 'git', 'location': 'u', 'reference': version},
    ).write_to_root(str(resource_root))


def replace_cppfront_tool(monkeypatch, **changes):
    monkeypatch.setitem(
        tool_registry.TOOLS,
        'cppfront',
        replace(tool_registry.TOOLS['cppfront'], **changes),
    )


def make_tools_cache_directory(tmp_path, *, tools_cache_directory=None):
    if tools_cache_directory is None:
        tools_cache_directory = str(tmp_path / 'tools-cache')

    return tools_cache_directory


def make_tool_manager(tmp_path, *, tools_cache_directory=None, locations=None,
                       resolution_policy=cache_resolution_policy.CacheResolutionPolicy.STRICT,
                       minimization_enabled=False,
                       minimization_length=default_setting('GOLEM_CACHE_MINIMIZATION_LENGTH')):
    # Tools are resolved across the configured cache locations, exactly like every
    # other resource kind. Classic-layout tests keep minimization disabled for
    # deterministic <root>/tools/<name> paths; minimized-layout tests opt in.
    if locations is None:
        locations = [cache_directory.CacheDirectory(location=make_tools_cache_directory(
            tmp_path, tools_cache_directory=tools_cache_directory))]
    conf = make_cache_configuration(
        *locations,
        resolution_policy=resolution_policy,
        minimization_enabled=minimization_enabled,
        minimization_length=minimization_length)
    return tool_manager.get_tool_manager(conf)


def classic_tool_root(base_cache_directory, tool_name='cppfront'):
    return os.path.join(str(base_cache_directory), cache_configuration.TOOLS_SUBDIR, tool_name)


def test_install_tool_dispatches_to_registry_tool(monkeypatch, tmp_path):
    captured = {}
    tools_cache_directory = tmp_path / 'tools-cache'

    def fake_build(resource_root):
        captured['resource_root'] = resource_root
        return None

    replace_cppfront_tool(
        monkeypatch,
        build_handler=fake_build,
    )

    manager = make_tool_manager(tmp_path, tools_cache_directory=str(tools_cache_directory))
    installed_tool = manager.get_tool('cppfront')
    cached_tool = manager.install(installed_tool)

    # Built from the source once it is in place, so the root is the real one and
    # not the staging directory the fetch went through.
    assert captured['resource_root'] == classic_tool_root(tools_cache_directory)
    assert installed_tool.name == 'cppfront'
    assert installed_tool.resolved_version == 'v0.8.1'

    source = manager.cache_manager.read_manifest_source(cached_tool.path)

    assert source.type == 'git'
    assert source.reference == 'v0.8.1'
    # The remote is recorded under the unified `location` key.
    assert source.location == tool_registry.TOOLS['cppfront'].repository
    assert not (tools_cache_directory / cache_configuration.TOOLS_SUBDIR / 'cppfront.tmp').exists()


def test_get_tool_returns_the_tool_asked_for(tmp_path):
    manager = make_tool_manager(tmp_path)

    assert manager.get_tool('cppfront').version == \
        tool_registry.TOOLS['cppfront'].default_version
    assert manager.get_tool('cppfront', version='v0.8.0').version == 'v0.8.0'
    with pytest.raises(ValueError, match='unsupported tool'):
        manager.get_tool('nope')


def test_locating_a_tool_asks_no_remote(monkeypatch, tmp_path):
    # configure's cppfront autodiscovery and `golem tools uninstall` both go
    # through this: a tool is keyed by its name, so finding one needs no version.
    monkeypatch.setattr(
        tool.VersionResolver, 'resolve',
        staticmethod(lambda *args, **kwargs: pytest.fail('resolved a version to locate a tool')))

    manager = make_tool_manager(tmp_path, tools_cache_directory=str(tmp_path / 'tools-cache'))

    assert manager.resolve_cached_resource(
        manager.get_tool('cppfront'), with_version_resolution=False).path == \
        classic_tool_root(tmp_path / 'tools-cache')


def test_removing_a_tool_deletes_the_resolved_tool_resource(tmp_path):
    tools_cache_directory = tmp_path / 'tools-cache'
    resource_root = tools_cache_directory / cache_configuration.TOOLS_SUBDIR / 'cppfront'
    resource_root.mkdir(parents=True)
    (resource_root / 'manifest.json').write_text('{}\n', encoding='utf-8')

    manager = make_tool_manager(tmp_path, tools_cache_directory=str(tools_cache_directory))
    cached_tool = manager.resolve_cached_resource(
        manager.get_tool('cppfront'), with_version_resolution=False)

    assert cached_tool.path == str(resource_root)
    assert cached_tool.exists() is True
    removed, _ = manager.cache_manager.remove_resources([cached_tool])
    assert removed == [cached_tool]
    assert not resource_root.exists()


def test_removing_a_tool_that_is_not_there_deletes_nothing(tmp_path):
    tools_cache_directory = tmp_path / 'tools-cache'

    manager = make_tool_manager(tmp_path, tools_cache_directory=str(tools_cache_directory))
    cached_tool = manager.resolve_cached_resource(
        manager.get_tool('cppfront'), with_version_resolution=False)

    assert cached_tool.exists() is False
    assert manager.cache_manager.remove_resources([cached_tool]) == ([], [])


def test_list_installed_tools_returns_registry_installed_tools(monkeypatch, tmp_path):
    tools_cache_directory = tmp_path / 'tools-cache'
    resource_root = tools_cache_directory / cache_configuration.TOOLS_SUBDIR / 'cppfront'
    resource_root.mkdir(parents=True)
    write_tool_manifest(resource_root)

    installed_tools = make_tool_manager(tmp_path, tools_cache_directory=str(tools_cache_directory)).list_installed_tools()

    assert len(installed_tools) == 1
    assert installed_tools[0].name == 'cppfront'
    assert installed_tools[0].version == 'v0.8.1'


def test_install_tool_uses_minimized_flat_layout_when_enabled(monkeypatch, tmp_path):
    tools_cache_directory = tmp_path / 'tools-cache'
    captured = {}

    def fake_build(resource_root):
        captured['resource_root'] = resource_root
        return None

    replace_cppfront_tool(monkeypatch, build_handler=fake_build)

    manager = make_tool_manager(
        tmp_path, tools_cache_directory=str(tools_cache_directory),
        minimization_enabled=True)

    expected_name = manager.cache_manager.make_minimized_resource_name(
        manager.resource_for(manager.get_tool('cppfront')),
        default_setting('GOLEM_CACHE_MINIMIZATION_LENGTH'))
    expected_root = tools_cache_directory / expected_name

    cached_tool = manager.install(manager.get_tool('cppfront'))

    # Flat under the cache root, no tools/ subdir, short hashed name.
    assert cached_tool.path == str(expected_root)
    assert captured['resource_root'] == str(expected_root)
    assert cache_configuration.TOOLS_SUBDIR not in os.path.relpath(
        cached_tool.path, str(tools_cache_directory))

    # The manifest records the real cache_key, so the scanner and
    # `golem cache list` identify it wherever it is stored.
    manifest = resource_manifest.ResourceManifest.read_from_root(str(expected_root))
    assert manifest.cache_key == 'cppfront'
    assert manifest.kind == resource_manifest.ResourceKind.TOOL.value


def test_install_tool_prefers_existing_classic_tool_layout(monkeypatch, tmp_path):
    tools_cache_directory = tmp_path / 'tools-cache'
    # A tool already installed under the classic layout keeps its location even
    # when minimization is enabled.
    classic_root = tools_cache_directory / cache_configuration.TOOLS_SUBDIR / 'cppfront'
    classic_root.mkdir(parents=True)

    manager = make_tool_manager(
        tmp_path, tools_cache_directory=str(tools_cache_directory),
        minimization_enabled=True)

    assert manager.resolve_cached_resource(
        manager.get_tool('cppfront'), with_version_resolution=False).path == str(classic_root)


def test_list_installed_tools_scans_additional_cache(tmp_path):
    # A tool living in an additional cache (not the primary) is still listed,
    # mirroring how `golem cache list` scans every configured location.
    primary = tmp_path / 'primary-cache'
    additional = tmp_path / 'additional-cache'
    resource_root = additional / cache_configuration.TOOLS_SUBDIR / 'cppfront'
    resource_root.mkdir(parents=True)
    write_tool_manifest(resource_root)

    manager = make_tool_manager(tmp_path, locations=[
        cache_directory.CacheDirectory(location=str(primary)),
        cache_directory.CacheDirectory(location=str(additional)),
    ])

    installed_tools = manager.list_installed_tools()

    assert len(installed_tools) == 1
    assert installed_tools[0].name == 'cppfront'
    assert installed_tools[0].cache_root == str(additional)
    assert installed_tools[0].is_read_only is False


def test_removing_a_tool_finds_it_in_an_additional_cache_under_weak_policy(tmp_path):
    primary = tmp_path / 'primary-cache'
    additional = tmp_path / 'additional-cache'
    resource_root = additional / cache_configuration.TOOLS_SUBDIR / 'cppfront'
    resource_root.mkdir(parents=True)
    write_tool_manifest(resource_root)

    manager = make_tool_manager(
        tmp_path,
        resolution_policy=cache_resolution_policy.CacheResolutionPolicy.WEAK,
        locations=[
            cache_directory.CacheDirectory(location=str(primary)),
            cache_directory.CacheDirectory(location=str(additional)),
        ])

    cached_tool = manager.resolve_cached_resource(
        manager.get_tool('cppfront'), with_version_resolution=False)

    assert cached_tool.cache_root == str(additional)
    removed, _ = manager.cache_manager.remove_resources([cached_tool])
    assert removed == [cached_tool]
    assert not resource_root.exists()


def test_install_tool_fetches_through_the_shared_mechanism(monkeypatch, tmp_path, git_calls):
    tools_cache_directory = tmp_path / 'tools-cache'
    replace_cppfront_tool(monkeypatch, build_handler=lambda resource_root: None)

    manager = make_tool_manager(tmp_path, tools_cache_directory=str(tools_cache_directory))
    manager.install(manager.get_tool('cppfront', version='v0.8.1'))

    # The tool clones through the same policy-driven sequence as every other kind,
    # landing on the resolved commit under the tag it asked for.
    assert git_calls == [
        ['clone', '--', tool_registry.TOOLS['cppfront'].repository, '.'],
        ['checkout', 'v0.8.1'],
        ['reset', '--hard', 'deadbeef'],
    ]
    assert (tools_cache_directory / cache_configuration.TOOLS_SUBDIR / 'cppfront'
            / cache_configuration.SOURCE_DIRNAME).is_dir()


def run_install(monkeypatch, tmp_path, version, build_handler):
    replace_cppfront_tool(monkeypatch, build_handler=build_handler)
    manager = make_tool_manager(
        tmp_path, tools_cache_directory=str(tmp_path / 'tools-cache'))
    return manager.install(manager.get_tool('cppfront', version=version))


def test_reinstalling_at_another_version_refreshes_and_rebuilds(monkeypatch, tmp_path, git_calls):
    def build(resource_root):
        os.makedirs(os.path.join(resource_root, 'bin'), exist_ok=True)
        with open(os.path.join(resource_root, 'bin', 'cppfront'), 'w') as fileout:
            fileout.write('v0.8.1')

    root = run_install(monkeypatch, tmp_path, 'v0.8.1', build).path
    git_calls.clear()

    def rebuild(resource_root):
        # The previous binary is gone before anything is built from the new source.
        assert not os.path.exists(os.path.join(resource_root, 'bin'))
        build(resource_root)

    cached_tool = run_install(monkeypatch, tmp_path, 'v0.8.2', rebuild)

    assert cached_tool.path == root
    # Refreshed in place, not re-cloned.
    assert git_calls == [
        ['clean', '-ffxd'],
        ['fetch', 'origin'],
        ['reset', '--hard', 'deadbeef'],
    ]
    assert os.path.isfile(os.path.join(root, 'bin', 'cppfront'))
    # And the root stops claiming the version it used to hold.
    assert resource_manifest.ResourceManifest.read_from_root(
        root).source['reference'] == 'v0.8.2'


def test_a_failed_build_leaves_nothing_built_from_the_old_version(monkeypatch, tmp_path):
    def build(resource_root):
        os.makedirs(os.path.join(resource_root, 'bin'), exist_ok=True)
        with open(os.path.join(resource_root, 'bin', 'cppfront'), 'w') as fileout:
            fileout.write('v0.8.1')

    root = run_install(monkeypatch, tmp_path, 'v0.8.1', build).path

    def failing_build(resource_root):
        raise RuntimeError('compiler exploded')

    with pytest.raises(RuntimeError, match='compiler exploded'):
        run_install(monkeypatch, tmp_path, 'v0.8.2', failing_build)

    # Fetched and correctly named but not built, which is what is_valid() detects
    # -- never a binary from one version beside a source and manifest naming another.
    assert not os.path.exists(os.path.join(root, 'bin'))
    assert resource_manifest.ResourceManifest.read_from_root(
        root).source['reference'] == 'v0.8.2'


def test_installing_a_tool_into_a_read_only_cache_is_refused(tmp_path):
    # A read-only cache is preferred by the resolver (like every other resource);
    # creating a tool in it is refused rather than silently writing elsewhere.
    read_only = tmp_path / 'read-only-cache'
    writable = tmp_path / 'writable-cache'

    manager = make_tool_manager(tmp_path, locations=[
        cache_directory.CacheDirectory(location=str(writable)),
        cache_directory.CacheDirectory(location=str(read_only), is_read_only=True),
    ])

    with pytest.raises(RuntimeError, match='read-only'):
        manager.install(manager.get_tool('cppfront'))