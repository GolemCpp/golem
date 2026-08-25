import shutil
import sys
import tempfile
from pathlib import Path
from typing import Iterator

import pytest

from golemcpp.golem import cache_directory
from golemcpp.golem import cppfront_tool
from golemcpp.golem import target_platform
from golemcpp.golem import tool_manager
from golemcpp.golem.locator import Locator
from example_project import assert_package_artifact_exists
from example_project import copy_example_project
from example_project import get_examples_tmp_dir
from example_project import prepare_example_project
from example_project import program_path
from example_project import read_dependencies_json
from example_project import run_binary
from example_project import run_golem
from example_project import REQUESTED_ARCH
from example_project import TARGET_LINE
from host import require_cxx_compiler
from host import require_git_remote_access
from host import require_packaging_tool
from host import require_qt_dir
from support import make_cache_configuration


PROJECT_VARIANTS = ('python', 'json')


@pytest.fixture
def example_tmp_path() -> Iterator[Path]:
    examples_tmp_dir = get_examples_tmp_dir()
    examples_tmp_dir.mkdir(exist_ok=True)
    path = Path(tempfile.mkdtemp(prefix='example-', dir=examples_tmp_dir))

    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


# --- No further than configure -------------------------------------------
#
# These run the real command line and stop at configure. They are the only
# tests outside the unit suite that run on every pull request, so they are
# what stands between a broken `golem configure` and a green develop.
#
# The target is settled by the end of configure, so the architecture model is
# exercised here too. Stopping here makes CI runners affordable. A runner is
# the only place some of the model can be exercised at all: the splice of a
# compiler's ABI with uname's ISA level needs a real 32-bit ARM userland, and
# every other test of it feeds the machine string in by hand.


def configure_example(example_name: str, destination: Path, *args: str) -> str:
    '''Configure an example, build nothing, and return the target it settled on.'''
    require_cxx_compiler()

    project_dir = prepare_example_project(example_name, destination)
    result = run_golem(project_dir, destination / 'cache', 'configure',
                       '--variant=release', *args)

    reported = TARGET_LINE.search(result.stdout)
    assert reported is not None, result.stdout
    return reported.group(1)


@pytest.mark.configure
def test_configure_settles_a_target_this_host_can_be_asked_for(example_tmp_path):
    # Self-validating, which is what lets it run on a host nobody has named:
    # whatever the compiler was understood to say is handed straight back as a
    # request, and settling refuses a request it disagrees with. A misread
    # triple names something the same compiler then rejects.
    settled = configure_example('hello', example_tmp_path)

    assert target_platform.is_arch_name(settled)
    assert configure_example('hello', example_tmp_path / 'again') == settled


@pytest.mark.configure
@pytest.mark.skipif(not REQUESTED_ARCH, reason='no architecture was asked for')
def test_configure_honours_the_architecture_it_was_asked_for(example_tmp_path):
    # Only the legs that ask for something the runner is not: 32-bit Windows on
    # a 64-bit host, and aarch64 from an x64 one. Settling refuses a request the
    # compiler disagrees with, so a green configure is already most of the
    # proof; this names what the leg is there to show.
    settled = configure_example('hello', example_tmp_path)

    assert settled == target_platform.normalize_arch(REQUESTED_ARCH)


@pytest.mark.configure
def test_configure_evaluates_conditions_that_name_a_target(example_tmp_path):
    # A condition can name an architecture, an operating system or a compiler,
    # and all three are answers only the chosen toolchain gives. Selecting
    # tasks before finding it raised on every golemfile carrying a when().
    assert configure_example('conditions', example_tmp_path)


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


@pytest.mark.configure
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

    project_dir = copy_example_project('modules', example_tmp_path)
    cache_dir = example_tmp_path / 'cache'

    try:
        run_golem(project_dir, cache_dir, 'configure', '--variant=debug')
        run_golem(project_dir, cache_dir, 'resolve')
        run_golem(project_dir, cache_dir, 'dependencies')
        run_golem(project_dir, cache_dir, 'build')
    except AssertionError as failure:
        # `import std;` needs the standard library to ship a module of its own,
        # which is a metadata file beside it.
        #
        # Matched on the symptom rather than on a list of toolchains, so that
        # any other way of failing stays a failure, and so that a toolchain
        # gaining the module needs no edit here.
        if 'std modules metadata file not found' not in str(failure):
            raise
        pytest.xfail('This toolchain ships no std module for import std')

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
    require_git_remote_access('https://github.com/nlohmann/json.git')

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
    require_git_remote_access('https://github.com/nlohmann/json.git')

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
        # Matched against the whole locator, so the cookbook's pattern has to
        # hold for the checkout and for the copy this test runs in. Its trailing
        # directory name is the part that is the same in both.
        '--additional-cache-directory=cache-cookbook=.*cookbook$',
        '--additional-cache-directory=cache-json=.*nlohmann.*',
        '--variant=release',
    )
    run_golem(project_dir, cache_dir, 'resolve')
    run_golem(project_dir, cache_dir, 'dependencies')
    run_golem(project_dir, cache_dir, 'build')

    # Non-empty, not merely present: the example gitignores these rather than
    # not having them, so an existence check passes on a machine that has run it
    # in place whether or not this run wrote anything.
    for bucket in ('cache-default', 'cache-json', 'cache-cookbook'):
        assert any((project_dir / bucket).iterdir()), bucket

    binary = program_path(project_dir, 'hello-cache')
    assert binary.exists()

    result = run_binary(binary, project_dir)

    assert result.returncode == 0, result.stderr
    assert '"x": 1' in result.stdout


@pytest.mark.qt
@pytest.mark.parametrize('project_variant', PROJECT_VARIANTS)
def test_qt_example_builds(example_tmp_path, project_variant):
    require_cxx_compiler()
    qt_dir = require_qt_dir()

    project_dir = prepare_example_project('qt', example_tmp_path, project_variant)
    cache_dir = example_tmp_path / f'cache-{project_variant}'

    run_golem(project_dir, cache_dir, 'configure', '--variant=debug', f'--qtdir={qt_dir}')
    run_golem(project_dir, cache_dir, 'build')

    assert program_path(project_dir, 'hello-qt-debug').exists()


@pytest.mark.qt
@pytest.mark.parametrize('project_variant', PROJECT_VARIANTS)
def test_qt_qml_example_builds(example_tmp_path, project_variant):
    require_cxx_compiler()
    qt_dir = require_qt_dir()

    project_dir = prepare_example_project('qt-qml', example_tmp_path, project_variant)
    cache_dir = example_tmp_path / f'cache-{project_variant}'

    run_golem(project_dir, cache_dir, 'configure', '--variant=debug', f'--qtdir={qt_dir}')
    run_golem(project_dir, cache_dir, 'build')

    assert program_path(project_dir, 'hello-qt-qml-debug').exists()


@pytest.mark.qt
@pytest.mark.packaging
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
