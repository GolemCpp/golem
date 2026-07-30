import os

from golemcpp.golem import cache_configuration
from golemcpp.golem import settings
from golemcpp.golem import helpers
from golemcpp.golem import command_tools
from golemcpp.golem import cppfront_tool
from golemcpp.golem import tool_manager


def expected_tools_cache(project_dir):
    return helpers.make_absolute_path('/tmp/custom-cache', str(project_dir))


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
    assert '    Repository: {}'.format(cppfront_tool.CPPFRONT_REPOSITORY) in stdout
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
        captured['location'] = self.locations[0].location
        return tool_manager.ToolInstallResult(
            name=tool_name,
            version=cppfront_tool.DEFAULT_CPPFRONT_VERSION,
            resource_root='/tmp/golem-tools-cache/cppfront',
            cache_root=self.locations[0].location,
        )

    monkeypatch.setattr(tool_manager.ToolManager, 'install_tool', fake_install_tool)

    result = command_tools.handle_tools_command(
        project_dir=str(project_dir),
        args=['install', 'cppfront'],
    )

    assert result == 0
    assert captured['tool_name'] == 'cppfront'
    assert captured['version'] == ''
    assert captured['location']

    stdout = capsys.readouterr().out
    assert 'Installed cppfront {}'.format(cppfront_tool.DEFAULT_CPPFRONT_VERSION) in stdout
    assert 'Selected cache location: {}'.format(captured['location']) in stdout


def test_handle_tools_command_accepts_explicit_version(monkeypatch, tmp_path):
    project_dir = tmp_path / 'demo-project'
    project_dir.mkdir()

    captured = {}

    def fake_install_tool(self, tool_name, version):
        captured['version'] = version
        return tool_manager.ToolInstallResult(
            name=tool_name,
            version=version,
            resource_root='/tmp/golem-tools-cache/cppfront',
            cache_root=self.locations[0].location,
        )

    monkeypatch.setattr(tool_manager.ToolManager, 'install_tool', fake_install_tool)

    result = command_tools.handle_tools_command(
        project_dir=str(project_dir),
        args=['install', 'cppfront', '--version=v0.8.0'],
    )

    assert result == 0
    assert captured['version'] == 'v0.8.0'


def test_handle_tools_command_accepts_explicit_cache_directory(monkeypatch, tmp_path):
    project_dir = tmp_path / 'demo-project'
    project_dir.mkdir()

    captured = {}

    def fake_install_tool(self, tool_name, version):
        captured['location'] = self.locations[0].location
        return tool_manager.ToolInstallResult(
            name=tool_name,
            version=version,
            resource_root=self.locations[0].location + '/cppfront',
            cache_root=self.locations[0].location,
        )

    monkeypatch.setattr(tool_manager.ToolManager, 'install_tool', fake_install_tool)

    result = command_tools.handle_tools_command(
        project_dir=str(project_dir),
        args=['install', 'cppfront', '--cache-directory=/tmp/custom-cache'],
    )

    assert result == 0
    assert captured['location'] == expected_tools_cache(project_dir)


def test_handle_tools_command_honors_persisted_configure_options(monkeypatch, tmp_path):
    # Like `golem cache`, `golem tools` resolves the cache the project was
    # configured with (persisted `golem configure` options), reached via
    # --build-dir, without the user re-passing --cache-directory.
    monkeypatch.delenv('GOLEM_CACHE_DIRECTORY', raising=False)

    project_dir = tmp_path / 'demo-project'
    project_dir.mkdir()
    build_dir = tmp_path / 'build'
    configured_cache = tmp_path / 'configured-cache'

    monkeypatch.setattr(
        settings, 'get_persisted_configure_options',
        lambda build_dir: {'cache_directory': str(configured_cache)})

    captured = {}

    def fake_install_tool(self, tool_name, version):
        captured['location'] = self.locations[0].location
        return tool_manager.ToolInstallResult(
            name=tool_name, version=version,
            resource_root=self.locations[0].location + '/cppfront',
            cache_root=self.locations[0].location)

    monkeypatch.setattr(tool_manager.ToolManager, 'install_tool', fake_install_tool)

    result = command_tools.handle_tools_command(
        project_dir=str(project_dir),
        args=['install', 'cppfront', '--build-dir', str(build_dir)],
    )

    assert result == 0
    assert captured['location'] == str(configured_cache)


def install_fake_tool_on_disk(cache_dir, tool_name='cppfront'):
    tool_root = cache_dir / cache_configuration.TOOLS_SUBDIR / tool_name
    tool_root.mkdir(parents=True)
    return tool_root


def test_handle_tools_command_uninstalls_cppfront(capsys, tmp_path):
    project_dir = tmp_path / 'demo-project'
    project_dir.mkdir()
    cache_dir = tmp_path / 'cache'
    tool_root = install_fake_tool_on_disk(cache_dir)

    result = command_tools.handle_tools_command(
        project_dir=str(project_dir),
        args=['uninstall', 'cppfront', '--cache-directory=' + str(cache_dir), '--yes'],
    )

    assert result == 0
    assert not tool_root.exists()

    stdout = capsys.readouterr().out
    assert 'Uninstalled cppfront from {}'.format(str(cache_dir)) in stdout


def test_handle_tools_command_uninstall_prompts_for_confirmation(capsys, tmp_path):
    # Without --yes, and with no interactive stdin, uninstall is aborted and the
    # tool stays on disk.
    project_dir = tmp_path / 'demo-project'
    project_dir.mkdir()
    cache_dir = tmp_path / 'cache'
    tool_root = install_fake_tool_on_disk(cache_dir)

    result = command_tools.handle_tools_command(
        project_dir=str(project_dir),
        args=['uninstall', 'cppfront', '--cache-directory=' + str(cache_dir)],
    )

    assert result == 0
    assert tool_root.exists()

    stdout = capsys.readouterr().out
    assert 'Aborted. Nothing was uninstalled.' in stdout


def test_handle_tools_command_refuses_to_uninstall_from_a_read_only_cache(
        capsys, monkeypatch, tmp_path):
    project_dir = tmp_path / 'demo-project'
    project_dir.mkdir()
    writable_cache = tmp_path / 'cache'
    read_only_cache = tmp_path / 'read-only-cache'
    tool_root = install_fake_tool_on_disk(read_only_cache)
    monkeypatch.setenv(
        'GOLEM_ADDITIONAL_READ_ONLY_CACHE_DIRECTORIES', str(read_only_cache))

    result = command_tools.handle_tools_command(
        project_dir=str(project_dir),
        args=['uninstall', 'cppfront', '--cache-directory=' + str(writable_cache), '--yes'],
    )

    assert result == 0
    assert tool_root.exists()

    stdout = capsys.readouterr().out
    assert 'cppfront is in the read-only cache location {} and was not removed'.format(
        str(read_only_cache)) in stdout


def test_handle_tools_command_reports_when_tool_is_not_installed(capsys, tmp_path):
    project_dir = tmp_path / 'demo-project'
    project_dir.mkdir()
    cache_dir = tmp_path / 'cache'
    cache_dir.mkdir()

    result = command_tools.handle_tools_command(
        project_dir=str(project_dir),
        args=['uninstall', 'cppfront', '--cache-directory=' + str(cache_dir), '--yes'],
    )

    assert result == 0

    stdout = capsys.readouterr().out
    assert 'cppfront is not installed in {}'.format(str(cache_dir)) in stdout


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
    assert '  Repository: {}'.format(cppfront_tool.CPPFRONT_REPOSITORY) in stdout
    assert '  Default version: {}'.format(cppfront_tool.DEFAULT_CPPFRONT_VERSION) in stdout


def test_handle_tools_command_lists_installed_tools(monkeypatch, capsys, tmp_path):
    project_dir = tmp_path / 'demo-project'
    project_dir.mkdir()

    monkeypatch.setattr(tool_manager.ToolManager, 'list_installed_tools', lambda self: [
        tool_manager.InstalledToolInfo(
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

    monkeypatch.setattr(tool_manager.ToolManager, 'list_installed_tools', lambda self: [])

    result = command_tools.handle_tools_command(
        project_dir=str(project_dir),
        args=['list'],
    )

    assert result == 0

    stdout = capsys.readouterr().out
    assert 'No installed tools found.' in stdout


def test_cache_minimization_enabled_optional_value_states(monkeypatch):
    monkeypatch.delenv('GOLEM_CACHE_MINIMIZATION_ENABLED', raising=False)

    def resolve(args):
        options = command_tools.parse_tools_args(args)
        return settings.get_settings(options=options).get(
            'GOLEM_CACHE_MINIMIZATION_ENABLED')

    # Absent -> automatic default (on).
    assert resolve(['list']) is True
    # Bare flag -> forced on.
    assert resolve(['list', '--cache-minimization-enabled']) is True
    # Explicit values.
    assert resolve(['list', '--cache-minimization-enabled=on']) is True
    assert resolve(['list', '--cache-minimization-enabled=off']) is False

    # Bare flag forces on even when the environment would disable it, because an
    # explicit option wins over env/config.
    monkeypatch.setenv('GOLEM_CACHE_MINIMIZATION_ENABLED', 'off')
    assert resolve(['list']) is False
    assert resolve(['list', '--cache-minimization-enabled']) is True
