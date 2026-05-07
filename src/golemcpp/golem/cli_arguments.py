import os


def make_absolute_path(path: str, cwd: str) -> str:
    if os.path.isabs(path):
        return path
    return os.path.join(cwd, path)

def parse_global_and_command_arguments(argv: list[str]) -> tuple[list[str], str | None, list[str]]:
    global_args = []
    command = None
    command_args = []

    for index, arg in enumerate(argv[1:], start=1):
        if not arg.startswith('-') and command is None:
            global_args = argv[1:index]
            command = arg
            command_args = argv[index + 1:]

    if command is None:
        global_args = argv[1:]

    return global_args, command, command_args

def parse_cli_arguments(argv: list[str], cwd: str) -> tuple[list[str], str | None, list[str]]:
    # Default directories
    project_dir = cwd
    build_dir = os.path.join(cwd, 'build')

    # Normalize arguments
    argv = normalize_argv(argv, cwd, project_dir=project_dir, build_dir=build_dir)

    return parse_global_and_command_arguments(argv)

def parse_directories_from_arguments(argv: list[str]) -> tuple[str, str]:
    project_dir = None
    build_dir = None

    for arg in argv:
        if arg.startswith('--project-dir='):
            project_dir = arg.split('=', 1)[1]
        elif arg.startswith('--build-dir='):
            build_dir = arg.split('=', 1)[1]

    return project_dir, build_dir

def normalize_args_by_removing_deprecated_dir_option(argv: list[str]) -> list[str]:
    '''
    Normalizes deprecated command-line arguments by converting them to their modern equivalents.
    For example, converts --dir to --build-dir if --build-dir is not already present.
    '''
    normalized_argv = [argv[0]]
    has_build_dir = False

    for arg in argv[1:]:
        if arg.startswith('--dir='):
            continue

        if arg.startswith('--build-dir='):
            has_build_dir = True

        normalized_argv.append(arg)

    # Deprecated --dir option, still supported for backward compatibility,
    # but overridden by --build-dir if both are present.
    for arg in argv[1:]:
        if arg.startswith('--dir=') and not has_build_dir:
            normalized_argv.append('--build-dir=' + arg.split('=', 1)[1])
            has_build_dir = True

    return normalized_argv

def normalize_argv_by_adding_explicit_dirs(argv: list[str], project_dir: str | None = None, build_dir: str | None = None) -> list[str]:
    '''
    Normalizes the command-line arguments by appending --project-dir and --build-dir with provided values if they are not already specified in the arguments.
    They need to be passed explicitely to Waf, so that Golem keeps a consistent behavior between Golem-defined commands and direct Waf invocation.
    '''
    normalized_argv = list(argv)
    has_build_dir = any(arg.startswith('--build-dir=') for arg in argv)
    has_project_dir = any(arg.startswith('--project-dir=') for arg in argv)

    if project_dir is not None and not has_project_dir:
        normalized_argv.append('--project-dir=' + project_dir)

    if build_dir is not None and not has_build_dir:
        normalized_argv.append('--build-dir=' + build_dir)

    return normalized_argv

def normalize_argv_by_resolving_dirs(argv: list[str], cwd: str) -> list[str]:
    '''
    Normalizes the command-line arguments by resolving --project-dir and --build-dir to absolute paths.
    This is useful to ensure that all parts of the code can rely on these arguments being absolute paths, regardless of how the user specified them.
    '''
    normalized_argv = []
    for arg in argv:
        if arg.startswith('--project-dir='):
            requested_dir = arg.split('=', 1)[1]
            if requested_dir:
                resolved_dir = make_absolute_path(requested_dir, cwd)
                normalized_argv.append('--project-dir=' + resolved_dir)
            else:
                normalized_argv.append(arg)
            continue

        if arg.startswith('--build-dir='):
            requested_dir = arg.split('=', 1)[1]
            if requested_dir:
                resolved_dir = make_absolute_path(requested_dir, cwd)
                normalized_argv.append('--build-dir=' + resolved_dir)
            else:
                normalized_argv.append(arg)
            continue

        normalized_argv.append(arg)

    return normalized_argv

def normalize_argv_by_moving_explicit_dirs_after_command(argv: list[str]) -> list[str]:
    '''
    Normalizes the command-line arguments by moving --project-dir and --build-dir after the command, so that they are not parsed as global arguments but as command-specific arguments.
    '''
    global_args, command, command_args = parse_global_and_command_arguments(argv)

    if command is None:
        return argv

    dirs_to_move = [ '--project-dir=', '--build-dir=' ]

    if not any(arg.startswith(tuple(dirs_to_move)) for arg in global_args):
        return argv
    
    new_argv = [argv[0]]
    new_argv += [arg for arg in global_args if not arg.startswith(tuple(dirs_to_move))]
    new_argv.append(command)
    new_argv += [arg for arg in global_args if arg.startswith(tuple(dirs_to_move))]
    new_argv += command_args
    return new_argv

def normalize_argv(argv: list[str], cwd: str, project_dir: str | None = None, build_dir: str | None = None) -> list[str]:
    argv = normalize_args_by_removing_deprecated_dir_option(argv)
    argv = normalize_argv_by_adding_explicit_dirs(argv, project_dir=project_dir, build_dir=build_dir)
    argv = normalize_argv_by_resolving_dirs(argv, cwd)
    argv = normalize_argv_by_moving_explicit_dirs_after_command(argv)
    return argv