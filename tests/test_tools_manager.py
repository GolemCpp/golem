import os
from dataclasses import replace

from golemcpp.golem import cache
from golemcpp.golem import cache_manifest
from golemcpp.golem import tools_manager
from golemcpp.golem import tools_registry


def write_tool_manifest(cache_root, *, name='cppfront', version='v0.8.1'):
    cache_manifest.ResourceManifest.create(
        kind=cache_manifest.ResourceKind.TOOL,
        cache_key=name,
        identity={'name': name, 'version': version},
    ).write_to_root(str(cache_root))


def replace_cppfront_tool(monkeypatch, **changes):
    monkeypatch.setitem(
        tools_registry.TOOLS,
        'cppfront',
        replace(tools_registry.TOOLS['cppfront'], **changes),
    )


def make_tools_cache_directory(tmp_path, *, tools_cache_directory=None):
    if tools_cache_directory is None:
        tools_cache_directory = str(tmp_path / 'tools-cache')

    return tools_cache_directory


def make_tools_manager(tmp_path, *, tools_cache_directory=None,
                       minimization_enabled=False, minimization_length=None):
    # Tools are resolved from the base cache root, exactly like every other
    # resource kind. Classic-layout tests keep minimization disabled for
    # deterministic <root>/tools/<name> paths; minimized-layout tests opt in.
    return tools_manager.ToolsManager(
        cache_directory=make_tools_cache_directory(tmp_path, tools_cache_directory=tools_cache_directory),
        minimization_enabled=minimization_enabled,
        minimization_length=minimization_length,
    )


def classic_tool_root(base_cache_directory, tool_name='cppfront'):
    return os.path.join(str(base_cache_directory), cache.TOOLS_SUBDIR, tool_name)


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

    result = make_tools_manager(tmp_path, tools_cache_directory=str(tools_cache_directory)).install_tool(
        tool_name='cppfront',
        version='',
    )

    assert captured['version'] == tools_registry.TOOLS['cppfront'].default_version
    assert captured['install_root'] == classic_tool_root(tools_cache_directory) + '.tmp'
    assert result.name == 'cppfront'
    assert result.version == 'v0.8.1'

    manifest = make_tools_manager(tmp_path, tools_cache_directory=str(tools_cache_directory)).read_tool_manifest(
        tool_name='cppfront',
    )

    assert manifest.tool == 'cppfront'
    assert manifest.version == 'v0.8.1'
    assert not (tools_cache_directory / cache.TOOLS_SUBDIR / 'cppfront.tmp').exists()


def test_uninstall_tool_removes_tool_named_cache_directory(tmp_path):
    tools_cache_directory = tmp_path / 'tools-cache'
    cache_root = tools_cache_directory / cache.TOOLS_SUBDIR / 'cppfront'
    cache_root.mkdir(parents=True)
    (cache_root / 'manifest.json').write_text('{}\n', encoding='utf-8')

    result = make_tools_manager(tmp_path, tools_cache_directory=str(tools_cache_directory)).uninstall_tool(
        tool_name='cppfront',
    )

    assert result.removed is True
    assert make_tools_manager(tmp_path, tools_cache_directory=str(tools_cache_directory)).tool_cache_root('cppfront') == str(cache_root)
    assert not cache_root.exists()


def test_uninstall_tool_reports_missing_tool_directory(tmp_path):
    tools_cache_directory = tmp_path / 'tools-cache'

    result = make_tools_manager(tmp_path, tools_cache_directory=str(tools_cache_directory)).uninstall_tool(
        tool_name='cppfront',
    )

    assert result.removed is False


def test_list_installed_tools_returns_registry_installed_tools(monkeypatch, tmp_path):
    tools_cache_directory = tmp_path / 'tools-cache'
    cache_root = tools_cache_directory / cache.TOOLS_SUBDIR / 'cppfront'
    cache_root.mkdir(parents=True)
    write_tool_manifest(cache_root)

    installed_tools = make_tools_manager(tmp_path, tools_cache_directory=str(tools_cache_directory)).list_installed_tools()

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

    manager = make_tools_manager(
        tmp_path, tools_cache_directory=str(tools_cache_directory),
        minimization_enabled=True)

    expected_name = cache.make_minimized_resource_name(
        cache.TOOLS_SUBDIR, 'cppfront', cache.DEFAULT_MINIMIZATION_LENGTH)
    expected_root = tools_cache_directory / expected_name

    result = manager.install_tool(tool_name='cppfront', version='')

    # Flat under the cache root, no tools/ subdir, short hashed name.
    assert result.cache_root == str(expected_root)
    assert captured['install_root'] == str(expected_root) + '.tmp'
    assert cache.TOOLS_SUBDIR not in os.path.relpath(
        result.cache_root, str(tools_cache_directory))

    # The manifest records the real cache_key, so the scanner and
    # `golem cache list` identify it wherever it is stored.
    manifest = cache_manifest.ResourceManifest.read_from_root(str(expected_root))
    assert manifest.cache_key == 'cppfront'
    assert manifest.kind == cache_manifest.ResourceKind.TOOL.value


def test_install_tool_prefers_existing_classic_tool_layout(monkeypatch, tmp_path):
    tools_cache_directory = tmp_path / 'tools-cache'
    # A tool already installed under the classic layout keeps its location even
    # when minimization is enabled.
    classic_root = tools_cache_directory / cache.TOOLS_SUBDIR / 'cppfront'
    classic_root.mkdir(parents=True)

    manager = make_tools_manager(
        tmp_path, tools_cache_directory=str(tools_cache_directory),
        minimization_enabled=True)

    assert manager.tool_cache_root('cppfront') == str(classic_root)