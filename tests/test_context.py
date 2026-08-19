import os
import pytest
from types import SimpleNamespace
import json

from waflib import Logs

from golemcpp.golem.resource_manager import ResourceManager
from golemcpp.golem.resolved_version import ResolvedVersion
from golemcpp.golem import (context as golem_context, helpers, network,
                            qt_discovery, target_platform)
from golemcpp.golem.settings import get_settings
from golemcpp.golem.cache_configuration import (
    CacheConfiguration, DEPENDENCIES_SUBDIR, COOKBOOKS_SUBDIR)
from golemcpp.golem.cache_resolution_policy import CacheResolutionPolicy
from golemcpp.golem.cache_directory import CacheDirectory
from golemcpp.golem.context import Context
from golemcpp.golem.dependency import Dependency
from golemcpp.golem.dependency_manager import get_dependency_manager
from golemcpp.golem.cookbook_manager import get_cookbook_manager
from golemcpp.golem.requested_source import RequestedSource
from golemcpp.golem.requested_source import detect_kind
from golemcpp.golem.locator import Locator
from golemcpp.golem.source import Source
from golemcpp.golem.resource_manager import make_revision_component
from golemcpp.golem.dependency_manager import DependencyManager
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
            arch=None,  # unset, as it now is unless asked for
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
    # These tests stub the compiler load out entirely, so nothing can be asked
    # for a triple; the answer stands in for one.
    context.compiler_target = lambda: target_platform.CompilerTarget(arch='x86_64')
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


UNSET = object()


def make_runtime_context(*,
                         variant='debug',
                         runtime_link='shared',
                         runtime_variant=None,
                         link='shared',
                         arch='x86_64',
                         requested=UNSET):
    '''
    A context for a build that has already been configured.

    `arch` is the resolved identity, i.e. what the compiler turned out to build
    for. `requested` is what was asked on the command line, which defaults to
    the same thing; pass None for a build where nothing was asked, since that
    is a different case and only a request may emit selecting flags.
    '''
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
            arch=arch if requested is UNSET else requested,
            resolved_arch=arch,
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
            DEST_CPU='',
            CXX=['g++'],
        ),
    )
    context.is_windows = lambda: True
    # get_arch is deliberately not stubbed: it reads options.arch through the
    # target, which is the path under test. osname still is, because the target
    # takes its OS from the host and these cases are about Windows.
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


@pytest.mark.parametrize('arch, expected', [('x86_64', '-m64'), ('i686', '-m32'),
                                            ('amd64', '-m64'), ('x86', '-m32')])
def test_gnu_word_size_flag_reaches_the_linker_too(arch, expected):
    # waf's link rule expands LINKFLAGS and never CXXFLAGS, so a word-size flag
    # given only to the compiler produces objects the link step cannot use.
    # The aliases are here too: how the flag was spelled must not change what
    # is emitted.
    context = make_runtime_context(arch=arch)
    context.is_msvc_like = lambda: False

    flags = context.make_default_build_flags(variant='release')

    assert expected in flags['cflags']
    assert expected in flags['cxxflags']
    assert expected in flags['linkflags']


def test_gnu_word_size_flag_is_omitted_for_an_arch_with_no_capability():
    context = make_runtime_context(arch='aarch64')
    context.is_msvc_like = lambda: False

    flags = context.make_default_build_flags(variant='release')

    assert not [f for f in flags['linkflags'] if f.startswith('-m')]


def test_msvc_machine_flag_comes_from_the_capability_table():
    context = make_runtime_context(arch='i686')

    flags = context.make_default_build_flags(variant='release')

    assert '/MACHINE:X86' in flags['linkflags']
    assert '/MACHINE:X86' in flags['arflags']


def test_arch_aliases_resolve_to_one_canonical_name():
    assert make_runtime_context(arch='amd64').get_arch() == 'x86_64'
    assert make_runtime_context(arch='x64').get_arch() == 'x86_64'
    assert make_runtime_context(arch='X86_64').get_arch() == 'x86_64'
    assert make_runtime_context(arch='arm64').get_arch() == 'aarch64'
    # A family name, not an alias: 'x86' names a family and resolves to its
    # conventional member rather than being a spelling of it.
    assert make_runtime_context(arch='x86').get_arch() == 'i686'


def test_unknown_arch_keeps_an_identity_and_gains_no_flags():
    context = make_runtime_context(arch='sparc64')
    context.is_msvc_like = lambda: False

    assert context.get_arch() == 'sparc64'
    assert context.make_default_build_flags(variant='release')['linkflags'] == []


@pytest.mark.parametrize('arch, expected', [
    ('x86_64', 'x64'),
    ('amd64', 'x64'),
    # The whole point: neither MSBuild nor CMake accepts 'x86', which is what
    # both were handed before.
    ('i686', 'Win32'),
    ('x86', 'Win32'),
    ('aarch64', 'ARM64'),
    ('arm64', 'ARM64'),
])
def test_vs_platform_uses_visual_studios_own_names(arch, expected):
    assert make_runtime_context(arch=arch).vs_platform() == expected


@pytest.mark.parametrize('arch, msvc_target, vcvars', [
    # waf's all_msvc_platforms pairs these, and they differ for x86_64.
    ('x86_64', 'x64', 'amd64'),
    ('i686', 'x86', 'x86'),
    ('aarch64', 'arm64', 'arm64'),
])
def test_the_two_msvc_vocabularies_stay_apart(arch, msvc_target, vcvars):
    context = make_runtime_context(arch=arch)

    assert context.arch_capability().msvc_target == msvc_target
    assert context.vcvars_arg() == vcvars


def test_vcvars_arg_refuses_an_arch_msvc_cannot_build():
    context = make_runtime_context(arch='armv7-eabihf')

    with pytest.raises(RuntimeError, match=r"No vcvarsall argument"):
        context.vcvars_arg()


def test_configure_default_leaves_msvc_targets_to_waf():
    context = make_runtime_context(arch='x86_64')
    context.context.env.MSVC_TARGETS = ['x64']

    context.configure_default()

    # The configure-time value survives: overwriting it here with the
    # vcvarsall spelling is what used to leave waf a value it would not match.
    assert context.context.env.MSVC_TARGETS == ['x64']


def test_vs_platform_takes_an_explicit_arch_over_the_target():
    context = make_runtime_context(arch='x86_64')

    assert context.vs_platform('i686') == 'Win32'


@pytest.mark.parametrize('arch', ['i486', 'armv7-eabihf', 'sparc64'])
def test_vs_platform_refuses_an_arch_visual_studio_cannot_build(arch):
    context = make_runtime_context(arch=arch)

    with pytest.raises(RuntimeError, match=r"No Visual Studio platform"):
        context.vs_platform()


def test_the_target_is_unavailable_until_a_compiler_has_answered():
    context = make_runtime_context()
    del context.context.options.resolved_arch

    with pytest.raises(RuntimeError, match=r"not resolved yet"):
        context.target()


def test_selecting_flags_do_not_need_a_resolved_target():
    # The one thing that runs before resolution is the MSVC_TARGETS write, and
    # it asks what was *requested*, never what the build turned out to be. If
    # this ever needed the target it would be reading a provisional value.
    context = make_runtime_context(arch='i686')
    del context.context.options.resolved_arch

    assert context.selecting_capability().msvc_target == 'x86'


def test_msvc_is_asked_what_it_targets_rather_than_assumed():
    # A Visual Studio installation need not include tools for the machine it
    # runs on, so the host is not an answer here. waf records the target of the
    # installation it detected.
    context = make_runtime_context()
    context.context.env.DEST_CPU = 'arm64'

    assert context.compiler_target().arch == 'aarch64'


def test_resolution_refuses_to_name_an_architecture_nobody_established():
    context = make_runtime_context(arch=None, requested=None)
    context.compiler_target = lambda: target_platform.CompilerTarget()

    with pytest.raises(RuntimeError, match=r"Cannot tell what architecture"):
        context.resolve_target_arch()


def test_an_absent_request_emits_no_selecting_flags():
    # The identity is still x86_64 and still names the artifact; what is absent
    # is any flag instructing the compiler, because nothing was asked for.
    context = make_runtime_context(arch='x86_64', requested=None)
    context.is_msvc_like = lambda: False

    flags = context.make_default_build_flags(variant='release')

    assert context.get_arch() == 'x86_64'
    assert '-m64' not in flags['cxxflags']
    assert '-m64' not in flags['linkflags']


def test_an_explicit_request_emits_them():
    context = make_runtime_context(arch='x86_64')
    context.is_msvc_like = lambda: False

    flags = context.make_default_build_flags(variant='release')

    assert '-m64' in flags['cxxflags']
    assert '-m64' in flags['linkflags']


def test_resolution_takes_the_compilers_answer_when_nothing_was_asked():
    context = make_runtime_context(arch=None)
    context.compiler_target = lambda: target_platform.CompilerTarget(arch='armv7-eabihf')

    context.resolve_target_arch()

    assert context.get_arch() == 'armv7-eabihf'


def test_resolution_accepts_a_request_the_compiler_agrees_with():
    context = make_runtime_context(arch='amd64')
    context.compiler_target = lambda: target_platform.CompilerTarget(arch='x86_64')

    context.resolve_target_arch()

    # Spelled 'amd64', resolved to the canonical name, and no disagreement.
    assert context.get_arch() == 'x86_64'


def test_resolution_rejects_a_request_the_compiler_contradicts():
    context = make_runtime_context(arch='aarch64')
    context.context.env.CXX = ['g++']
    context.compiler_target = lambda: target_platform.CompilerTarget(arch='x86_64')

    with pytest.raises(RuntimeError, match=r"Requested architecture 'aarch64'"):
        context.resolve_target_arch()


def make_gnu_context(*, arch, triple, builds=False):
    '''
    A configured context whose compiler reports `triple` and is not MSVC.

    `builds` is what the compiler answers when asked to build with selecting
    flags, which is the only way a multilib target can be confirmed.
    '''
    context = make_runtime_context(arch=arch)
    context.is_msvc_like = lambda: False
    context.compiler_target = lambda: target_platform.CompilerTarget.from_triple(
        triple, 'x86_64')
    context.attempted = []
    context.compiler_builds_with = lambda flags: (
        context.attempted.append(flags) or builds)
    return context


@pytest.mark.parametrize('arch, expected', [
    ('i686', 'x86'),
    ('x86', 'x86'),
    ('x86_64', 'x64'),
    ('aarch64', 'arm64'),
])
def test_an_explicit_arch_narrows_the_msvc_search(arch, expected):
    # configure() writes this into MSVC_TARGETS before context.load(), which
    # is how a request reaches waf's msvc detection rather than only the
    # flags. waf itself fails when no installation carries those tools.
    context = make_runtime_context(arch=arch)

    assert context.selecting_capability().msvc_target == expected


def test_an_absent_arch_leaves_the_msvc_search_alone():
    # Nothing was asked, so waf tries every platform it knows and reports what
    # it found. Naming one here would turn an observation into an instruction.
    context = make_runtime_context(arch='x86_64', requested=None)

    assert context.selecting_capability().msvc_target == ''


def test_a_multilib_compiler_reaches_a_target_its_triple_never_names():
    # gcc reports the target it was configured for, not the only one it can
    # build: `gcc -m32 -dumpmachine` still answers x86_64. Comparing triples
    # alone would refuse every 32-bit build on a 64-bit host.
    context = make_gnu_context(arch='i686', triple='x86_64-linux-gnu',
                               builds=True)

    context.resolve_target_arch()

    assert context.get_arch() == 'i686'
    assert context.attempted == [['-m32']]


def test_a_multilib_target_the_compiler_cannot_actually_build_is_refused():
    # The flag exists but the platform ships no 32-bit userland, so nothing
    # links. Asking is what tells them apart.
    context = make_gnu_context(arch='i686', triple='x86_64-linux-gnu',
                               builds=False)

    with pytest.raises(RuntimeError, match=r'-m32'):
        context.resolve_target_arch()


def test_a_target_no_flag_reaches_is_refused_without_asking():
    # No -m flag turns an x86_64 compiler into an ARM one, and the capability
    # table says so by carrying no flags at all. Nothing to try.
    context = make_gnu_context(arch='aarch64', triple='x86_64-linux-gnu',
                               builds=True)

    with pytest.raises(RuntimeError, match=r"builds for 'x86_64'"):
        context.resolve_target_arch()

    assert context.attempted == []


def test_a_ruled_out_family_is_not_a_multilib_question():
    # The triple named no target, so there is nothing for a flag to reach
    # from. -m64 must not be tried, nor claimed to have been.
    context = make_gnu_context(arch='x86_64', triple='arm-linux-gnueabihf')

    with pytest.raises(RuntimeError, match=r"'arm' family") as raised:
        context.resolve_target_arch()

    assert context.attempted == []
    assert '-m64' not in str(raised.value)


def test_a_request_supplies_the_isa_level_a_cross_triple_cannot():
    # arm-linux-gnueabihf on an x86_64 host: the compiler cannot say whether it
    # means armv6 or armv7, because only uname knows and uname is describing
    # the host. The request is allowed to settle exactly that.
    context = make_runtime_context(arch='armv7-eabihf')
    context.is_msvc_like = lambda: False
    context.compiler_target = lambda: target_platform.CompilerTarget.from_triple(
        'arm-linux-gnueabihf', 'x86_64')

    context.resolve_target_arch()

    assert context.get_arch() == 'armv7-eabihf'


def test_a_request_may_not_contradict_the_abi_the_triple_did_report():
    # The triple could not name a target but was emphatic about hard float.
    # Accepting armv7-eabi here would cache an artifact that links with nothing.
    context = make_runtime_context(arch='armv7-eabi')
    context.is_msvc_like = lambda: False
    context.compiler_target = lambda: target_platform.CompilerTarget.from_triple(
        'arm-linux-gnueabihf', 'x86_64')

    with pytest.raises(RuntimeError, match=r"'eabihf' ABI"):
        context.resolve_target_arch()


@pytest.mark.parametrize('arch', ['aarch64', 'x86_64'])
def test_a_request_may_not_contradict_the_family_either(arch):
    context = make_runtime_context(arch=arch)
    context.is_msvc_like = lambda: False
    context.compiler_target = lambda: target_platform.CompilerTarget.from_triple(
        'arm-linux-gnueabihf', 'x86_64')

    with pytest.raises(RuntimeError, match=r"'arm' family"):
        context.resolve_target_arch()


def test_a_silent_compiler_is_still_asked_to_build_where_a_flag_can_ask(
        monkeypatch):
    # It reported no target, but the request is one Golem has a flag for, so
    # there is a check available and taking it on trust would be a choice.
    warnings = []
    monkeypatch.setattr(Logs, 'warn', lambda message, *args: warnings.append(
        message))
    context = make_runtime_context(arch='i686')
    context.is_msvc_like = lambda: False
    context.compiler_target = lambda: target_platform.CompilerTarget()
    context.attempted = []
    context.compiler_builds_with = lambda flags: (
        context.attempted.append(flags) or True)

    context.resolve_target_arch()

    assert context.get_arch() == 'i686'
    assert context.attempted == [['-m32']]
    # Confirmed rather than trusted, so there is nothing to warn about.
    assert warnings == []


def test_a_silent_compiler_that_cannot_build_the_request_is_an_error():
    # Nothing supports the request: no target reported, and the one check
    # available failed. Naming the artifact anyway would be a plain lie.
    context = make_runtime_context(arch='i686')
    context.is_msvc_like = lambda: False
    context.compiler_target = lambda: target_platform.CompilerTarget()
    context.compiler_builds_with = lambda flags: False

    with pytest.raises(RuntimeError, match=r'no target of its own'):
        context.resolve_target_arch()


def test_a_compiler_that_answered_nothing_constrains_nothing(monkeypatch):
    # An MSVC-like toolchain that reported nothing, which is waf's
    # no_autodetect(): it returns before writing DEST_CPU. No flag can put the
    # question to cl.exe either, so nothing checks the request and it is taken
    # on trust. The other silent case is a toolchain with no -dumpmachine.
    warnings = []
    monkeypatch.setattr(Logs, 'warn', lambda message, *args: warnings.append(
        message))
    context = make_runtime_context(arch='i686')
    context.compiler_target = lambda: target_platform.CompilerTarget()

    context.resolve_target_arch()

    assert context.get_arch() == 'i686'
    # Taken on trust, and said so: an unchecked request names the artifact, so
    # a wrong one is cached under a wrong name rather than failing to build.
    assert len(warnings) == 1
    assert "'i686' on request alone" in warnings[0]


def test_a_compiler_that_did_answer_is_not_second_guessed(monkeypatch):
    # The warning is about nothing having checked the request, so a compiler
    # that agreed must not produce it.
    warnings = []
    monkeypatch.setattr(Logs, 'warn', lambda message, *args: warnings.append(
        message))
    context = make_runtime_context(arch='x86_64')
    context.compiler_target = lambda: target_platform.CompilerTarget(
        arch='x86_64')

    context.resolve_target_arch()

    assert warnings == []


def test_a_coarse_answer_counts_as_an_answer(monkeypatch):
    # The triple could not name a target, but it did rule things out, so the
    # request was held to something and is not being taken on trust.
    warnings = []
    monkeypatch.setattr(Logs, 'warn', lambda message, *args: warnings.append(
        message))
    context = make_runtime_context(arch='armv7-eabihf')
    context.is_msvc_like = lambda: False
    context.compiler_target = lambda: target_platform.CompilerTarget.from_triple(
        'arm-linux-gnueabihf', 'x86_64')

    context.resolve_target_arch()

    assert context.get_arch() == 'armv7-eabihf'
    assert warnings == []


def test_restore_normalizes_both_the_request_and_the_resolved_identity():
    context = make_runtime_context()
    context.context.env = SimpleNamespace(
        OPTIONS=json.dumps({
            'arch': 'x64',
            'resolved_arch': 'amd64',
            'targets': '',
            'only_update_dependencies_regex': '',
            'output_file': '',
        }))
    context.context.options.targets = ''
    context.context.options.output_file = ''
    context.context.options.only_update_dependencies_regex = ''

    restored = context.restore_options_env(context.context.env)

    assert restored['arch'] == 'x86_64'
    assert restored['resolved_arch'] == 'x86_64'


def test_an_env_with_no_resolved_identity_is_not_given_one():
    # An env saved before resolution existed gets no invented value: reading
    # the target raises and asks for a reconfigure, rather than a guessed
    # architecture reaching a build slug.
    context = make_runtime_context()
    context.context.env = SimpleNamespace(
        OPTIONS=json.dumps({
            'arch': 'x64',
            'targets': '',
            'only_update_dependencies_regex': '',
            'output_file': '',
        }))
    context.context.options.targets = ''
    context.context.options.output_file = ''
    context.context.options.only_update_dependencies_regex = ''

    restored = context.restore_options_env(context.context.env)

    assert 'resolved_arch' not in restored


def test_debian_arch_comes_from_the_capability_table():
    assert make_runtime_context(arch='x86_64').get_arch_for_linux() == 'amd64'
    assert make_runtime_context(arch='aarch64').get_arch_for_linux() == 'arm64'
    assert make_runtime_context(arch='sparc64').get_arch_for_linux() is None


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
            arch='x86_64',
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
            DEST_CPU='',
            CXX=['g++'],
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
    context.is_msvc_like = lambda: True
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


def stub_dependency_manager(monkeypatch, context, *, is_read_only=False,
                            cache_root='/tmp/cache', source_path='/tmp/repo',
                            installs=None):
    '''Stands in for the real manager, so a fake dep needs no cache to resolve in.'''
    context.cache_configuration = None
    cached_dep = SimpleNamespace(is_read_only=is_read_only, cache_root=cache_root)

    def install(dep, refresh=True, cached_resource=None):
        if installs is not None:
            installs.append(refresh)
        return SimpleNamespace(source_path=source_path)

    monkeypatch.setattr(
        golem_context, 'get_dependency_manager',
        lambda cache_configuration: SimpleNamespace(
            get_cached_resource=lambda dep: cached_dep,
            install=install))


def test_run_dep_command_forwards_runtime_link_and_runtime_variant(monkeypatch):
    context = make_runtime_context(runtime_variant='release')
    context.resolved_overrides = '/tmp/overrides.json'
    context.get_dep_location = lambda dep: '/tmp/dep-export'
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
        resolved=ResolvedVersion(reference='1.0.0', revision='cafebabe'),
    )

    calls = []

    monkeypatch.setattr(golem_context.Logs, 'info', lambda *args, **kwargs: None)
    monkeypatch.setattr(helpers, 'make_golem_command', lambda command: [command])
    monkeypatch.setattr(helpers, 'run_task', lambda args, cwd=None, stdout=None: calls.append(args))
    stub_dependency_manager(monkeypatch, context)

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


def test_run_dep_command_refuses_a_read_only_cache_location(monkeypatch):
    # The command builds into the dependency's cache root, so a location that
    # forbids writing is refused before anything runs.
    context = make_runtime_context(runtime_variant='release')
    monkeypatch.setattr(golem_context.Logs, 'info', lambda *args, **kwargs: None)
    monkeypatch.setattr(
        helpers, 'run_task',
        lambda *args, **kwargs: pytest.fail('ran a command from a read-only cache'))
    stub_dependency_manager(
        monkeypatch, context, is_read_only=True, cache_root='/shared/cache')

    with pytest.raises(RuntimeError, match='read-only cache location /shared/cache'):
        context.run_dep_command(
            dep=SimpleNamespace(name='demo', version='1.0.0'), command='build')


def test_run_dep_command_refreshes_the_repository_only_when_building(monkeypatch):
    # Building dirties the dependency's working tree, so its source is cleaned and
    # reset first; resolving reads what is already there.
    monkeypatch.setattr(golem_context.Logs, 'info', lambda *args, **kwargs: None)
    monkeypatch.setattr(helpers, 'make_golem_command', lambda command: [command])
    monkeypatch.setattr(helpers, 'run_task', lambda args, cwd=None, stdout=None: None)

    refreshed = []
    for command in ('resolve', 'build'):
        context = make_runtime_context(runtime_variant='release')
        context.resolved_overrides = '/tmp/overrides.json'
        context.get_dep_location = lambda dep: '/tmp/dep-export'
        context.get_dep_build_location = lambda dep: '/tmp/repo/build'
        context.get_global_dependencies_configuration_file = lambda: '/tmp/global.json'
        context.get_only_update_dependencies_regex = lambda: ''
        context.settings = get_settings(
            project_dir=absolute_path('tmp', 'project'),
            options=SimpleNamespace(cache_directory=absolute_path('tmp', 'cache')))
        stub_dependency_manager(monkeypatch, context, installs=refreshed)

        context.run_dep_command(
            dep=SimpleNamespace(
                name='demo', version='1.0.0', runtime_link=None, runtime_variant=None,
                link=None, variant=None, shallow=False,
                resolved=ResolvedVersion(reference='1.0.0', revision='cafebabe')),
            command=command)

    assert refreshed == [False, True]


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
    assert detect_kind(Locator(dependency.directory)) == 'directory'


def test_detect_ignores_local_git_directory(tmp_path):
    repository_dir = tmp_path / 'recipes'
    git_dir = repository_dir / '.git'
    git_dir.mkdir(parents=True)
    (git_dir / 'HEAD').write_text('ref: refs/heads/main\n', encoding='utf-8')

    dependency = Dependency(repository=repository_dir.resolve().as_uri())

    assert detect_kind(Locator(dependency.repository)) == 'git'
    assert Locator(dependency.repository).get_local_path() == str(repository_dir)


def test_a_dependency_location_resolves_to_the_kind_it_spells(tmp_path):
    lib_dir = tmp_path / 'mylib'
    lib_dir.mkdir()

    detected = Dependency(location='mylib')
    detected.update_source(str(tmp_path))
    assert detected.directory == lib_dir.resolve().as_uri()
    assert detected.repository == ''
    assert detected.location == ''

    # The override that changes an answer is the other way round: a checkout git
    # would clone, asked for as a directory to copy instead. `git+` cannot turn
    # `mylib` into a repository, so it refuses it rather than mislabelling it.
    checkout = tmp_path / 'myrepo'
    (checkout / '.git').mkdir(parents=True)
    (checkout / '.git' / 'HEAD').write_text('ref: refs/heads/main\n', encoding='utf-8')

    copied = Dependency(location='directory+myrepo')
    copied.update_source(str(tmp_path))
    assert copied.directory == checkout.resolve().as_uri()
    assert copied.repository == ''

    cloned = Dependency(location='git+myrepo')
    cloned.update_source(str(tmp_path))
    assert cloned.repository == checkout.resolve().as_uri()
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

    assert [cookbook.locator for cookbook in cookbooks] == [Locator(recipes_dir.resolve().as_uri())]


def test_get_overlay_locations_normalizes_local_paths(monkeypatch, tmp_path):
    context = make_repository_context(project_dir=tmp_path)
    overrides_dir = tmp_path / 'overrides'
    overrides_dir.mkdir()

    monkeypatch.setenv('GOLEM_OVERLAYS_LOCATIONS', 'overrides')

    overlays = context.get_settings().get('GOLEM_OVERLAYS_LOCATIONS')

    assert [overlay.locator for overlay in overlays] == [Locator(overrides_dir.resolve().as_uri())]


def test_normalize_repository_url_percent_encodes_local_paths(tmp_path):
    project_dir = tmp_path / 'project dir'
    recipes_dir = project_dir / 'recipes #1'
    recipes_dir.mkdir(parents=True)

    repository = RequestedSource.parse('recipes #1', str(project_dir)).locator

    assert repository == Locator(recipes_dir.resolve().as_uri())
    assert repository.get_local_path() == str(recipes_dir.resolve())


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
    # amd64, not x64: vcvarsall takes the second member of waf's pair.
    assert captured['command'][4].startswith('call "C:\\VS Path\\VC\\Auxiliary\\Build\\vcvarsall.bat" amd64')
    assert '&& cl.exe /nologo' in captured['command'][4]


# -- overrides: the precedence and the memo Context still owns ---------------


def make_overrides_context(tmp_path, monkeypatch):
    project_dir = tmp_path / 'project'
    project_dir.mkdir(exist_ok=True)
    context = make_repository_context(project_dir=project_dir, deps_resolve=False)
    context.resolved_overrides = ''
    monkeypatch.setattr(context, 'make_build_path',
                        lambda path: str(tmp_path / 'build' / path))
    return context, project_dir


def test_an_explicit_configuration_stands_in_for_the_overlays(monkeypatch, tmp_path):
    context, project_dir = make_overrides_context(tmp_path, monkeypatch)
    (project_dir / 'explicit.json').write_text(
        json.dumps([{'repository': 'https://host/fmt.git', 'version': '^10.0.0'}]),
        encoding='utf-8')
    monkeypatch.setenv('GOLEM_OVERRIDES_CONFIGURATION', 'explicit.json')
    # Never consulted: the explicit file wins outright.
    monkeypatch.setenv('GOLEM_OVERLAYS_LOCATIONS', 'directory+{}'.format(tmp_path / 'unused'))

    overrides = context.load_overrides_configuration()

    assert [override.repository for override in overrides] == ['https://host/fmt.git']


def test_the_resolved_overrides_path_is_worked_out_once(monkeypatch, tmp_path):
    # Sub-builds are handed this memo, so it must survive being read again.
    context, project_dir = make_overrides_context(tmp_path, monkeypatch)
    (project_dir / 'explicit.json').write_text('[]', encoding='utf-8')
    monkeypatch.setenv('GOLEM_OVERRIDES_CONFIGURATION', 'explicit.json')

    context.load_overrides_configuration()
    resolved = context.resolved_overrides
    assert resolved == str(project_dir / 'explicit.json')

    monkeypatch.delenv('GOLEM_OVERRIDES_CONFIGURATION')
    context.load_overrides_configuration()

    assert context.resolved_overrides == resolved


def test_no_overrides_configured_at_all_resolves_to_nothing(monkeypatch, tmp_path):
    context, _ = make_overrides_context(tmp_path, monkeypatch)
    monkeypatch.delenv('GOLEM_OVERRIDES_CONFIGURATION', raising=False)
    monkeypatch.delenv('GOLEM_OVERLAYS_LOCATIONS', raising=False)

    assert context.load_overrides_configuration() is None


def test_make_basic_dependency_repo_path_uses_the_cache_key_with_branch(tmp_path):
    context = make_repository_context(project_dir=tmp_path)
    context.cache_configuration = make_cache_configuration(
        CacheDirectory('/cache', is_read_only=False), minimization_enabled=False)

    requested = RequestedSource.for_repository(
        'https://github.com/GolemCpp/recipes.git', version='main')

    manager = get_cookbook_manager(context.cache_configuration)
    repo_path = manager.resolve_cached_resource(
        manager.get_cookbook(requested)).path

    assert repo_path == os.path.join(
        '/cache', COOKBOOKS_SUBDIR,
        get_cookbook_manager(context.cache_configuration).cache_key_for(
            manager.get_cookbook(requested)))


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
    dep.resolved = ResolvedVersion(revision='1234567890abcdef')
    # Primed the way configure does, so the path comes from that resolution.
    get_dependency_manager(context.cache_configuration).update_cached_resource(dep)

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
        'resolved': {'reference': '3.11.3', 'revision': '1234567890abcdef'},
    })
    assert dep.cached_resource is None

    location = context.get_dep_location(dep)

    assert location == get_dependency_manager(
        context.cache_configuration).resolve_cached_resource(dep).path
    # Resolved once and kept: the same cached resource answers every later path.
    assert dep.cached_resource.path == location
    assert context.get_dep_cached_resource(dep) is dep.cached_resource


def test_a_dependency_source_prefers_the_commit_whole():
    # Whole, not abbreviated: git is handed this as it is, and cutting it down to
    # fit a directory name is resource_manager.make_revision_component's job.
    dep = Dependency(repository='https://host/json.git')
    dep.resolved = ResolvedVersion(reference='3.11.3', revision='1234567890abcdef')
    assert ResourceManager.source_for(dep).resolved.revision == '1234567890abcdef'

    # Keyed on the commit, which is what the kind's Pinning names -- not the
    # Source's rule.
    assert DependencyManager.cache_key_for(dep).endswith(
        '+' + make_revision_component('1234567890abcdef'))


def test_a_build_script_may_reach_a_remote():
    # What a project runs for itself is not golem fetching a resource, so a
    # script may use git the way it likes even during a build.
    context = Context.__new__(Context)
    observed = []

    context.run_build_script(lambda ctx: observed.append(
        (ctx, network.is_allowed())))

    assert observed == [(context, True)]
    assert network.is_allowed() is False