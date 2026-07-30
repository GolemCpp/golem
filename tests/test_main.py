from pathlib import Path

from golemcpp.golem import main


def test_main_without_command_dispatches_to_command_help(tmp_path, monkeypatch, capsys):
    project_dir = tmp_path / 'demo-project'
    project_dir.mkdir()

    monkeypatch.chdir(project_dir)
    monkeypatch.setattr(main.sys, 'argv', ['golem'])

    called = {'help': False}

    def fake_handle_help_command():
        called['help'] = True
        print('help-called')

    def fail_if_called(*args, **kwargs):
        raise AssertionError('Waf entry point should not run without a command')

    monkeypatch.setattr(main.command_help, 'handle_help_command', fake_handle_help_command)
    monkeypatch.setattr(main.Scripting, 'waf_entry_point', fail_if_called)

    result = main.main()

    assert result == 0
    assert called['help'] is True

    stdout = capsys.readouterr().out
    assert '=== Golem C++ Build System ===' in stdout
    assert 'help-called' in stdout


def test_main_version_flag_dispatches_to_command_version(monkeypatch, capsys):
    monkeypatch.setattr(main.sys, 'argv', ['golem', '--version'])

    called = {'version': False}

    def fake_handle_version_command():
        called['version'] = True
        print('version-called')
        return True

    def fail_if_called(*args, **kwargs):
        raise AssertionError('Waf entry point should not run for --version')

    monkeypatch.setattr(main.command_version, 'handle_version_command', fake_handle_version_command)
    monkeypatch.setattr(main.Scripting, 'waf_entry_point', fail_if_called)

    result = main.main()

    assert result == 0
    assert called['version'] is True

    stdout = capsys.readouterr().out
    assert '=== Golem C++ Build System ===' in stdout
    assert 'version-called' in stdout


def test_main_init_dispatches_to_command_init(tmp_path, monkeypatch):
    project_dir = tmp_path / 'demo-project'
    project_dir.mkdir()

    monkeypatch.chdir(project_dir)
    monkeypatch.setattr(main.sys, 'argv', ['golem', 'init'])

    captured = {}

    def fake_handle_init_command(project_dir, data_dir, args):
        captured['project_dir'] = project_dir
        captured['data_dir'] = data_dir
        captured['args'] = list(args)
        return 7

    def fail_if_called(*args, **kwargs):
        raise AssertionError('Waf entry point should not run for init')

    monkeypatch.setattr(main.command_init, 'handle_init_command', fake_handle_init_command)
    monkeypatch.setattr(main.Scripting, 'waf_entry_point', fail_if_called)

    result = main.main()

    assert result == 7
    assert captured['project_dir'] == str(project_dir)
    assert captured['data_dir'] == Path(main.helpers.get_golemcpp_golem_dir()).parent.joinpath('data')
    assert captured['args'] == [
        '--project-dir=' + str(project_dir),
        '--build-dir=' + str(project_dir / 'build'),
    ]


def test_main_tools_dispatches_to_command_tools(tmp_path, monkeypatch):
    project_dir = tmp_path / 'demo-project'
    project_dir.mkdir()

    monkeypatch.chdir(project_dir)
    monkeypatch.setattr(main.sys, 'argv', ['golem', 'tools', 'install', 'cppfront'])

    captured = {}

    def fake_handle_tools_command(project_dir, args):
        captured['project_dir'] = project_dir
        captured['args'] = list(args)
        return 11

    def fail_if_called(*args, **kwargs):
        raise AssertionError('Waf entry point should not run for tools')

    monkeypatch.setattr(main.command_tools, 'handle_tools_command', fake_handle_tools_command)
    monkeypatch.setattr(main.Scripting, 'waf_entry_point', fail_if_called)

    result = main.main()

    assert result == 11
    assert captured['project_dir'] == str(project_dir)
    assert captured['args'] == [
        'install',
        'cppfront',
        '--project-dir=' + str(project_dir),
        '--build-dir=' + str(project_dir / 'build'),
    ]


def test_main_config_dispatches_to_command_config(tmp_path, monkeypatch):
    project_dir = tmp_path / 'demo-project'
    project_dir.mkdir()

    monkeypatch.chdir(project_dir)
    monkeypatch.setattr(main.sys, 'argv', ['golem', 'config', 'overlays.locations', '/opt/overrides'])

    captured = {}

    def fake_handle_config_command(project_dir, args):
        captured['project_dir'] = project_dir
        captured['args'] = list(args)
        return 13

    def fail_if_called(*args, **kwargs):
        raise AssertionError('Waf entry point should not run for config')

    monkeypatch.setattr(main.command_config, 'handle_config_command', fake_handle_config_command)
    monkeypatch.setattr(main.Scripting, 'waf_entry_point', fail_if_called)

    result = main.main()

    assert result == 13
    assert captured['project_dir'] == str(project_dir)
    assert captured['args'] == [
        'overlays.locations',
        '/opt/overrides',
        '--project-dir=' + str(project_dir),
        '--build-dir=' + str(project_dir / 'build'),
    ]


def test_main_sets_project_and_build_dir_before_calling_waf(tmp_path, monkeypatch):
    project_dir = tmp_path / 'demo-project'
    project_dir.mkdir()

    monkeypatch.chdir(project_dir)
    monkeypatch.setattr(main.sys, 'argv', ['golem', 'configure', '--clangd'])

    captured = {}

    def fake_waf_entry_point(build_dir, waf_version, wafdir):
        captured['build_dir'] = build_dir
        captured['argv'] = list(main.sys.argv)

    monkeypatch.setattr(main.Scripting, 'waf_entry_point', fake_waf_entry_point)

    result = main.main()

    assert result == 0
    assert captured['build_dir'] == str(project_dir / 'build' / 'golem')
    assert captured['argv'] == [
        'golem',
        'configure',
        '--clangd',
        '--project-dir=' + str(project_dir),
        '--build-dir=' + str(project_dir / 'build'),
    ]


def test_main_writes_wscript_with_repr_safe_builder_path(tmp_path, monkeypatch):
    project_dir = tmp_path / 'demo-project'
    project_dir.mkdir()

    fake_package_dir = tmp_path / 'golem 日本 path' / 'golem'
    fake_package_dir.mkdir(parents=True)
    (fake_package_dir / 'builder.py').write_text('# builder\n', encoding='utf-8')

    data_dir = fake_package_dir.parent / 'data'
    data_dir.mkdir()
    (data_dir / 'wscript').write_text(
        "builder = import_from_file('builder', $builder_path)\n",
        encoding='utf-8',
    )

    monkeypatch.chdir(project_dir)
    monkeypatch.setattr(main.sys, 'argv', ['golem', 'configure'])
    monkeypatch.setattr(main.helpers, 'get_golemcpp_golem_dir', lambda: str(fake_package_dir))

    captured = {}

    def fake_waf_entry_point(build_dir, waf_version, wafdir):
        captured['build_dir'] = build_dir

    monkeypatch.setattr(main.Scripting, 'waf_entry_point', fake_waf_entry_point)

    result = main.main()

    generated_wscript = (project_dir / 'build' / 'golem' / 'wscript').read_text(encoding='utf-8')

    assert result == 0
    assert captured['build_dir'] == str(project_dir / 'build' / 'golem')
    assert generated_wscript == "builder = import_from_file('builder', {})\n".format(
        repr(str(fake_package_dir / 'builder.py'))
    )
