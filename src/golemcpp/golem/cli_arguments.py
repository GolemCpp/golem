import os


def make_absolute_path(path: str, cwd: str) -> str:
    if os.path.isabs(path):
        return path
    return os.path.join(cwd, path)


def resolve_cli_arguments(argv: list[str], cwd: str) -> tuple[str | None, str, str, list[str]]:
    command = None
    project_dir = cwd
    build_dir = os.path.join(cwd, 'build')
    command_args = []

    has_explicit_build_dir = False

    for index, arg in enumerate(argv[1:], start=1):
        if arg.startswith('--project-dir='):
            requested_dir = arg.split('=', 1)[1]
            if requested_dir:
                project_dir = make_absolute_path(requested_dir, cwd)
            continue

        if arg.startswith('--build-dir='):
            requested_dir = arg.split('=', 1)[1]
            if requested_dir:
                build_dir = make_absolute_path(requested_dir, cwd)
            has_explicit_build_dir = True
            continue

        if not arg.startswith('-') and command is None:
            command = arg
            command_args = argv[index + 1:]

    # Deprecated --dir option, still supported for backward compatibility,
    # but overridden by --build-dir if both are present.
    for arg in argv[1:]:
        if arg.startswith('--dir=') and not has_explicit_build_dir:
            requested_dir = arg.split('=', 1)[1]
            if requested_dir:
                build_dir = make_absolute_path(requested_dir, cwd)

    return command, project_dir, build_dir, command_args


def normalize_argv(argv: list[str]) -> list[str]:
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
        if arg.startswith('--dir='):
            if not has_build_dir:
                normalized_argv.append('--build-dir=' + arg.split('=', 1)[1])

    return normalized_argv