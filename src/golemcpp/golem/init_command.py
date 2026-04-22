from pathlib import Path


def initialize_project(project_dir: str, data_dir: Path, force: bool = False) -> int:
    project_path = Path(project_dir).joinpath('golemfile.py')
    alternate_project_path = Path(project_dir).joinpath('golemfile.json')

    if not force:
        project_file_found = False
        if alternate_project_path.exists():
            print("ERROR: golemfile.json already exists in this directory")
            project_file_found = True

        if project_path.exists():
            print("ERROR: golemfile.py already exists in this directory")
            project_file_found = True

        if project_file_found:
            print("Use `golem init --force` to remove existing project files and generate a new golemfile.py.")
            return 1
    else:
        print("WARNING: --force option removes existing golemfile.py and golemfile.json files in the project directory if they exist.")

        if alternate_project_path.exists():
            alternate_project_path.unlink()
            print("Removed {}".format(alternate_project_path))

        if project_path.exists():
            project_path.unlink()
            print("Removed {}".format(project_path))

    template_path = data_dir.joinpath('golemfile.py.template')
    with open(template_path, 'r', encoding='utf-8') as filein:
        content = filein.read()

    with open(project_path, 'w', encoding='utf-8') as fileout:
        fileout.write(content)

    print("Created {}".format(project_path))
    print("Add your sources, then run `golem configure --variant=debug` and `golem build`.")
    return 0


def handle_init_command(project_dir: str, data_dir: Path, args: list[str]) -> int:
    force = False

    for arg in args:
        if arg.startswith('--project-dir='):
            continue
        if arg in ('-h', '--help'):
            print("Usage: golem init [--project-dir=<project_dir>] [--force]")
            print("Generate a commented golemfile.py in the current project directory.")
            return 0
        if arg == '--force':
            force = True
            continue

        print("ERROR: unsupported option for `golem init`: {}".format(arg))
        print("Usage: golem init [--project-dir=<project_dir>] [--force]")
        return 1

    return initialize_project(project_dir=project_dir, data_dir=data_dir, force=force)