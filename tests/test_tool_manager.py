import os
from dataclasses import replace

import pytest

from golemcpp.golem import cache_configuration
from golemcpp.golem import cache_directory
from golemcpp.golem import cache_resolution_policy
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
        tool_manager.VersionResolver, 'resolve',
        staticmethod(lambda url, version, version_regex='': (version, 'deadbeef')))


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

    def fake_install(version, install_root):
        captured['version'] = version
        captured['install_root'] = install_root
        assert install_root == classic_tool_root(tools_cache_directory) + '.tmp'
        return None

    replace_cppfront_tool(
        monkeypatch,
        install_handler=fake_install,
    )

    result = make_tool_manager(tmp_path, tools_cache_directory=str(tools_cache_directory)).install_tool(
        tool_name='cppfront',
        version='',
    )

    assert captured['version'] == tool_registry.TOOLS['cppfront'].default_version
    assert captured['install_root'] == classic_tool_root(tools_cache_directory) + '.tmp'
    assert result.name == 'cppfront'
    assert result.version == 'v0.8.1'

    source = make_tool_manager(tmp_path, tools_cache_directory=str(tools_cache_directory)).read_tool_source(
        tool_name='cppfront',
    )

    assert source.type == 'git'
    assert source.reference == 'v0.8.1'
    # The remote is recorded under the unified `location` key.
    assert source.location == tool_registry.TOOLS['cppfront'].repository
    assert not (tools_cache_directory / cache_configuration.TOOLS_SUBDIR / 'cppfront.tmp').exists()


def test_uninstall_tool_removes_the_resolved_tool_resource(tmp_path):
    tools_cache_directory = tmp_path / 'tools-cache'
    resource_root = tools_cache_directory / cache_configuration.TOOLS_SUBDIR / 'cppfront'
    resource_root.mkdir(parents=True)
    (resource_root / 'manifest.json').write_text('{}\n', encoding='utf-8')

    manager = make_tool_manager(tmp_path, tools_cache_directory=str(tools_cache_directory))
    cached_tool = manager.resolve_cached_tool('cppfront')

    assert cached_tool.path == str(resource_root)
    assert cached_tool.exists() is True
    assert manager.uninstall_tool(cached_tool) is True
    assert not resource_root.exists()


def test_uninstall_tool_reports_missing_tool_directory(tmp_path):
    tools_cache_directory = tmp_path / 'tools-cache'

    manager = make_tool_manager(tmp_path, tools_cache_directory=str(tools_cache_directory))
    cached_tool = manager.resolve_cached_tool('cppfront')

    assert cached_tool.exists() is False
    assert manager.uninstall_tool(cached_tool) is False


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

    def fake_install(version, install_root):
        captured['install_root'] = install_root
        return None

    replace_cppfront_tool(monkeypatch, install_handler=fake_install)

    manager = make_tool_manager(
        tmp_path, tools_cache_directory=str(tools_cache_directory),
        minimization_enabled=True)

    expected_name = manager.cache_manager.make_minimized_resource_name(
        manager.resource_for(manager.get_tool('cppfront')),
        default_setting('GOLEM_CACHE_MINIMIZATION_LENGTH'))
    expected_root = tools_cache_directory / expected_name

    result = manager.install_tool(tool_name='cppfront', version='')

    # Flat under the cache root, no tools/ subdir, short hashed name.
    assert result.resource_root == str(expected_root)
    assert captured['install_root'] == str(expected_root) + '.tmp'
    assert cache_configuration.TOOLS_SUBDIR not in os.path.relpath(
        result.resource_root, str(tools_cache_directory))

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

    assert manager.resolve_cached_tool('cppfront').path == str(classic_root)


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


def test_uninstall_tool_finds_tool_in_additional_cache_under_weak_policy(tmp_path):
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

    cached_tool = manager.resolve_cached_tool('cppfront')

    assert cached_tool.cache_root == str(additional)
    assert manager.uninstall_tool(cached_tool) is True
    assert not resource_root.exists()


def test_install_tool_refuses_read_only_cache(tmp_path):
    # A read-only cache is preferred by the resolver (like every other resource);
    # installing into it is refused rather than silently writing elsewhere.
    read_only = tmp_path / 'read-only-cache'
    writable = tmp_path / 'writable-cache'

    manager = make_tool_manager(tmp_path, locations=[
        cache_directory.CacheDirectory(location=str(writable)),
        cache_directory.CacheDirectory(location=str(read_only), is_read_only=True),
    ])

    try:
        manager.install_tool(tool_name='cppfront', version='')
        assert False, 'expected install into read-only cache to be refused'
    except RuntimeError as error:
        assert 'read-only' in str(error)