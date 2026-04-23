from golemcpp.golem.cli_arguments import make_absolute_path, normalize_argv, resolve_cli_arguments


def test_make_absolute_path_returns_absolute_input_unchanged():
    assert make_absolute_path('/tmp/project', '/workspace') == '/tmp/project'


def test_make_absolute_path_joins_relative_path_with_cwd():
    assert make_absolute_path('build-debug', '/workspace/project') == '/workspace/project/build-debug'


def test_resolve_cli_arguments_uses_defaults_when_no_command_is_provided():
    command, project_dir, build_dir, command_args = resolve_cli_arguments(['golem'], '/workspace/project')

    assert command is None
    assert project_dir == '/workspace/project'
    assert build_dir == '/workspace/project/build'
    assert command_args == []


def test_resolve_cli_arguments_extracts_command_and_relative_directories():
    command, project_dir, build_dir, command_args = resolve_cli_arguments(
        ['golem', '--project-dir=demo', 'configure', '--clangd'],
        '/workspace/project',
    )

    assert command == 'configure'
    assert project_dir == '/workspace/project/demo'
    assert build_dir == '/workspace/project/build'
    assert command_args == ['--clangd']


def test_resolve_cli_arguments_supports_deprecated_dir_option():
    command, project_dir, build_dir, command_args = resolve_cli_arguments(
        ['golem', 'configure', '--dir=out'],
        '/workspace/project',
    )

    assert command == 'configure'
    assert project_dir == '/workspace/project'
    assert build_dir == '/workspace/project/out'
    assert command_args == ['--dir=out']


def test_resolve_cli_arguments_prefers_build_dir_over_deprecated_dir_option():
    command, project_dir, build_dir, command_args = resolve_cli_arguments(
        ['golem', '--dir=legacy-build', 'configure', '--build-dir=modern-build', '--variant=debug'],
        '/workspace/project',
    )

    assert command == 'configure'
    assert project_dir == '/workspace/project'
    assert build_dir == '/workspace/project/modern-build'
    assert command_args == ['--build-dir=modern-build', '--variant=debug']


def test_normalize_argv_converts_deprecated_dir_option():
    assert normalize_argv(['golem', 'configure', '--dir=out']) == [
        'golem',
        'configure',
        '--build-dir=out',
    ]


def test_normalize_argv_keeps_explicit_build_dir_and_drops_deprecated_dir_option():
    assert normalize_argv(['golem', '--dir=legacy', 'configure', '--build-dir=current']) == [
        'golem',
        'configure',
        '--build-dir=current',
    ]