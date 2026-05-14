import os
import pytest
from types import SimpleNamespace
import json

from golemcpp.golem import context as golem_context, helpers, qt_discovery
from golemcpp.golem.cache import CacheConf, CacheDir, CacheResolutionPolicy, CachedResourceResolver
from golemcpp.golem.context import Context
from golemcpp.golem.dependency import Dependency
from golemcpp.golem.repository import Repository


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
        ),
        want_qt6=False,
        env=SimpleNamespace(),
        setenv=lambda _: None,
        load=lambda _: None,
    )
    context.version = SimpleNamespace(force_version=lambda _: None)
    context.make_cache_conf = lambda: None
    context.load_recipe = lambda: None
    context.get_tasks_and_targets_to_process = lambda: []
    context.ensures_qt_is_installed = lambda: None
    context.configure_compiler = lambda: None
    context.save_options = lambda: None
    context.is_windows = lambda: False
    context.get_arch = lambda: 'x64'
    return context


def test_configure_autodiscovers_qtdir_when_qt_is_enabled_and_other_sources_are_missing(monkeypatch):
    context = make_configure_context()
    context.get_tasks_and_targets_to_process = lambda: [(SimpleNamespace(features=['QT6CORE'], wfeatures=[]), None)]

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
            SimpleNamespace(
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
    context.context = SimpleNamespace(
        options=SimpleNamespace(
            variant=variant,
            runtime_link=runtime_link,
            runtime_variant=runtime_variant,
            link=link,
            arch='x64',
            nounicode=False,
        ),
        env=SimpleNamespace(
            DEFINES=[],
            CXXFLAGS=[],
            CFLAGS=[],
            LINKFLAGS=[],
            ARFLAGS=[],
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
        ),
        env=AttrDict(
            DEFINES=['FROM_ENV'],
            CXXFLAGS=['/env-cxx'],
            CFLAGS=['/env-c'],
            LINKFLAGS=['/env-link'],
            ARFLAGS=[],
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
    context.resolved_master_dependencies = '/tmp/master-dependencies.json'
    context.get_dep_location = lambda dep, cache_dir: '/tmp/dep-export'
    context.make_repo_ready = lambda dep, cache_dir, should_clean=False: '/tmp/repo'
    context.get_dep_build_location = lambda dep, cache_dir: '/tmp/repo/build'
    context.get_global_dependencies_configuration_file = lambda: '/tmp/global-dependencies.json'
    context.make_cache_dir_option = lambda: '/tmp/cache'
    context.get_only_update_dependencies_regex = lambda: ''
    context.make_define_cache_directories_option = lambda: ''
    context.make_define_static_cache_directories_option = lambda: ''
    context.make_cache_resolution_policy_option = lambda: 'strict'

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

    context.run_dep_command(dep=dep, cache_dir='/tmp/cache', command='resolve')

    assert '--runtime-link=shared' in calls[0]
    assert '--runtime-variant=release' in calls[0]
    assert '--runtime=shared' not in calls[0]


def make_repository_context(project_dir, *, deps_resolve=True, no_recipes_repositories_fetch=False):
    context = Context.__new__(Context)
    context.project = SimpleNamespace(master_dependencies_repository=None)
    context.context = SimpleNamespace(
        options=SimpleNamespace(
            project_dir=str(project_dir),
            no_recipes_repositories_fetch=no_recipes_repositories_fetch,
            cache_resolution_policy='strict',
        ))
    context.deps_resolve = deps_resolve
    return context


def make_cache_conf(*cache_dirs):
    cache_conf = CacheConf()
    cache_conf.locations = list(cache_dirs)
    return cache_conf


def test_cached_resource_resolver_strict_policy_returns_first_match_without_probe():
    cache_conf = make_cache_conf(
        CacheDir('/static-regex', is_static=True, regex='.*recipes.*'),
        CacheDir('/writable', is_static=False),
    )

    resolver = CachedResourceResolver(
        identifier='https://github.com/GolemCpp/recipes.git',
        cache_conf=cache_conf,
        policy=CacheResolutionPolicy.WEAK,
    )

    assert resolver.resolve().location == '/static-regex'


def test_cached_resource_resolver_weak_policy_without_probe_returns_none_for_phase():
    cache_conf = make_cache_conf(
        CacheDir('/static-default', is_static=True),
        CacheDir('/writable-regex', is_static=False, regex='.*recipes.*'),
        CacheDir('/writable-default', is_static=False),
    )

    resolver = CachedResourceResolver(
        identifier='https://github.com/GolemCpp/recipes.git',
        cache_conf=cache_conf,
        policy=CacheResolutionPolicy.WEAK,
    )

    assert resolver._select_cache(cache_conf.locations) is None


def test_cached_resource_resolver_weak_policy_checks_existing_caches():
    static_missing = CacheDir('/static-missing', is_static=True, regex='.*json.*')
    static_present = CacheDir('/static-present', is_static=True, regex='.*json.*')
    cache_conf = make_cache_conf(static_missing, static_present)

    resolver = CachedResourceResolver(
        identifier='https://github.com/nlohmann/json.git',
        cache_conf=cache_conf,
        policy=CacheResolutionPolicy.WEAK,
        exists_in_cache=lambda cache_dir: cache_dir.location == '/static-present',
    )

    assert resolver.resolve().location == '/static-present'


def test_cached_resource_resolver_weak_policy_falls_back_to_first_writable_cache():
    writable_regex = CacheDir('/writable-regex', is_static=False, regex='.*json.*')
    writable_default = CacheDir('/writable-default', is_static=False)
    cache_conf = make_cache_conf(writable_regex, writable_default)

    resolver = CachedResourceResolver(
        identifier='https://github.com/nlohmann/json.git',
        cache_conf=cache_conf,
        policy=CacheResolutionPolicy.WEAK,
        exists_in_cache=lambda cache_dir: False,
    )

    assert resolver.resolve().location == '/writable-regex'


def test_find_repository_cache_dir_uses_repository_probe_under_weak_policy(tmp_path):
    context = make_repository_context(project_dir=tmp_path)
    context.context.options.cache_resolution_policy = 'weak'
    context.cache_conf = make_cache_conf(
        CacheDir('/static-regex', is_static=True, regex='.*recipes.*'),
        CacheDir('/writable-default', is_static=False),
    )

    context.is_resource_in_cache_dir = lambda resource, cache_dir: cache_dir.location == '/static-regex'

    repository = Repository(url='https://github.com/GolemCpp/recipes.git')

    cache_dir = context.find_repository_cache_dir(repository)

    assert cache_dir.location == '/static-regex'


def test_find_repository_cache_dir_weak_policy_skips_read_only_hit_when_probe_fails(tmp_path):
    context = make_repository_context(project_dir=tmp_path)
    context.context.options.cache_resolution_policy = 'weak'
    context.cache_conf = make_cache_conf(
        CacheDir('/static-regex', is_static=True, regex='.*recipes.*'),
        CacheDir('/writable-default', is_static=False),
    )

    context.is_resource_in_cache_dir = lambda resource, cache_dir: False

    repository = Repository(url='https://github.com/GolemCpp/recipes.git')

    cache_dir = context.find_repository_cache_dir(repository)

    assert cache_dir.location == '/static-regex'


def test_parse_local_non_git_repository_returns_local_path_for_non_git_directory(tmp_path):
    repository_dir = tmp_path / 'recipes'
    repository_dir.mkdir()

    dependency = Dependency(repository='file://' + str(repository_dir))

    assert Repository.parse_local_non_git_repository(dependency.repository) == str(repository_dir)


def test_parse_local_non_git_repository_ignores_local_git_directory(tmp_path):
    repository_dir = tmp_path / 'recipes'
    git_dir = repository_dir / '.git'
    git_dir.mkdir(parents=True)
    (git_dir / 'HEAD').write_text('ref: refs/heads/main\n', encoding='utf-8')

    dependency = Dependency(repository='file://' + str(repository_dir))

    assert Repository.parse_local_non_git_repository(dependency.repository) is None
    assert Repository.parse_local_directory_path(url=dependency.repository) == str(repository_dir)


def test_helpers_parse_local_non_git_repository_ignores_local_git_directory(tmp_path):
    repository_dir = tmp_path / 'recipes'
    git_dir = repository_dir / '.git'
    git_dir.mkdir(parents=True)
    (git_dir / 'HEAD').write_text('ref: refs/heads/main\n', encoding='utf-8')

    assert Repository.parse_local_non_git_repository('file://' + str(repository_dir)) is None
    assert Repository.parse_local_directory_path('file://' + str(repository_dir)) == str(repository_dir)


def test_load_recipes_repositories_normalizes_local_paths(monkeypatch, tmp_path):
    context = make_repository_context(project_dir=tmp_path)
    recipes_dir = tmp_path / 'recipes'
    recipes_dir.mkdir()

    monkeypatch.setenv('GOLEM_RECIPES_REPOSITORIES', 'recipes')

    repositories = context.load_recipes_repositories()

    assert [repository.url for repository in repositories] == ['file://' + str(recipes_dir)]


def test_get_master_dependencies_repository_normalizes_local_paths(monkeypatch, tmp_path):
    context = make_repository_context(project_dir=tmp_path)
    master_dir = tmp_path / 'master-dependencies'
    master_dir.mkdir()

    monkeypatch.setenv('GOLEM_MASTER_DEPENDENCIES_REPOSITORY', 'master-dependencies')

    assert context.get_master_dependencies_repository().url == 'file://' + str(master_dir)


def test_normalize_repository_url_percent_encodes_local_paths(tmp_path):
    project_dir = tmp_path / 'project dir'
    recipes_dir = project_dir / 'recipes #1?x'
    recipes_dir.mkdir(parents=True)

    repository = Repository.from_url('recipes #1?x', str(project_dir)).url

    assert repository == recipes_dir.resolve().as_uri()
    assert Repository.parse_local_directory_path(repository) == str(recipes_dir.resolve())


def test_clone_repository_copies_non_git_directory(tmp_path):
    project_dir = tmp_path / 'project'
    project_dir.mkdir()
    source_dir = project_dir / 'recipes'
    source_dir.mkdir()
    (source_dir / 'marker.txt').write_text('copied\n', encoding='utf-8')
    repo_path = tmp_path / 'cache' / 'recipes'

    context = make_repository_context(project_dir=project_dir)
    repository = Repository.from_url('recipes', str(project_dir))

    context.clone_repository(path=str(repo_path), repository=repository)

    assert (repo_path / 'marker.txt').read_text(encoding='utf-8') == 'copied\n'
    assert (repo_path / '.golem-origin').read_text(encoding='utf-8') == repository.url


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
    repository = Repository.from_url('recipes', str(project_dir))

    context.clone_repository(path=str(repo_path), repository=repository)

    assert (repo_path / 'marker.txt').read_text(encoding='utf-8') == 'fresh\n'


def test_clone_repository_raises_for_missing_local_directory(tmp_path):
    context = make_repository_context(project_dir=tmp_path)
    repository = Repository.from_url('missing-recipes', str(tmp_path))
    repo_path = tmp_path / 'cache' / 'recipes'

    with pytest.raises(RuntimeError, match="Can't find local repository directory"):
        context.clone_repository(path=str(repo_path), repository=repository)


def test_clone_repository_uses_git_for_local_git_directory(monkeypatch, tmp_path):
    project_dir = tmp_path / 'project'
    project_dir.mkdir()
    source_dir = project_dir / 'recipes'
    git_dir = source_dir / '.git'
    git_dir.mkdir(parents=True)
    (git_dir / 'HEAD').write_text('ref: refs/heads/main\n', encoding='utf-8')
    repo_path = tmp_path / 'cache' / 'recipes'

    context = make_repository_context(project_dir=project_dir)
    repository = Repository.from_url('recipes', str(project_dir))
    calls = []

    monkeypatch.setattr(helpers, 'run_git', lambda args, cwd=None, stdout=None: calls.append((args, cwd)))

    context.clone_repository(path=str(repo_path), repository=repository)

    assert calls[0] == (['clone', '--', repository.url, '.'], str(repo_path))
    assert calls[1] == (['reset', '--hard', 'origin/main'], str(repo_path))


def test_make_basic_dependency_repo_path_uses_repository_base_with_branch(tmp_path):
    context = make_repository_context(project_dir=tmp_path)
    context.cache_conf = make_cache_conf(CacheDir('/cache', is_static=False))
    context.find_repository_cache_dir = lambda repository: CacheDir('/cache', is_static=False)

    repository = Repository(url='https://github.com/GolemCpp/recipes.git')

    repo_path = context.make_basic_dependency_repo_path(repository)

    assert repo_path == '/cache/' + Repository.make_repository_base(
        'https://github.com/GolemCpp/recipes.git', 'main')


def test_get_resource_location_reuses_repository_cache_key_for_dependency(tmp_path):
    context = make_repository_context(project_dir=tmp_path)
    cache_dir = CacheDir(str(tmp_path / 'cache'), is_static=False)

    dep = Dependency(
        repository='https://github.com/nlohmann/json.git',
        version='^3.0.0')
    dep.resolved_hash = '1234567890abcdef'

    expected_repository = Repository(
        url=dep.repository,
        reference=helpers.get_dependency_resolved_version(dep))

    assert context.get_resource_location(dep, cache_dir) == os.path.join(
        cache_dir.location, expected_repository.get_cache_key())


def test_is_resource_in_cache_dir_uses_dependency_base(tmp_path):
    context = make_repository_context(project_dir=tmp_path)
    cache_dir = CacheDir(str(tmp_path / 'cache'), is_static=False)
    os.makedirs(cache_dir.location, exist_ok=True)

    dep = Dependency(
        repository='https://github.com/nlohmann/json.git',
        version='^3.0.0')
    dep.resolved_hash = '1234567890abcdef'

    resource_path = context.get_resource_location(dep, cache_dir)
    os.makedirs(resource_path, exist_ok=True)

    assert context.is_resource_in_cache_dir(dep, cache_dir) is True


def test_make_dependency_path_uses_shared_resource_location(tmp_path):
    context = make_repository_context(project_dir=tmp_path)
    cache_dir = CacheDir(str(tmp_path / 'cache'), is_static=False)

    dep = Dependency(
        repository='https://github.com/nlohmann/json.git',
        version='^3.0.0')
    dep.resolved_hash = '1234567890abcdef'
    dep.cache_dir = cache_dir

    assert context.make_dependency_path(dep, 'artifact') == os.path.join(
        context.get_resource_location(dep, cache_dir), 'artifact')


def test_get_dependency_resolved_version_prefers_hash_prefix():
    dep = Dependency(
        repository='https://github.com/nlohmann/json.git',
        version='^3.0.0')
    dep.resolved_version = '3.11.3'
    dep.resolved_hash = '1234567890abcdef'

    assert helpers.get_dependency_resolved_version(dep) == '12345678'


def test_is_resource_in_cache_dir_uses_repository_base(tmp_path):
    context = make_repository_context(project_dir=tmp_path)
    cache_dir = CacheDir(str(tmp_path / 'cache'), is_static=False)
    os.makedirs(cache_dir.location, exist_ok=True)

    repository = Repository(url='https://github.com/GolemCpp/recipes.git')
    resource_path = context.get_resource_location(repository, cache_dir)
    os.makedirs(resource_path, exist_ok=True)

    assert context.is_resource_in_cache_dir(repository, cache_dir) is True