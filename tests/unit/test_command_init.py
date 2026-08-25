from pathlib import Path

from golemcpp.golem import command_init


def write_template(data_dir: Path, content: str = '# generated\n') -> Path:
    data_dir.mkdir()
    template_path = data_dir / 'golemfile.py.template'
    template_path.write_text(content, encoding='utf-8')
    return template_path


def test_handle_init_command_creates_golemfile_from_template(tmp_path, capsys):
    project_dir = tmp_path / 'demo-project'
    project_dir.mkdir()
    data_dir = tmp_path / 'data'
    template_path = write_template(data_dir)

    result = command_init.handle_init_command(
        project_dir=str(project_dir),
        data_dir=data_dir,
        args=[
            '--project-dir=' + str(project_dir),
            '--build-dir=' + str(project_dir / 'build'),
        ],
    )

    created_file = project_dir / 'golemfile.py'

    assert result == 0
    assert created_file.exists()
    assert created_file.read_text(encoding='utf-8') == template_path.read_text(encoding='utf-8')

    stdout = capsys.readouterr().out
    assert 'Created' in stdout
    assert 'golem configure --variant=debug' in stdout


def test_handle_init_command_returns_error_when_project_file_exists(tmp_path, capsys):
    project_dir = tmp_path / 'demo-project'
    project_dir.mkdir()
    data_dir = tmp_path / 'data'
    write_template(data_dir)
    existing_file = project_dir / 'golemfile.py'
    existing_file.write_text('# existing\n', encoding='utf-8')

    result = command_init.handle_init_command(
        project_dir=str(project_dir),
        data_dir=data_dir,
        args=['--project-dir=' + str(project_dir)],
    )

    assert result == 1
    assert existing_file.read_text(encoding='utf-8') == '# existing\n'

    stdout = capsys.readouterr().out
    assert 'already exists' in stdout
    assert '--force' in stdout


def test_handle_init_command_prints_help(capsys, tmp_path):
    project_dir = tmp_path / 'demo-project'
    project_dir.mkdir()
    data_dir = tmp_path / 'data'
    write_template(data_dir)

    result = command_init.handle_init_command(
        project_dir=str(project_dir),
        data_dir=data_dir,
        args=['--help'],
    )

    assert result == 0

    stdout = capsys.readouterr().out
    assert 'Usage: golem init' in stdout
    assert 'Generate a commented golemfile.py' in stdout