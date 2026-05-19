from golemcpp.golem import command_tools
from golemcpp.golem import cppfront_tool
from golemcpp.golem import tools_manager


def test_handle_tools_command_prints_help(capsys, tmp_path):
    project_dir = tmp_path / 'demo-project'
    project_dir.mkdir()

    result = command_tools.handle_tools_command(
        project_dir=str(project_dir),
        args=['--help'],
    )

    assert result == 0

    stdout = capsys.readouterr().out
    assert 'Usage: golem tools install <tool>' in stdout
    assert 'golem tools uninstall <tool>' in stdout
    assert 'golem tools list [--available]' in stdout
    assert '  cppfront\n    Description:' in stdout
    assert '    Repository: {}'.format(cppfront_tool.CPPFRONT_REPOSITORY_URL) in stdout
    assert '    Default version: {}'.format(cppfront_tool.DEFAULT_CPPFRONT_VERSION) in stdout


def test_handle_tools_command_rejects_unknown_subcommand(capsys, tmp_path):
    project_dir = tmp_path / 'demo-project'
    project_dir.mkdir()

    result = command_tools.handle_tools_command(
        project_dir=str(project_dir),
        args=['remove', 'cppfront'],
    )

    assert result == 1

    stdout = capsys.readouterr().out
    assert 'unsupported tools command' in stdout


def test_handle_tools_command_rejects_unknown_tool(capsys, tmp_path):
    project_dir = tmp_path / 'demo-project'
    project_dir.mkdir()

    result = command_tools.handle_tools_command(
        project_dir=str(project_dir),
        args=['install', 'unknown-tool'],
    )

    assert result == 1

    stdout = capsys.readouterr().out
    assert 'unsupported tool: unknown-tool' in stdout


def test_handle_tools_command_installs_cppfront_with_default_version(monkeypatch, capsys, tmp_path):
    project_dir = tmp_path / 'demo-project'
    project_dir.mkdir()

    captured = {}

    def fake_install_tool(self, tool_name, version):
        captured['tool_name'] = tool_name
        captured['version'] = version
        captured['cache_directory'] = self.cache_directory
        return tools_manager.ToolInstallResult(
            name=tool_name,
            version=cppfront_tool.DEFAULT_CPPFRONT_VERSION,
            cache_root='/tmp/golem-tools-cache/cppfront',
        )

    monkeypatch.setattr(tools_manager.ToolsManager, 'install_tool', fake_install_tool)

    result = command_tools.handle_tools_command(
        project_dir=str(project_dir),
        args=['install', 'cppfront'],
    )

    assert result == 0
    assert captured['tool_name'] == 'cppfront'
    assert captured['version'] == ''
    assert captured['cache_directory']

    stdout = capsys.readouterr().out
    assert 'Installed cppfront {}'.format(cppfront_tool.DEFAULT_CPPFRONT_VERSION) in stdout
    assert 'Selected tools cache directory: {}'.format(captured['cache_directory']) in stdout


def test_handle_tools_command_accepts_explicit_version(monkeypatch, tmp_path):
    project_dir = tmp_path / 'demo-project'
    project_dir.mkdir()

    captured = {}

    def fake_install_tool(self, tool_name, version):
        captured['version'] = version
        return tools_manager.ToolInstallResult(
            name=tool_name,
            version=version,
            cache_root='/tmp/golem-tools-cache/cppfront',
        )

    monkeypatch.setattr(tools_manager.ToolsManager, 'install_tool', fake_install_tool)

    result = command_tools.handle_tools_command(
        project_dir=str(project_dir),
        args=['install', 'cppfront', '--version=v0.8.0'],
    )

    assert result == 0
    assert captured['version'] == 'v0.8.0'


def test_handle_tools_command_accepts_explicit_tools_cache_directory(monkeypatch, tmp_path):
    project_dir = tmp_path / 'demo-project'
    project_dir.mkdir()

    captured = {}

    def fake_install_tool(self, tool_name, version):
        captured['cache_directory'] = self.cache_directory
        return tools_manager.ToolInstallResult(
            name=tool_name,
            version=version,
            cache_root=self.cache_directory + '/cppfront',
        )

    monkeypatch.setattr(tools_manager.ToolsManager, 'install_tool', fake_install_tool)

    result = command_tools.handle_tools_command(
        project_dir=str(project_dir),
        args=['install', 'cppfront', '--tools-cache-directory=/tmp/custom-tools-cache'],
    )

    assert result == 0
    assert captured['cache_directory'] == '/tmp/custom-tools-cache'


def test_handle_tools_command_uninstalls_cppfront(monkeypatch, capsys, tmp_path):
    project_dir = tmp_path / 'demo-project'
    project_dir.mkdir()

    captured = {}

    def fake_uninstall_tool(self, tool_name):
        captured['tool_name'] = tool_name
        captured['cache_directory'] = self.cache_directory
        return tools_manager.ToolUninstallResult(name=tool_name, removed=True)

    monkeypatch.setattr(tools_manager.ToolsManager, 'uninstall_tool', fake_uninstall_tool)

    result = command_tools.handle_tools_command(
        project_dir=str(project_dir),
        args=['uninstall', 'cppfront', '--tools-cache-directory=/tmp/custom-tools-cache'],
    )

    assert result == 0
    assert captured['tool_name'] == 'cppfront'
    assert captured['cache_directory'] == '/tmp/custom-tools-cache'

    stdout = capsys.readouterr().out
    assert 'Uninstalled cppfront from /tmp/custom-tools-cache' in stdout


def test_handle_tools_command_reports_when_tool_is_not_installed(monkeypatch, capsys, tmp_path):
    project_dir = tmp_path / 'demo-project'
    project_dir.mkdir()

    monkeypatch.setattr(tools_manager.ToolsManager, 'uninstall_tool', lambda self, tool_name: tools_manager.ToolUninstallResult(name=tool_name, removed=False))

    result = command_tools.handle_tools_command(
        project_dir=str(project_dir),
        args=['uninstall', 'cppfront', '--tools-cache-directory=/tmp/custom-tools-cache'],
    )

    assert result == 0

    stdout = capsys.readouterr().out
    assert 'cppfront is not installed in /tmp/custom-tools-cache' in stdout


def test_handle_tools_command_lists_available_tools(capsys, tmp_path):
    project_dir = tmp_path / 'demo-project'
    project_dir.mkdir()

    result = command_tools.handle_tools_command(
        project_dir=str(project_dir),
        args=['list', '--available'],
    )

    assert result == 0

    stdout = capsys.readouterr().out
    assert 'Supported installable tools:' in stdout
    assert 'cppfront\n  Description:' in stdout
    assert '  Repository: {}'.format(cppfront_tool.CPPFRONT_REPOSITORY_URL) in stdout
    assert '  Default version: {}'.format(cppfront_tool.DEFAULT_CPPFRONT_VERSION) in stdout


def test_handle_tools_command_lists_installed_tools(monkeypatch, capsys, tmp_path):
    project_dir = tmp_path / 'demo-project'
    project_dir.mkdir()

    monkeypatch.setattr(tools_manager.ToolsManager, 'list_installed_tools', lambda self: [
        tools_manager.InstalledToolInfo(
            name='cppfront',
            version='v0.8.1',
        )
    ])

    result = command_tools.handle_tools_command(
        project_dir=str(project_dir),
        args=['list'],
    )

    assert result == 0

    stdout = capsys.readouterr().out
    assert 'Installed tools:' in stdout
    assert 'cppfront v0.8.1' in stdout


def test_handle_tools_command_reports_no_installed_tools(monkeypatch, capsys, tmp_path):
    project_dir = tmp_path / 'demo-project'
    project_dir.mkdir()

    monkeypatch.setattr(tools_manager.ToolsManager, 'list_installed_tools', lambda self: [])

    result = command_tools.handle_tools_command(
        project_dir=str(project_dir),
        args=['list'],
    )

    assert result == 0

    stdout = capsys.readouterr().out
    assert 'No installed tools found.' in stdout
