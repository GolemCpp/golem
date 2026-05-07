from golemcpp.golem.cli_arguments import (
    make_absolute_path,
    normalize_argv,
    parse_cli_arguments,
    parse_directories_from_arguments,
    parse_global_and_command_arguments,
)


def test_make_absolute_path_returns_absolute_input_unchanged():
    assert make_absolute_path('/tmp/project', '/workspace') == '/tmp/project'


def test_make_absolute_path_joins_relative_path_with_cwd():
    assert make_absolute_path('build-debug', '/workspace/project') == '/workspace/project/build-debug'


def test_parse_global_and_command_arguments_splits_global_flags_and_command_args():
    global_args, command, command_args = parse_global_and_command_arguments(
        ['golem', '--version', 'configure', '--clangd']
    )

    assert global_args == ['--version']
    assert command == 'configure'
    assert command_args == ['--clangd']


def test_parse_cli_arguments_uses_defaults_when_no_command_is_provided():
    global_args, command, command_args = parse_cli_arguments(['golem'], '/workspace/project')

    assert global_args == [
        '--project-dir=/workspace/project',
        '--build-dir=/workspace/project/build',
    ]
    assert command is None
    assert command_args == []


def test_parse_cli_arguments_extracts_command_and_relative_directories():
    global_args, command, command_args = parse_cli_arguments(
        ['golem', '--project-dir=demo', 'configure', '--clangd'],
        '/workspace/project',
    )

    assert global_args == []
    assert command == 'configure'
    assert command_args == [
        '--project-dir=/workspace/project/demo',
        '--clangd',
        '--build-dir=/workspace/project/build',
    ]


def test_parse_cli_arguments_supports_deprecated_dir_option():
    global_args, command, command_args = parse_cli_arguments(
        ['golem', 'configure', '--dir=out'],
        '/workspace/project',
    )

    assert global_args == []
    assert command == 'configure'
    assert command_args == [
        '--build-dir=/workspace/project/out',
        '--project-dir=/workspace/project',
    ]


def test_parse_cli_arguments_prefers_build_dir_over_deprecated_dir_option():
    global_args, command, command_args = parse_cli_arguments(
        ['golem', '--dir=legacy-build', 'configure', '--build-dir=modern-build', '--variant=debug'],
        '/workspace/project',
    )

    assert global_args == []
    assert command == 'configure'
    assert command_args == [
        '--build-dir=/workspace/project/modern-build',
        '--variant=debug',
        '--project-dir=/workspace/project',
    ]


def test_normalize_argv_converts_deprecated_dir_option():
    assert normalize_argv(['golem', 'configure', '--dir=out'], '/workspace/project') == [
        'golem',
        'configure',
        '--build-dir=/workspace/project/out',
    ]


def test_normalize_argv_keeps_explicit_build_dir_and_drops_deprecated_dir_option():
    assert normalize_argv(['golem', '--dir=legacy', 'configure', '--build-dir=current'], '/workspace/project') == [
        'golem',
        'configure',
        '--build-dir=/workspace/project/current',
    ]


def test_normalize_argv_adds_project_and_build_dir_when_missing():
    assert normalize_argv(
        ['golem', 'configure', '--clangd'],
        '/workspace/project',
        project_dir='/workspace/project',
        build_dir='/workspace/project/build',
    ) == [
        'golem',
        'configure',
        '--clangd',
        '--project-dir=/workspace/project',
        '--build-dir=/workspace/project/build',
    ]


def test_normalize_argv_preserves_explicit_project_and_build_dir():
    assert normalize_argv(
        ['golem', '--project-dir=demo', 'configure', '--build-dir=out'],
        '/workspace/project',
        project_dir='/workspace/project',
        build_dir='/workspace/project/build',
    ) == [
        'golem',
        'configure',
        '--project-dir=/workspace/project/demo',
        '--build-dir=/workspace/project/out',
    ]


def test_parse_directories_from_arguments_extracts_explicit_dirs():
    project_dir, build_dir = parse_directories_from_arguments(
        ['--project-dir=/workspace/project', '--build-dir=/workspace/project/build', '--variant=debug']
    )

    assert project_dir == '/workspace/project'
    assert build_dir == '/workspace/project/build'


def test_parse_cli_arguments_keeps_global_version_before_command():
    global_args, command, command_args = parse_cli_arguments(
        ['golem', '--version', 'configure', '--clangd'],
        '/workspace/project',
    )

    assert global_args == ['--version']
    assert command == 'configure'
    assert command_args == [
        '--clangd',
        '--project-dir=/workspace/project',
        '--build-dir=/workspace/project/build',
    ]


def test_parse_cli_arguments_treats_only_flags_as_global_args_when_no_command_exists():
    global_args, command, command_args = parse_cli_arguments(
        ['golem', '--version'],
        '/workspace/project',
    )

    assert global_args == [
        '--version',
        '--project-dir=/workspace/project',
        '--build-dir=/workspace/project/build',
    ]
    assert command is None
    assert command_args == []