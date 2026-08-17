import os
import pytest
from types import SimpleNamespace
import json

from golemcpp.golem import context as golem_context, helpers, qt_discovery
from golemcpp.golem.settings import get_settings
from golemcpp.golem.cache_configuration import (
    CacheConfiguration, DEPENDENCIES_SUBDIR, COOKBOOKS_SUBDIR)
from golemcpp.golem.cache_resolution_policy import CacheResolutionPolicy
from golemcpp.golem.cache_directory import CacheDirectory
from golemcpp.golem.context import Context
from golemcpp.golem.dependency import Dependency
from golemcpp.golem.dependency_manager import get_dependency_manager
from golemcpp.golem.cookbook_manager import get_cookbook_manager
from golemcpp.golem.source import Source
from conftest import absolute_path, make_cache_configuration


class AttrDict(dict):
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name, value):
        self[name] = value


def make_configure_context(project_qt=True, project_qtdir=''):
    context = Context.__new__(Context)
    context.project = SimpleNamespace(
        qt=project_qt,
        qtdir=project_qtdir,
        enable_qt=lambda: None,
    )
    context.context = SimpleNamespace(
        options=SimpleNamespace(
            qtdir='',
            force_version=None,
            runtime_link='shared',
            runtime_variant=None,
            variant='debug',
            link='shared',
            arch='x64',
            project_dir=os.getcwd(),
            compile_commands=False,
            vscode=False,
            clangd=False,
        ),
        want_qt6=False,
        env=SimpleNamespace(),
        setenv=lambda _: None,
        load=lambda _: None,
    )
    context.version = SimpleNamespace(force_version=lambda _: None)
    context.make_cache_configuration = lambda: None
    context.load_recipe = lambda: None
    context.get_tasks_and_targets_to_process = lambda: []
    context.ensures_qt_is_installed = lambda: None
    context.configure_compiler = lambda: None
    context.save_options = lambda: None
    context.is_windows = lambda: False
    context.get_arch = lambda: 'x64'
    return context


def make_task_config(*, features=None, wfeatures=None, source=None):
    config = golem_context.Configuration(
        features=features or [],
        wfeatures=wfeatures or [],
        source=source or [],
    )
    config.type = []
    return config


def test_configure_autodiscovers_qtdir_when_qt_is_enabled_and_other_sources_are_missing(monkeypatch):
    context = make_configure_context()
    context.get_tasks_and_targets_to_process = lambda: [(
        make_task_config(features=['QT6CORE']),
        None,
    )]

    monkeypatch.delenv('QT5_ROOT', raising=False)
    monkeypatch.delenv('QT6_ROOT', raising=False)
    monkeypatch.setattr(context, 'is_qmake_available_on_path', lambda wants_qt6=False: False)
    monkeypatch.setattr(
        qt_discovery,
        'search_for_qt_root_in_default_dirs',
        lambda _, wants_qt6=False: '/opt/Qt/6.7.2/gcc_64' if wants_qt6 else '/opt/Qt/5.15.2/gcc_64',
    )

    context.configure()

    assert context.context.options.qtdir == '/opt/Qt/6.7.2/gcc_64'


def test_configure_skips_qtdir_autodiscovery_when_qmake_or_qt_roots_are_available(monkeypatch):
    test_cases = [
        {'env': {'QT5_ROOT': '/opt/Qt/5.15.2/gcc_64'}, 'qmake': False, 'wants_qt6': False},
        {'env': {'QT6_ROOT': '/opt/Qt/6.7.2/gcc_64'}, 'qmake': False, 'wants_qt6': True},
        {'env': {}, 'qmake': True, 'wants_qt6': False},
    ]

    for test_case in test_cases:
        context = make_configure_context()
        called = {'search': False}
        context.get_tasks_and_targets_to_process = lambda: [(
            make_task_config(
                features=['QT6CORE'] if test_case['wants_qt6'] else ['QT5CORE'],
                wfeatures=['qt6'] if test_case['wants_qt6'] else [],
            ),
            None,
        )]

        monkeypatch.delenv('QT5_ROOT', raising=False)
        monkeypatch.delenv('QT6_ROOT', raising=False)
        for name, value in test_case['env'].items():
            monkeypatch.setenv(name, value)

        monkeypatch.setattr(
            context,
            'is_qmake_available_on_path',
            lambda wants_qt6=False: test_case['qmake'],
        )

        def fake_search(_, wants_qt6=False):
            called['search'] = True
            return '/opt/Qt/6.7.2/gcc_64' if wants_qt6 else '/opt/Qt/5.15.2/gcc_64'

        monkeypatch.setattr(qt_discovery, 'search_for_qt_root_in_default_dirs', fake_search)

        context.configure()

        assert called['search'] is False
        assert context.context.options.qtdir == ''


def test_configure_autodiscovers_qtdir_when_only_other_qt_major_root_is_set(monkeypatch):
    context = make_configure_context()

    monkeypatch.delenv('QT5_ROOT', raising=False)
    monkeypatch.delenv('QT6_ROOT', raising=False)
    monkeypatch.setenv('QT6_ROOT', '/opt/Qt/6.7.2/gcc_64')
    monkeypatch.setattr(context, 'is_qmake_available_on_path', lambda wants_qt6=False: False)

    called = {'search': False}

    def fake_search(_, wants_qt6=False):
        called['search'] = True
        assert wants_qt6 is False
        return '/opt/Qt/5.15.2/gcc_64'

    monkeypatch.setattr(qt_discovery, 'search_for_qt_root_in_default_dirs', fake_search)

    context.configure()

    assert called['search'] is True
    assert context.context.options.qtdir == '/opt/Qt/5.15.2/gcc_64'


def make_runtime_context(*,
                         variant='debug',
                         runtime_link='shared',
                         runtime_variant=None,
                         link='shared'):
    context = Context.__new__(Context)
    # Both are set by Context.__init__, which building through __new__ skips.
    context.project = None
    context.settings = None
    context.context = SimpleNamespace(
        options=SimpleNamespace(
            variant=variant,
            runtime_link=runtime_link,
            runtime_variant=runtime_variant,
            link=link,
            arch='x64',
            nounicode=False,
            compile_commands=False,
            vscode=False,
            clangd=False,
        ),
        env=SimpleNamespace(
            DEFINES=[],
            CXXFLAGS=[],
            CFLAGS=[],
            LINKFLAGS=[],
            ARFLAGS=[],
            ISYSTEMS=[],
        ),
    )
    context.is_windows = lambda: True
    context.get_arch = lambda: 'x64'
    context.osname = lambda: 'windows'
    context.compiler_min = lambda: 'm'
    context.is_msvc_like = lambda: True
    return context


def test_runtime_uses_runtime_link_option_and_runtime_variant_defaults_to_variant():
    context = make_runtime_context(variant='release', runtime_link='static')

    assert context.runtime_link() == 'static'
    assert context.runtime_variant() == 'release'


def test_runtime_link_requires_normalized_dependency():
    context = make_runtime_context()

    with pytest.raises(AttributeError):
        context.runtime_link(SimpleNamespace(runtime_variant=None))


def test_restore_options_env_upgrades_legacy_runtime_option():
    context = make_runtime_context()
    context.context.env = SimpleNamespace(
        OPTIONS=json.dumps({
            'runtime': 'static',
            'targets': '',
            'only_update_dependencies_regex': '',
            'output_file': '',
        })
    )
    context.context.options.targets = ''
    context.context.options.output_file = ''
    context.context.options.only_update_dependencies_regex = ''

    restored = context.restore_options_env(context.context.env)

    assert restored['runtime_link'] == 'static'
    assert 'runtime_variant' in restored


def test_build_path_on_windows_includes_runtime_variant_segment():
    context = make_runtime_context(runtime_variant='release')

    assert context.build_path() == 'w64mshrshd'


def test_configure_debug_keeps_debug_flags_with_release_runtime_variant():
    context = make_runtime_context(runtime_variant='release')

    flags = context.make_default_build_flags(variant='debug')

    assert '/MD' in flags['cxxflags']
    assert '/MDd' not in flags['cxxflags']
    assert '/Od' in flags['cxxflags']
    assert '/RTC1' in flags['cxxflags']


def test_make_default_build_flags_enables_utf8_for_msvc():
    context = make_runtime_context()

    flags = context.make_default_build_flags(variant='debug')

    assert '/utf-8' in flags['cflags']
    assert '/utf-8' in flags['cxxflags']


def make_build_target_context(*, variant='release', no_defaults=False):
    context = Context.__new__(Context)
    context.project = SimpleNamespace(deps=[])
    context.context = SimpleNamespace(
        options=SimpleNamespace(
            nounicode=False,
            variant=variant,
            runtime_link='shared',
            runtime_variant='release',
            link='shared',
            arch='x64',
            compile_commands=False,
            vscode=False,
            clangd=False,
        ),
        env=AttrDict(
            DEFINES=['FROM_ENV'],
            CXXFLAGS=['/env-cxx'],
            CFLAGS=['/env-c'],
            LINKFLAGS=['/env-link'],
            ARFLAGS=[],
            ISYSTEMS=[],
        ),
        root=SimpleNamespace(
            find_or_declare=lambda path: path,
            find_node=lambda path: path,
        ),
        add_group=lambda: None,
    )
    context.context_tasks = []
    context.make_decorated_target_list_from_context = lambda config, target_names: target_names
    context.make_decorated_target_from_context = lambda config, target_name: target_name
    context.is_qt5_used = lambda config: False
    context.is_qt6_used = lambda config: False
    context.is_qt_enabled = lambda config: False
    context.is_debug = lambda: variant == 'debug'
    context.is_windows = lambda: True
    context.is_linux = lambda: False
    context.is_darwin = lambda: False
    context.is_android = lambda: False
    context.is_msvc_like = lambda: True
    context.is_x86 = lambda: False
    context.is_x64 = lambda: True
    context.is_runtime_static = lambda: False
    context.is_runtime_shared = lambda: True
    context.is_runtime_variant_debug = lambda: False
    context.list_include = lambda includes, project_dir: list(includes)
    context.list_qt_qrc = lambda source: []
    context.list_source = lambda source: list(source)
    context.list_qt_ui = lambda source: []
    context.list_moc = lambda moc: []
    context.list_template = lambda source: []
    context.get_project_dir = lambda: '/tmp/project'
    context.get_build_number = lambda default=None: 0
    context.osname = lambda: 'windows'
    context.get_arch = lambda: 'x64'
    context.compiler_name = lambda: 'msvc'
    context.make_c_standard_flag = lambda standard, compiler_name: None
    context.make_cxx_standard_flag = lambda standard, compiler_name: None
    context.strip_language_standard_flags = Context.strip_language_standard_flags
    context.make_out_path = lambda: '/tmp/out'
    context.make_target_out = lambda: '/tmp/out'
    context.patch_linux_binary_artifacts = lambda **kwargs: []
    context.make_artifacts_list = lambda config, decorated_target: []

    task = SimpleNamespace(
        name='demo',
        version_template=None,
        templates=None,
        type_unique='program',
    )
    config = golem_context.Configuration(type='program', no_defaults=no_defaults)
    config.type = 'program'

    return context, task, config


def make_static_library_build_target_context(*, variant='release', no_defaults=False):
    context, task, config = make_build_target_context(
        variant=variant, no_defaults=no_defaults)
    context.is_shared = lambda: False
    context.is_static = lambda: True
    task.type_unique = 'library'
    task.link = ['static']
    task.link_unique = 'static'
    config.type = ['library']

    return context, task, config


def test_build_target_gather_config_applies_default_flags_per_target(monkeypatch):
    context, task, config = make_build_target_context(no_defaults=False)

    monkeypatch.setattr(
        golem_context,
        'Version',
        lambda working_dir, build_number: SimpleNamespace(semver_short='1.2.3'),
    )

    build_target = context.build_target_gather_config(task=task, targets=['demo'], config=config)

    assert 'UNICODE' in build_target.defines
    assert 'NDEBUG' in build_target.defines
    assert '/MACHINE:X64' in build_target.linkflags
    assert '/INCREMENTAL:NO' in build_target.linkflags
    assert '/MD' in build_target.cxxflags
    assert '/O2' in build_target.cxxflags
    assert build_target.env_defines == ['FROM_ENV']
    assert build_target.env_cxxflags == ['/env-cxx']


def test_build_target_gather_config_skips_default_flags_when_no_defaults_is_enabled(monkeypatch):
    context, task, config = make_build_target_context(no_defaults=True)

    monkeypatch.setattr(
        golem_context,
        'Version',
        lambda working_dir, build_number: SimpleNamespace(semver_short='1.2.3'),
    )

    build_target = context.build_target_gather_config(task=task, targets=['demo'], config=config)

    assert 'UNICODE' not in build_target.defines
    assert 'NDEBUG' not in build_target.defines
    assert '/MACHINE:X64' not in build_target.linkflags
    assert '/INCREMENTAL:NO' not in build_target.linkflags
    assert '/MD' not in build_target.cxxflags
    assert '/O2' not in build_target.cxxflags
    assert build_target.env_defines == ['FROM_ENV']
    assert build_target.env_cxxflags == ['/env-cxx']


def test_build_target_gather_config_applies_default_arflags_per_target(monkeypatch):
    context, task, config = make_static_library_build_target_context(
        no_defaults=False)

    monkeypatch.setattr(
        golem_context,
        'Version',
        lambda working_dir, build_number: SimpleNamespace(semver_short='1.2.3'),
    )

    build_target = context.build_target_gather_config(task=task, targets=['demo'], config=config)

    assert '/MACHINE:X64' in build_target.arflags
    assert '/INCREMENTAL:NO' in build_target.arflags


def test_build_target_gather_config_merges_config_arflags(monkeypatch):
    context, task, config = make_static_library_build_target_context(
        no_defaults=False)
    config.arflags = ['/custom-arflag']

    monkeypatch.setattr(
        golem_context,
        'Version',
        lambda working_dir, build_number: SimpleNamespace(semver_short='1.2.3'),
    )

    build_target = context.build_target_gather_config(task=task, targets=['demo'], config=config)

    assert '/MACHINE:X64' in build_target.arflags
    assert '/INCREMENTAL:NO' in build_target.arflags
    assert '/custom-arflag' in build_target.arflags


def test_build_target_gather_config_skips_default_arflags_when_no_defaults_is_enabled(monkeypatch):
    context, task, config = make_static_library_build_target_context(
        no_defaults=True)
    config.arflags = ['/custom-arflag']

    monkeypatch.setattr(
        golem_context,
        'Version',
        lambda working_dir, build_number: SimpleNamespace(semver_short='1.2.3'),
    )

    build_target = context.build_target_gather_config(task=task, targets=['demo'], config=config)

    assert '/MACHINE:X64' not in build_target.arflags
    assert '/INCREMENTAL:NO' not in build_target.arflags
    assert build_target.arflags == ['/custom-arflag']


def test_run_dep_command_forwards_runtime_link_and_runtime_variant(monkeypatch):
    context = make_runtime_context(runtime_variant='release')
    context.resolved_overrides = '/tmp/overrides.json'
    context.get_dep_location = lambda dep: '/tmp/dep-export'
    context.make_repo_ready = lambda dep, should_clean=False: '/tmp/repo'
    context.get_dep_build_location = lambda dep: '/tmp/repo/build'
    context.get_global_dependencies_configuration_file = lambda: '/tmp/global-dependencies.json'
    context.get_only_update_dependencies_regex = lambda: ''
    # The cache options forwarded to the dependency sub-build are the flags the
    # settings spell, so the sub-build reaches the same caches with the same layout.
    project_dir = absolute_path('tmp', 'project')
    cache_dir = absolute_path('tmp', 'cache')
    context.settings = get_settings(
        project_dir=project_dir,
        options=SimpleNamespace(
            cache_directory=cache_dir,
            cache_minimization_enabled='off',
            cache_minimization_length=12,
            additional_cache_directory=['shared=github'],
        ))

    dep = SimpleNamespace(
        name='demo',
        version='1.0.0',
        runtime_link=None,
        runtime_variant=None,
        link=None,
        variant=None,
        shallow=False,
        resolved_version='1.0.0',
    )

    calls = []

    monkeypatch.setattr(golem_context.Logs, 'info', lambda *args, **kwargs: None)
    monkeypatch.setattr(helpers, 'make_golem_command', lambda command: [command])
    monkeypatch.setattr(helpers, 'run_task', lambda args, cwd=None, stdout=None: calls.append(args))

    context.run_dep_command(dep=dep, command='resolve')

    assert '--runtime-link=shared' in calls[0]
    assert '--runtime-variant=release' in calls[0]
    assert '--runtime=shared' not in calls[0]
    # Path minimization settings are forwarded to the dependency sub-build so it
    # resolves cache paths with the same layout as the parent.
    assert '--cache-directory={}'.format(cache_dir) in calls[0]
    assert '--cache-minimization-enabled=off' in calls[0]
    assert '--cache-minimization-length=12' in calls[0]
    # A relative cache directory is forwarded absolute: the sub-build runs
    # elsewhere and would otherwise resolve it against its own directory.
    assert '--additional-cache-directory={}=github'.format(
        os.path.join(project_dir, 'shared')) in calls[0]


def make_repository_context(project_dir, *, deps_resolve=True, no_cookbooks_fetch=False):
    context = Context.__new__(Context)
    context.project = SimpleNamespace()
    context.context = SimpleNamespace(
        options=SimpleNamespace(
            project_dir=str(project_dir),
            no_cookbooks_fetch=no_cookbooks_fetch,
            cache_resolution_policy='strict',
            cache_minimization_enabled='',
            cache_minimization_length=0,
        ))
    context.deps_resolve = deps_resolve
    # Built lazily by Context.get_settings(), which __init__ would have reset.
    context.settings = None
    # Cache settings now live on the CacheConfiguration the CacheManager is built from
    # (default: path-minimization enabled). Tests that need a different layout or
    # specific cache locations override context.cache_configuration explicitly.
    context.cache_configuration = make_cache_configuration()
    return context

def test_directory_dependency_is_detected_as_non_git(tmp_path):
    directory = tmp_path / 'recipes'
    directory.mkdir()

    dependency = Dependency(directory=directory.resolve().as_uri())

    assert dependency.is_non_git_directory()
    assert Source.detect(dependency.directory) == 'directory'


def test_detect_ignores_local_git_directory(tmp_path):
    repository_dir = tmp_path / 'recipes'
    git_dir = repository_dir / '.git'
    git_dir.mkdir(parents=True)
    (git_dir / 'HEAD').write_text('ref: refs/heads/main\n', encoding='utf-8')

    dependency = Dependency(repository=repository_dir.resolve().as_uri())

    assert Source.detect(dependency.repository) == 'git'
    assert Source.parse_local_directory_path(url=dependency.repository) == str(repository_dir)


def test_a_dependency_location_resolves_to_the_kind_it_spells(tmp_path):
    lib_dir = tmp_path / 'mylib'
    lib_dir.mkdir()

    detected = Dependency(location='mylib')
    detected.update_source(str(tmp_path))
    assert detected.directory == lib_dir.resolve().as_uri()
    assert detected.repository == ''
    assert detected.location == ''

    cloned = Dependency(location='git+mylib')
    cloned.update_source(str(tmp_path))
    assert cloned.repository == lib_dir.resolve().as_uri()
    assert cloned.directory == ''


@pytest.mark.parametrize('sources', [
    {'location': './mylib', 'repository': 'https://host/r.git'},
    {'location': './mylib', 'directory': './mylib'},
    {'repository': 'https://host/r.git', 'directory': './mylib'},
    {'location': './mylib', 'repository': 'https://host/r.git', 'directory': './mylib'},
])
def test_a_dependency_declares_exactly_one_source(sources):
    with pytest.raises(ValueError, match='declares several sources'):
        Dependency(name='mylib', **sources)


def test_a_dependency_may_declare_no_source_yet():
    # unserialize_from_json builds an empty one before filling it in.
    assert Dependency().get_source_location() == ''


def test_several_sources_are_refused_when_read_from_a_configuration(tmp_path):
    # read_json writes the members straight in, so __init__ never sees them.
    override = Dependency.unserialize_from_json(
        {'repository': 'https://host/r.git', 'directory': './mylib'})

    with pytest.raises(ValueError, match='declares several sources'):
        override.update_source(str(tmp_path))


def test_get_cookbook_locations_normalizes_local_paths(monkeypatch, tmp_path):
    context = make_repository_context(project_dir=tmp_path)
    recipes_dir = tmp_path / 'recipes'
    recipes_dir.mkdir()

    monkeypatch.setenv('GOLEM_COOKBOOKS_LOCATIONS', 'recipes')

    cookbooks = context.get_settings().get('GOLEM_COOKBOOKS_LOCATIONS')

    assert [cookbook.location for cookbook in cookbooks] == [recipes_dir.resolve().as_uri()]


def test_get_overlay_locations_normalizes_local_paths(monkeypatch, tmp_path):
    context = make_repository_context(project_dir=tmp_path)
    overrides_dir = tmp_path / 'overrides'
    overrides_dir.mkdir()

    monkeypatch.setenv('GOLEM_OVERLAYS_LOCATIONS', 'overrides')

    assert [overlay.location for overlay in context.get_overlay_locations()] == \
        [overrides_dir.resolve().as_uri()]


def test_normalize_repository_url_percent_encodes_local_paths(tmp_path):
    project_dir = tmp_path / 'project dir'
    recipes_dir = project_dir / 'recipes #1'
    recipes_dir.mkdir(parents=True)

    repository = Source.parse('recipes #1', str(project_dir)).location

    assert repository == recipes_dir.resolve().as_uri()
    assert Source.parse_local_directory_path(repository) == str(recipes_dir.resolve())


def test_run_command_uses_subprocess_without_shell_on_windows(monkeypatch):
    context = make_runtime_context()
    captured = {}

    def fake_call(command, cwd=None, shell=False, env=None):
        captured['command'] = command
        captured['cwd'] = cwd
        captured['shell'] = shell
        captured['env'] = env
        return 0

    monkeypatch.setattr(golem_context.subprocess, 'call', fake_call)

    result = context.run_command(['git', 'status'], cwd='C:/tmp/project', env={'GOLEM_FLAG': '1'})

    assert result is None
    assert captured['command'] == ['git', 'status']
    assert captured['cwd'] == 'C:/tmp/project'
    assert captured['shell'] is False
    assert captured['env']['GOLEM_FLAG'] == '1'


def test_run_command_with_msvisualcpp_uses_cmd_wrapper_without_shell(monkeypatch):
    context = make_runtime_context()
    context.context.env = AttrDict(MSVC_TARGETS=['x64'])
    captured = {}

    monkeypatch.setattr(context, 'vswhere_get_installation_path', lambda: 'C:\\VS Path')

    def fake_call(command, cwd=None, shell=False, env=None):
        captured['command'] = command
        captured['cwd'] = cwd
        captured['shell'] = shell
        return 0

    monkeypatch.setattr(golem_context.subprocess, 'call', fake_call)

    result = context.run_command_with_msvisualcpp(['cl.exe', '/nologo'], cwd='C:/tmp/project')

    assert result is None
    assert captured['command'][:4] == ['cmd', '/d', '/s', '/c']
    assert captured['cwd'] == 'C:/tmp/project'
    assert captured['shell'] is False
    assert captured['command'][4].startswith('call "C:\\VS Path\\VC\\Auxiliary\\Build\\vcvarsall.bat" x64')
    assert '&& cl.exe /nologo' in captured['command'][4]


def test_clone_repository_copies_non_git_directory(tmp_path):
    project_dir = tmp_path / 'project'
    project_dir.mkdir()
    source_dir = project_dir / 'recipes'
    source_dir.mkdir()
    (source_dir / 'marker.txt').write_text('copied\n', encoding='utf-8')
    repo_path = tmp_path / 'cache' / 'recipes'

    context = make_repository_context(project_dir=project_dir)
    repository = Source.parse('recipes', str(project_dir))

    context.clone_repository(path=str(repo_path), source=repository)

    assert (repo_path / 'marker.txt').read_text(encoding='utf-8') == 'copied\n'
    assert (repo_path / '.golem-origin').read_text(encoding='utf-8') == repository.location


def test_clone_repository_recopies_non_git_directory_when_cache_exists(tmp_path):
    project_dir = tmp_path / 'project'
    project_dir.mkdir()
    source_dir = project_dir / 'recipes'
    source_dir.mkdir()
    (source_dir / 'marker.txt').write_text('fresh\n', encoding='utf-8')
    repo_path = tmp_path / 'cache' / 'recipes'
    repo_path.mkdir(parents=True)
    (repo_path / 'marker.txt').write_text('stale\n', encoding='utf-8')

    context = make_repository_context(project_dir=project_dir)
    repository = Source.parse('recipes', str(project_dir))

    context.clone_repository(path=str(repo_path), source=repository)

    assert (repo_path / 'marker.txt').read_text(encoding='utf-8') == 'fresh\n'


def test_clone_repository_raises_for_missing_local_directory(tmp_path):
    context = make_repository_context(project_dir=tmp_path)
    repository = Source.parse('missing-recipes', str(tmp_path))
    repo_path = tmp_path / 'cache' / 'recipes'

    with pytest.raises(RuntimeError, match="Can't find local source directory"):
        context.clone_repository(path=str(repo_path), source=repository)


def test_clone_repository_uses_git_for_local_git_directory(monkeypatch, tmp_path):
    project_dir = tmp_path / 'project'
    project_dir.mkdir()
    source_dir = project_dir / 'recipes'
    git_dir = source_dir / '.git'
    git_dir.mkdir(parents=True)
    (git_dir / 'HEAD').write_text('ref: refs/heads/main\n', encoding='utf-8')
    repo_path = tmp_path / 'cache' / 'recipes'

    context = make_repository_context(project_dir=project_dir)
    repository = Source.parse('recipes', str(project_dir))
    calls = []

    monkeypatch.setattr(helpers, 'run_git', lambda args, cwd=None, stdout=None: calls.append((args, cwd)))

    context.clone_repository(path=str(repo_path), source=repository)

    assert calls[0] == (['clone', '--', repository.location, '.'], str(repo_path))
    assert calls[1] == (['reset', '--hard', 'origin/main'], str(repo_path))


# -- overlays: several overrides.json layered in the order they are configured --


def make_overlay(tmp_path, name, entries):
    overlay_dir = tmp_path / name
    overlay_dir.mkdir(parents=True)
    (overlay_dir / 'overrides.json').write_text(json.dumps(entries), encoding='utf-8')
    return overlay_dir


def load_layered_overrides(monkeypatch, tmp_path, overlay_names):
    project_dir = tmp_path / 'project'
    project_dir.mkdir(exist_ok=True)
    context = make_repository_context(project_dir=project_dir, deps_resolve=False)
    context.resolved_overrides = ''

    monkeypatch.setenv('GOLEM_OVERLAYS_LOCATIONS', '|'.join(
        'directory+{}'.format(tmp_path / name) for name in overlay_names))
    monkeypatch.delenv('GOLEM_OVERRIDES_CONFIGURATION', raising=False)
    # An overlay is read where it was installed; here that is the directory itself.
    monkeypatch.setattr(context, 'install_overlay', lambda source: source.get_local_path())
    monkeypatch.setattr(context, 'make_build_path',
                        lambda path: str(tmp_path / 'build' / path))

    return context.load_overrides_configuration()


def test_a_later_overlay_overwrites_only_the_members_it_sets(monkeypatch, tmp_path):
    make_overlay(tmp_path, 'first', [
        {'repository': 'https://host/json.git', 'version': '^3.0.0', 'shallow': True}])
    make_overlay(tmp_path, 'second', [
        {'repository': 'https://host/json.git', 'version': '^4.0.0'}])

    overrides = load_layered_overrides(monkeypatch, tmp_path, ['first', 'second'])

    assert len(overrides) == 1
    assert overrides[0].version == '^4.0.0'
    # Untouched by the second overlay, so the first one still carries it.
    assert overrides[0].shallow is True


def test_layering_keeps_an_entry_only_one_overlay_defines(monkeypatch, tmp_path):
    make_overlay(tmp_path, 'first', [
        {'repository': 'https://host/json.git', 'version': '^3.0.0'}])
    make_overlay(tmp_path, 'second', [
        {'repository': 'https://host/fmt.git', 'version': '^10.0.0'}])

    overrides = load_layered_overrides(monkeypatch, tmp_path, ['first', 'second'])

    assert [override.repository for override in overrides] == \
        ['https://host/json.git', 'https://host/fmt.git']


def test_layering_identifies_an_entry_by_the_source_it_overrides(monkeypatch, tmp_path):
    lib_dir = tmp_path / 'project' / 'mylib'
    lib_dir.mkdir(parents=True)
    make_overlay(tmp_path, 'first', [{'directory': 'mylib', 'variant': 'debug'}])
    make_overlay(tmp_path, 'second', [{'location': 'mylib', 'variant': 'release'}])

    overrides = load_layered_overrides(monkeypatch, tmp_path, ['first', 'second'])

    assert len(overrides) == 1
    assert overrides[0].directory == lib_dir.resolve().as_uri()
    assert overrides[0].variant == ['release']


def test_an_explicit_configuration_stands_in_for_the_overlays(monkeypatch, tmp_path):
    make_overlay(tmp_path, 'first', [
        {'repository': 'https://host/json.git', 'version': '^3.0.0'}])
    project_dir = tmp_path / 'project'
    project_dir.mkdir()
    (project_dir / 'explicit.json').write_text(
        json.dumps([{'repository': 'https://host/fmt.git', 'version': '^10.0.0'}]),
        encoding='utf-8')

    context = make_repository_context(project_dir=project_dir, deps_resolve=False)
    context.resolved_overrides = ''
    monkeypatch.setenv('GOLEM_OVERLAYS_LOCATIONS',
                       'directory+{}'.format(tmp_path / 'first'))
    monkeypatch.setenv('GOLEM_OVERRIDES_CONFIGURATION', 'explicit.json')

    overrides = context.load_overrides_configuration()

    assert [override.repository for override in overrides] == ['https://host/fmt.git']


def test_make_basic_dependency_repo_path_uses_repository_base_with_branch(tmp_path):
    context = make_repository_context(project_dir=tmp_path)
    context.cache_configuration = make_cache_configuration(
        CacheDirectory('/cache', is_read_only=False), minimization_enabled=False)

    repository = Source.for_repository(location='https://github.com/GolemCpp/recipes.git')

    manager = get_cookbook_manager(context.cache_configuration)
    repo_path = manager.resolve_cached_resource(repository).path

    assert repo_path == os.path.join('/cache', COOKBOOKS_SUBDIR, Source.make_repository_base(
        'https://github.com/GolemCpp/recipes.git', 'main')
    )


def test_cache_minimization_length_and_toggle_resolution(tmp_path):
    options = SimpleNamespace(
        cache_minimization_enabled='', cache_minimization_length=0)
    settings = get_settings(
        options=options, project_dir=str(tmp_path))

    # Defaults: enabled, length 8.
    assert settings.get('GOLEM_CACHE_MINIMIZATION_ENABLED') is True
    assert settings.get('GOLEM_CACHE_MINIMIZATION_LENGTH') == 8

    options.cache_minimization_length = 16
    assert settings.get('GOLEM_CACHE_MINIMIZATION_LENGTH') == 16

    options.cache_minimization_enabled = 'off'
    assert settings.get('GOLEM_CACHE_MINIMIZATION_ENABLED') is False


def test_make_dependency_path_uses_shared_resource_location(tmp_path):
    context = make_repository_context(project_dir=tmp_path)
    cache_dir = CacheDirectory(str(tmp_path / 'cache'), is_read_only=False)
    context.cache_configuration = make_cache_configuration(cache_dir)

    dep = Dependency(
        repository='https://github.com/nlohmann/json.git',
        version='^3.0.0')
    dep.resolved_hash = '1234567890abcdef'
    # Primed the way configure does, so the path comes from that resolution.
    dep.update_cached_resource(context.cache_configuration)

    assert context.make_dependency_path(dep, 'artifact') == os.path.join(
        get_dependency_manager(
            context.cache_configuration).resolve_cached_resource(dep).path,
        'artifact')


def test_dependency_resolves_its_cached_resource_on_first_use(tmp_path):
    # A dependency restored from a dependencies.json comes back without a cached
    # resource: it resolves its own on first use rather than needing a caller to
    # prime it.
    context = make_repository_context(project_dir=tmp_path)
    cache_dir = CacheDirectory(str(tmp_path / 'cache'), is_read_only=False)
    context.cache_configuration = make_cache_configuration(cache_dir)

    dep = Dependency.unserialize_from_json({
        'name': 'json',
        'repository': 'https://github.com/nlohmann/json.git',
        'resolved_version': '3.11.3',
        'resolved_hash': '1234567890abcdef',
    })
    assert dep.cached_resource is None

    location = context.get_dep_location(dep)

    assert location == get_dependency_manager(
        context.cache_configuration).resolve_cached_resource(dep).path
    # Resolved once and kept: the same cached resource answers every later path.
    assert dep.cached_resource.path == location
    assert context.get_dep_cached_resource(dep) is dep.cached_resource


def test_resolved_reference_prefers_hash_prefix():
    assert helpers.resolved_reference('3.11.3', '1234567890abcdef') == '12345678'
    # Falls back to the resolved version name when there is no hash.
    assert helpers.resolved_reference('3.11.3', '') == '3.11.3'