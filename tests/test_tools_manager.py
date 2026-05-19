from dataclasses import replace

from golemcpp.golem import tools_manager
from golemcpp.golem import tools_registry


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


def make_tools_manager(tmp_path, *, tools_cache_directory=None):
    return tools_manager.ToolsManager(
        cache_directory=make_tools_cache_directory(tmp_path, tools_cache_directory=tools_cache_directory),
    )


def test_install_tool_dispatches_to_registry_tool(monkeypatch, tmp_path):
    captured = {}
    tools_cache_directory = tmp_path / 'tools-cache'

    def fake_install(version, install_root):
        captured['version'] = version
        captured['install_root'] = install_root
        assert install_root == str(tmp_path / 'tools-cache' / 'cppfront.tmp')
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
    assert captured['install_root'] == str(tools_cache_directory / 'cppfront.tmp')
    assert result.name == 'cppfront'
    assert result.version == 'v0.8.1'

    manifest = make_tools_manager(tmp_path, tools_cache_directory=str(tools_cache_directory)).read_tool_manifest(
        tool_name='cppfront',
    )

    assert manifest.tool == 'cppfront'
    assert manifest.version == 'v0.8.1'
    assert not (tools_cache_directory / 'cppfront.tmp').exists()


def test_uninstall_tool_removes_tool_named_cache_directory(tmp_path):
    tools_cache_directory = tmp_path / 'tools-cache'
    cache_root = tools_cache_directory / 'cppfront'
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
    cache_root = tools_cache_directory / 'cppfront'
    cache_root.mkdir(parents=True)
    (cache_root / 'manifest.json').write_text(
        '{"tool": "cppfront", "version": "v0.8.1"}\n',
        encoding='utf-8',
    )

    installed_tools = make_tools_manager(tmp_path, tools_cache_directory=str(tools_cache_directory)).list_installed_tools()

    assert len(installed_tools) == 1
    assert installed_tools[0].name == 'cppfront'
    assert installed_tools[0].version == 'v0.8.1'