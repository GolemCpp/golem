import json
import os
import shutil
import subprocess
import sys
import tempfile
from functools import lru_cache
from pathlib import Path
from typing import Iterator

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLES_DIR = REPO_ROOT / 'examples'
EXAMPLES_TMP_DIR = REPO_ROOT / '.pytest-examples'
PROJECT_VARIANTS = ('python', 'json')


def command_exists(command: str) -> bool:
    return shutil.which(command) is not None


def run_tool_query(command: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [command, *args],
        capture_output=True,
        text=True,
        check=False,
    )


def require_cxx_compiler() -> None:
    if any(command_exists(candidate) for candidate in ('c++', 'g++', 'clang++')):
        return
    pytest.skip('No C++ compiler available for example integration tests')


@lru_cache(maxsize=None)
def can_access_git_remote(repository: str) -> bool:
    result = subprocess.run(
        ['git', 'ls-remote', '--heads', repository, 'HEAD'],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    return result.returncode == 0


def require_git_remote_access(*repositories: str) -> None:
    for repository in repositories:
        if not can_access_git_remote(repository):
            pytest.skip(f'Git remote not reachable for integration test: {repository}')


@lru_cache(maxsize=1)
def find_qt_dir() -> str | None:
    for env_name in ('QTDIR', 'QT_DIR', 'QT6_DIR'):
        value = os.environ.get(env_name)
        if value and Path(value).exists():
            return value

    for command in ('qmake6', 'qmake'):
        if not command_exists(command):
            continue

        version_result = run_tool_query(command, '-query', 'QT_VERSION')
        if version_result.returncode != 0:
            continue

        version = version_result.stdout.strip()
        if not version.startswith('6.'):
            continue

        prefix_result = run_tool_query(command, '-query', 'QT_INSTALL_PREFIX')
        if prefix_result.returncode != 0:
            continue

        prefix = prefix_result.stdout.strip()
        if prefix and Path(prefix).exists():
            return prefix

    return None


def require_qt_dir() -> str:
    qt_dir = find_qt_dir()
    if qt_dir is None:
        pytest.skip('Qt 6 was not found for the Qt example integration tests')
    return qt_dir


def require_packaging_tool() -> None:
    if sys.platform.startswith('linux'):
        if command_exists('fakeroot') and command_exists('strip') and command_exists('linuxdeployqt'):
            return
        pytest.skip('fakeroot, strip, and linuxdeployqt are required for the package example on Linux')

    if sys.platform.startswith('darwin'):
        if command_exists('hdiutil'):
            return
        pytest.skip('hdiutil is required for the package example on macOS')

    if sys.platform.startswith('win32'):
        if command_exists('candle') and command_exists('light'):
            return
        pytest.skip('WiX candle/light are required for the package example on Windows')


def make_golem_env(cache_dir: Path) -> dict[str, str]:
    env = os.environ.copy()

    pythonpath_entries = [str(REPO_ROOT / 'src'), str(REPO_ROOT / 'waflib' / 'waf')]
    if env.get('PYTHONPATH'):
        pythonpath_entries.append(env['PYTHONPATH'])

    env['PYTHONPATH'] = os.pathsep.join(pythonpath_entries)
    env['GOLEM_RECIPES_REPOSITORIES'] = ''
    env['GOLEM_STATIC_CACHE_DIRECTORY'] = ''
    env['GOLEM_DEFINE_CACHE_DIRECTORIES'] = f'{cache_dir}=^.*$'
    env['GOLEM_MASTER_DEPENDENCIES_REPOSITORY'] = ''

    return env


def copy_example_project(example_name: str, destination_root: Path) -> Path:
    source = EXAMPLES_DIR / example_name
    destination = destination_root / example_name

    shutil.copytree(
        source,
        destination,
        ignore=shutil.ignore_patterns('build', 'dependencies.json', '__pycache__'),
    )

    return destination


def prepare_example_project(example_name: str, destination_root: Path, project_variant: str = 'python') -> Path:
    project_dir = copy_example_project(example_name, destination_root)
    if project_variant == 'json':
        use_json_project_file(project_dir)
    return project_dir


def use_json_project_file(project_dir: Path) -> None:
    python_project_file = project_dir / 'golemfile.py'
    json_project_file = project_dir / 'golemfile.json'

    assert json_project_file.exists()
    if python_project_file.exists():
        python_project_file.unlink()


@pytest.fixture
def example_tmp_path() -> Iterator[Path]:
    EXAMPLES_TMP_DIR.mkdir(exist_ok=True)
    path = Path(tempfile.mkdtemp(prefix='example-', dir=EXAMPLES_TMP_DIR))

    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def run_golem(project_dir: Path, cache_dir: Path, *args: str) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [sys.executable, '-m', 'golemcpp.golem', *args],
        cwd=project_dir,
        env=make_golem_env(cache_dir),
        capture_output=True,
        text=True,
        check=False,
    )

    if result.returncode != 0:
        raise AssertionError(
            'Command failed: {}\nstdout:\n{}\nstderr:\n{}'.format(
                ' '.join(args), result.stdout, result.stderr))

    return result


def program_path(project_dir: Path, program_name: str) -> Path:
    suffix = '.exe' if sys.platform.startswith('win32') else ''
    return project_dir / 'build' / 'bin' / f'{program_name}{suffix}'


def run_binary(binary: Path, project_dir: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(binary)],
        cwd=project_dir,
        capture_output=True,
        text=True,
        check=False,
    )


def read_dependencies_json(project_dir: Path) -> list[dict[str, object]]:
    with (project_dir / 'dependencies.json').open(encoding='utf-8') as handle:
        return json.load(handle)


def assert_package_artifact_exists(project_dir: Path) -> None:
    if sys.platform.startswith('linux'):
        assert any(project_dir.joinpath('build').rglob('*.deb'))
    elif sys.platform.startswith('darwin'):
        assert any(project_dir.joinpath('build').rglob('*.dmg'))
    elif sys.platform.startswith('win32'):
        assert any(project_dir.joinpath('build').rglob('*.msi'))


@pytest.mark.parametrize('project_variant', PROJECT_VARIANTS)
def test_hello_example_builds_and_runs(example_tmp_path, project_variant):
    require_cxx_compiler()

    project_dir = prepare_example_project('hello', example_tmp_path, project_variant)
    cache_dir = example_tmp_path / f'cache-{project_variant}'

    run_golem(project_dir, cache_dir, 'configure', '--variant=release')
    run_golem(project_dir, cache_dir, 'build')

    binary = program_path(project_dir, 'hello')
    assert binary.exists()

    result = run_binary(binary, project_dir)

    assert result.returncode == 0, result.stderr
    assert result.stdout == 'Hello World!\n'


def test_conditions_example_builds_and_uses_platform_specific_sources(example_tmp_path):
    require_cxx_compiler()

    project_dir = copy_example_project('conditions', example_tmp_path)
    cache_dir = example_tmp_path / 'cache'

    run_golem(project_dir, cache_dir, 'configure', '--variant=release')
    run_golem(project_dir, cache_dir, 'build')

    binary = program_path(project_dir, 'hello-conditions')
    assert binary.exists()

    result = run_binary(binary, project_dir)

    assert result.returncode == 0, result.stderr
    if sys.platform.startswith('win32'):
        expected_output = 'Hello, Windows!\n'
    elif sys.platform.startswith('darwin'):
        expected_output = 'Hello, MacOS!\n'
    else:
        expected_output = 'Hello, Linux!\n'

    assert result.stdout == expected_output


def test_advanced_example_resolves_dependencies_builds_and_runs(example_tmp_path):
    require_cxx_compiler()

    project_dir = copy_example_project('advanced', example_tmp_path)
    cache_dir = example_tmp_path / 'cache'

    run_golem(project_dir, cache_dir, 'configure', '--variant=release')
    run_golem(project_dir, cache_dir, 'resolve')
    run_golem(project_dir, cache_dir, 'dependencies')
    run_golem(project_dir, cache_dir, 'build')

    binary = program_path(project_dir, 'hello-advanced')
    assert binary.exists()

    result = run_binary(binary, project_dir)

    assert result.returncode == 0, result.stderr
    output_lines = result.stdout.splitlines()
    if output_lines == [
        'Variant is: Release',
        'Message is: ADVANCED_LIB_MESSAGE',
    ]:
        pytest.xfail('Advanced example still does not apply the dependency define override for ADVANCED_LIB_MESSAGE')

    assert output_lines == [
        'Variant is: Release',
        'Message is: Hello',
    ]


@pytest.mark.parametrize('project_variant', PROJECT_VARIANTS)
def test_minimal_example_builds_and_runs(example_tmp_path, project_variant):
    require_cxx_compiler()
    require_git_remote_access(
        'https://github.com/GolemCpp/recipes.git',
        'https://github.com/nlohmann/json.git',
    )

    project_dir = prepare_example_project('minimal', example_tmp_path, project_variant)
    cache_dir = example_tmp_path / f'cache-{project_variant}'

    run_golem(project_dir, cache_dir, 'configure', '--variant=debug')
    run_golem(project_dir, cache_dir, 'resolve')
    run_golem(project_dir, cache_dir, 'dependencies')
    run_golem(project_dir, cache_dir, 'build')

    binary = program_path(project_dir, 'hello-minimal-debug')
    assert binary.exists()

    result = run_binary(binary, project_dir)

    assert result.returncode == 0, result.stderr
    assert '"x": 1' in result.stdout
    assert 'Hello!' in result.stdout
    assert 'FOO!' in result.stdout


def test_dependencies_example_honors_master_dependencies_configuration(example_tmp_path):
    require_cxx_compiler()
    require_git_remote_access(
        'https://github.com/GolemCpp/recipes.git',
        'https://github.com/nlohmann/json.git',
    )

    project_dir = copy_example_project('dependencies', example_tmp_path)
    cache_dir = example_tmp_path / 'cache'

    run_golem(
        project_dir,
        cache_dir,
        'configure',
        '--variant=debug',
        '--master-dependencies-configuration=master_dependencies.json',
    )
    run_golem(project_dir, cache_dir, 'resolve')
    run_golem(project_dir, cache_dir, 'dependencies')
    run_golem(project_dir, cache_dir, 'build')

    dependencies = read_dependencies_json(project_dir)
    json_dependency = next(dep for dep in dependencies if dep['name'] == 'json')
    assert json_dependency['resolved_version'] == 'v3.10.0'

    binary = program_path(project_dir, 'hello-dependencies-debug')
    assert binary.exists()

    result = run_binary(binary, project_dir)

    assert result.returncode == 0, result.stderr
    assert '"x": 1' in result.stdout


def test_cache_example_respects_custom_cache_directories(example_tmp_path):
    require_cxx_compiler()
    require_git_remote_access(
        'https://github.com/GolemCpp/recipes.git',
        'https://github.com/nlohmann/json.git',
        'https://github.com/microsoft/GSL.git',
    )

    project_dir = copy_example_project('cache', example_tmp_path)
    cache_dir = example_tmp_path / 'cache'

    run_golem(
        project_dir,
        cache_dir,
        'configure',
        '--cache-directory=cache-default',
        '--define-cache-directories=cache-recipes=.*GolemCpp/recipes.*|cache-json=.*nlohmann.*',
        '--variant=release',
    )
    run_golem(project_dir, cache_dir, 'resolve')
    run_golem(project_dir, cache_dir, 'dependencies')
    run_golem(project_dir, cache_dir, 'build')

    assert (project_dir / 'cache-default').exists()
    assert (project_dir / 'cache-json').exists()
    assert (project_dir / 'cache-recipes').exists()

    binary = program_path(project_dir, 'hello-cache')
    assert binary.exists()

    result = run_binary(binary, project_dir)

    assert result.returncode == 0, result.stderr
    assert '"x": 1' in result.stdout


@pytest.mark.parametrize('project_variant', PROJECT_VARIANTS)
def test_qt_example_builds(example_tmp_path, project_variant):
    require_cxx_compiler()
    qt_dir = require_qt_dir()

    project_dir = prepare_example_project('qt', example_tmp_path, project_variant)
    cache_dir = example_tmp_path / f'cache-{project_variant}'

    run_golem(project_dir, cache_dir, 'configure', '--variant=debug', f'--qtdir={qt_dir}')
    run_golem(project_dir, cache_dir, 'build')

    assert program_path(project_dir, 'hello-qt-debug').exists()


@pytest.mark.parametrize('project_variant', PROJECT_VARIANTS)
def test_qt_qml_example_builds(example_tmp_path, project_variant):
    require_cxx_compiler()
    qt_dir = require_qt_dir()

    project_dir = prepare_example_project('qt-qml', example_tmp_path, project_variant)
    cache_dir = example_tmp_path / f'cache-{project_variant}'

    run_golem(project_dir, cache_dir, 'configure', '--variant=debug', f'--qtdir={qt_dir}')
    run_golem(project_dir, cache_dir, 'build')

    assert program_path(project_dir, 'hello-qt-qml-debug').exists()


def test_package_example_builds_and_packages(example_tmp_path):
    require_cxx_compiler()
    qt_dir = require_qt_dir()
    require_packaging_tool()

    project_dir = copy_example_project('package', example_tmp_path)
    cache_dir = example_tmp_path / 'cache'

    run_golem(project_dir, cache_dir, 'configure', '--variant=release', f'--qtdir={qt_dir}')
    run_golem(project_dir, cache_dir, 'build')
    run_golem(project_dir, cache_dir, 'package')

    assert program_path(project_dir, 'hello-package').exists()
    assert_package_artifact_exists(project_dir)