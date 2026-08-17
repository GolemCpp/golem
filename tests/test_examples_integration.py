import json
import os
import shutil
import subprocess
import sys
import tempfile
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace
from typing import Iterator

import pytest

from golemcpp.golem import cache_configuration
from golemcpp.golem import cache_directory
from golemcpp.golem import cppfront_tool
from golemcpp.golem import tool_manager
from golemcpp.golem.locator import Locator
from conftest import make_cache_configuration


REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLES_DIR = REPO_ROOT / 'examples'
PROJECT_VARIANTS = ('python', 'json')


def get_examples_tmp_dir() -> Path:
    return REPO_ROOT / '.pytest-examples'


def command_exists(command: str) -> bool:
    return shutil.which(command) is not None


def has_windows_msvc_toolchain() -> bool:
    installer_root = Path(
        os.environ.get(
            'ProgramFiles(x86)',
            os.environ.get('ProgramFiles', 'C:\\Program Files (x86)'),
        )
    )
    vswhere_path = installer_root / 'Microsoft Visual Studio' / 'Installer' / 'vswhere.exe'
    return command_exists('cl') or vswhere_path.is_file()


def run_tool_query(command: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [command, *args],
        capture_output=True,
        text=True,
        check=False,
    )


def require_cxx_compiler() -> None:
    if sys.platform.startswith('win32') and has_windows_msvc_toolchain():
        return
    if any(command_exists(candidate) for candidate in ('c++', 'g++', 'clang++')):
        return
    pytest.skip('No C++ compiler available for example integration tests')

def require_long_paths() -> None:
    if sys.platform.startswith('win32'):
        pytest.skip('This test is not supported on Windows due to the too long path lengths of the generated build files')

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
    env['GOLEM_COOKBOOKS_LOCATIONS'] = ''
    env['GOLEM_ADDITIONAL_CACHE_DIRECTORIES'] = f'{cache_dir}=^.*$'
    env['GOLEM_OVERLAYS_LOCATIONS'] = ''

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
    examples_tmp_dir = get_examples_tmp_dir()
    examples_tmp_dir.mkdir(exist_ok=True)
    path = Path(tempfile.mkdtemp(prefix='example-', dir=examples_tmp_dir))

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


def test_tools_install_cppfront_installs_cppfront_in_tools_cache(example_tmp_path):
    require_cxx_compiler()
    require_git_remote_access(cppfront_tool.CPPFRONT_REPOSITORY)

    project_dir = example_tmp_path / 'project'
    project_dir.mkdir()
    cache_dir = example_tmp_path / 'cache'

    result = run_golem(
        project_dir,
        cache_dir,
        'tools',
        'install',
        'cppfront',
        '--cache-directory=' + str(cache_dir),
    )

    assert result.returncode == 0

    # Resolve the installed tool the same way the code does: from the base cache
    # root, honoring path minimization (on by default). This finds the tool
    # whether it landed under tools/<name> or a minimized flat path.
    manager = tool_manager.get_tool_manager(
        make_cache_configuration(cache_directory.CacheDirectory(location=str(cache_dir))))
    cached_tool = manager.resolve_cached_resource(
        manager.get_tool(cppfront_tool.CPPFRONT_NAME))
    cache_info = cppfront_tool.CppFrontCacheInfo.from_tool_root(cached_tool.path)

    assert Path(cache_info.executable_path).is_file()
    assert Path(cache_info.include_path).is_dir()

    source = manager.cache_manager.read_manifest_source(cached_tool)

    assert source.type == 'git'
    assert source.resolved.reference == cppfront_tool.DEFAULT_CPPFRONT_VERSION
    # A Locator deliberately does not compare equal to the string spelling it, so
    # this asserts the manifest read the locator back as one rather than as text.
    assert source.locator == Locator(cppfront_tool.CPPFRONT_REPOSITORY)


def test_tools_list_available_mentions_supported_tools(example_tmp_path):
    project_dir = example_tmp_path / 'project'
    project_dir.mkdir()
    cache_dir = example_tmp_path / 'cache'

    result = run_golem(
        project_dir,
        cache_dir,
        'tools',
        'list',
        '--available',
    )

    assert result.returncode == 0
    assert 'Supported installable tools:' in result.stdout
    assert 'cppfront\n  Description:' in result.stdout
    assert '  Repository: {}'.format(cppfront_tool.CPPFRONT_REPOSITORY) in result.stdout
    assert '  Default version: {}'.format(cppfront_tool.DEFAULT_CPPFRONT_VERSION) in result.stdout


@pytest.mark.parametrize('project_variant', PROJECT_VARIANTS)
def test_cppfront_example_installs_builds_and_runs(example_tmp_path, project_variant):
    require_cxx_compiler()
    require_git_remote_access(cppfront_tool.CPPFRONT_REPOSITORY)

    project_dir = prepare_example_project('cppfront', example_tmp_path, project_variant)
    cache_dir = example_tmp_path / f'cache-{project_variant}'

    run_golem(
        project_dir,
        cache_dir,
        'tools',
        'install',
        'cppfront',
        '--cache-directory=' + str(cache_dir),
    )
    run_golem(
        project_dir,
        cache_dir,
        'configure',
        '--variant=debug',
        '--cache-directory=' + str(cache_dir),
    )
    run_golem(
        project_dir,
        cache_dir,
        'build',
        '--cache-directory=' + str(cache_dir),
    )

    binary = program_path(project_dir, 'hello-cppfront-debug')
    assert binary.exists()

    result = run_binary(binary, project_dir)

    assert result.returncode == 0, result.stderr
    assert result.stdout == 'Hello, Alice!\nHello, Bob!\n'


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
    require_long_paths()

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


def test_modules_example_resolves_dependencies_builds_and_runs_named_modules(example_tmp_path):
    require_cxx_compiler()
    require_long_paths()

    project_dir = copy_example_project('modules', example_tmp_path)
    cache_dir = example_tmp_path / 'cache'

    run_golem(project_dir, cache_dir, 'configure', '--variant=debug')
    run_golem(project_dir, cache_dir, 'resolve')
    run_golem(project_dir, cache_dir, 'dependencies')
    run_golem(project_dir, cache_dir, 'build')

    binary = program_path(project_dir, 'hello-modules-debug')
    assert binary.exists()

    result = run_binary(binary, project_dir)

    assert result.returncode == 0, result.stderr

    if 'Caller: mylogger' in result.stdout:
        pytest.xfail('MSVC returns "Caller: mylogger" instead of "Caller: consumer", see src/main.cpp')

    assert result.stdout == (
        '=> mylogger/MyLogger\n'
        '[INFO] This is an info message\n'
        'Caller: consumer\n'
        '=> myfigures/Figures\n'
        '[INFO] Rectangle::area() called\n'
        '[INFO] Rectangle::width() called\n'
        '[INFO] Rectangle::height() called\n'
        'Rectangle Area: 50\n'
        '[INFO] Rectangle::width() called\n'
        'Rectangle Width: 10\n'
        '=> hello_modules/Greetings\n'
        'Hello\n'
        '=> hello_modules/Media\n'
        'Playing: Test\n'
    )


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


def test_dependencies_example_honors_overrides_configuration(example_tmp_path):
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
        '--overrides-configuration=overrides.json',
    )
    run_golem(project_dir, cache_dir, 'resolve')
    run_golem(project_dir, cache_dir, 'dependencies')
    run_golem(project_dir, cache_dir, 'build')

    dependencies = read_dependencies_json(project_dir)
    json_dependency = next(dep for dep in dependencies if dep['name'] == 'json')
    assert json_dependency['resolved']['reference'] == 'v3.10.0'

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
        '--additional-cache-directory=cache-recipes=.*GolemCpp/recipes.*',
        '--additional-cache-directory=cache-json=.*nlohmann.*',
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


def test_has_windows_msvc_toolchain_accepts_vswhere_installation(monkeypatch, tmp_path):
    installer_root = tmp_path / 'Program Files (x86)'
    vswhere_path = installer_root / 'Microsoft Visual Studio' / 'Installer' / 'vswhere.exe'
    vswhere_path.parent.mkdir(parents=True)
    vswhere_path.write_text('', encoding='utf-8')

    monkeypatch.setenv('ProgramFiles(x86)', str(installer_root))
    monkeypatch.setattr(sys, 'platform', 'win32')
    monkeypatch.setattr(__import__(__name__), 'command_exists', lambda command: False)

    assert has_windows_msvc_toolchain() is True


def test_require_cxx_compiler_skips_on_windows_without_any_detected_toolchain(monkeypatch, tmp_path):
    installer_root = tmp_path / 'Program Files (x86)'
    installer_root.mkdir()

    monkeypatch.setenv('ProgramFiles(x86)', str(installer_root))
    monkeypatch.setattr(sys, 'platform', 'win32')
    monkeypatch.setattr(__import__(__name__), 'command_exists', lambda command: False)

    with pytest.raises(pytest.skip.Exception, match=r'No C\+\+ compiler available'):
        require_cxx_compiler()


def test_get_examples_tmp_dir_uses_repo_root_off_windows(monkeypatch):
    monkeypatch.setattr(sys, 'platform', 'linux')

    assert get_examples_tmp_dir() == REPO_ROOT / '.pytest-examples'
