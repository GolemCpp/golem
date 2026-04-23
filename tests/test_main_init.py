from pathlib import Path

from golemcpp.golem import main


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