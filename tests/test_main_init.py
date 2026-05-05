from pathlib import Path

from golemcpp.golem import main


def test_main_without_command_prints_command_recap(tmp_path, monkeypatch, capsys):
    project_dir = tmp_path / 'demo-project'
    project_dir.mkdir()

    monkeypatch.chdir(project_dir)
    monkeypatch.setattr(main.sys, 'argv', ['golem'])

    def fail_if_called(*args, **kwargs):
        raise AssertionError('Waf entry point should not run without a command')

    monkeypatch.setattr(main.Scripting, 'waf_entry_point', fail_if_called)

    result = main.main()

    assert result == 0

    stdout = capsys.readouterr().out
    assert '=== Golem C++ Build System ===' in stdout
    assert 'Run `golem <command>` from your project root.' in stdout
    assert 'Useful commands:' in stdout
    assert 'init' in stdout
    assert 'configure' in stdout
    assert 'resolve' in stdout
    assert 'dependencies' in stdout
    assert 'build' in stdout
    assert 'package' in stdout
    assert 'clean' in stdout
    assert 'distclean' in stdout
    assert 'Documentation: https://golemcpp.org/docs/' in stdout


def test_main_init_creates_golemfile_from_template(tmp_path, monkeypatch, capsys):
    project_dir = tmp_path / 'demo-project'
    project_dir.mkdir()

    monkeypatch.chdir(project_dir)
    monkeypatch.setattr(main.sys, 'argv', ['golem', 'init'])

    result = main.main()

    created_file = project_dir / 'golemfile.py'
    template_path = Path(main.helpers.get_golemcpp_data_dir()) / 'golemfile.py.template'

    assert result == 0
    assert created_file.exists()
    assert created_file.read_text(encoding='utf-8') == template_path.read_text(encoding='utf-8')

    stdout = capsys.readouterr().out
    assert 'Created' in stdout
    assert 'golem configure --variant=debug' in stdout


def test_main_init_returns_error_when_project_file_exists(tmp_path, monkeypatch, capsys):
    project_dir = tmp_path / 'demo-project'
    project_dir.mkdir()
    existing_file = project_dir / 'golemfile.py'
    existing_file.write_text('# existing\n', encoding='utf-8')

    monkeypatch.chdir(project_dir)
    monkeypatch.setattr(main.sys, 'argv', ['golem', 'init'])

    result = main.main()

    assert result == 1
    assert existing_file.read_text(encoding='utf-8') == '# existing\n'

    stdout = capsys.readouterr().out
    assert 'already exists' in stdout
    assert '--force' in stdout


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
    assert '--project-dir=' + str(project_dir) in captured['argv']
    assert '--build-dir=' + str(project_dir / 'build') in captured['argv']