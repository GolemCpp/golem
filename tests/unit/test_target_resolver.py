import pytest
from types import SimpleNamespace

from waflib import Logs

from golemcpp.golem import target_platform
from golemcpp.golem.target_resolver import TargetResolver


def make_resolver(*, arch=None, msvc=False, builds=False, dest_cpu=''):
    '''
    A resolver over a configuration context that answers what it is asked.

    `builds` is what the compiler says when told to build with selecting
    flags, which is the only way a multilib target can be confirmed; every
    such attempt is recorded on `attempted`.
    '''
    conf = SimpleNamespace(
        options=SimpleNamespace(arch=arch),
        env=SimpleNamespace(CXX=['g++'], DEST_CPU=dest_cpu),
    )
    resolver = TargetResolver(conf, msvc=msvc)
    resolver.attempted = []
    resolver.reported = []
    conf.check_cxx = lambda **kw: (resolver.attempted.append(kw['cxxflags']) or builds)
    conf.msg = lambda label, value: resolver.reported.append((label, value))
    return resolver


def answering(resolver, target):
    resolver.compiler_target = lambda: target
    return resolver


@pytest.fixture
def warnings(monkeypatch):
    said = []
    monkeypatch.setattr(Logs, 'warn', lambda message, *args: said.append(message))
    return said


# --- Asking the compiler -------------------------------------------------


def test_msvc_is_asked_what_it_targets_rather_than_assumed():
    # A Visual Studio installation need not include tools for the machine it
    # runs on, so the host is not an answer here. waf records the target of
    # the installation it detected.
    resolver = make_resolver(msvc=True, dest_cpu='arm64')

    assert resolver.compiler_target().arch == 'aarch64'


def test_msvc_is_not_asked_for_a_triple_it_does_not_have():
    assert make_resolver(msvc=True).compiler_triple() == ''


def test_a_compiler_that_is_not_there_is_not_run():
    # Nothing to execute, so nothing is claimed rather than an exception from
    # somewhere further down.
    resolver = make_resolver()
    resolver.conf.env.CXX = []

    assert resolver.compiler_triple() == ''


# --- Settling it against the request -------------------------------------


def test_resolution_refuses_to_name_an_architecture_nobody_established():
    resolver = answering(make_resolver(), target_platform.CompilerTarget())

    with pytest.raises(RuntimeError, match=r'Cannot tell what architecture'):
        resolver.resolve()


def test_resolution_takes_the_compilers_answer_when_nothing_was_asked():
    resolver = answering(
        make_resolver(), target_platform.CompilerTarget(arch='armv7-eabihf')
    )

    assert resolver.resolve() == 'armv7-eabihf'


def test_resolution_accepts_a_request_the_compiler_agrees_with():
    resolver = answering(
        make_resolver(arch='amd64'), target_platform.CompilerTarget(arch='x86_64')
    )

    # Spelled 'amd64', resolved to the canonical name, and no disagreement.
    assert resolver.resolve() == 'x86_64'


def test_resolution_rejects_a_request_the_compiler_contradicts():
    resolver = answering(
        make_resolver(arch='aarch64'), target_platform.CompilerTarget(arch='x86_64')
    )

    with pytest.raises(RuntimeError, match=r"Requested architecture 'aarch64'"):
        resolver.resolve()


def test_a_request_supplies_the_isa_level_a_cross_triple_cannot():
    # arm-linux-gnueabihf on an x86_64 host: the compiler cannot say whether
    # it means armv6 or armv7, because only uname knows and uname is
    # describing the host. The request is allowed to settle exactly that.
    resolver = answering(
        make_resolver(arch='armv7-eabihf'),
        target_platform.CompilerTarget.from_triple('arm-linux-gnueabihf', 'x86_64'),
    )

    assert resolver.resolve() == 'armv7-eabihf'


def test_a_request_may_not_contradict_the_abi_the_triple_did_report():
    # The triple could not name a target but was emphatic about hard float.
    # Accepting armv7-eabi here would cache an artifact that links with
    # nothing.
    resolver = answering(
        make_resolver(arch='armv7-eabi'),
        target_platform.CompilerTarget.from_triple('arm-linux-gnueabihf', 'x86_64'),
    )

    with pytest.raises(RuntimeError, match=r"'eabihf' ABI"):
        resolver.resolve()


@pytest.mark.parametrize('arch', ['aarch64', 'x86_64'])
def test_a_request_may_not_contradict_the_family_either(arch):
    resolver = answering(
        make_resolver(arch=arch),
        target_platform.CompilerTarget.from_triple('arm-linux-gnueabihf', 'x86_64'),
    )

    with pytest.raises(RuntimeError, match=r"'arm' family"):
        resolver.resolve()


# --- Asking by building --------------------------------------------------


def test_a_multilib_compiler_reaches_a_target_its_triple_never_names():
    # gcc reports the target it was configured for, not the only one it can
    # build: `gcc -m32 -dumpmachine` still answers x86_64. Comparing triples
    # alone would refuse every 32-bit build on a 64-bit host.
    resolver = answering(
        make_resolver(arch='i686', builds=True),
        target_platform.CompilerTarget(arch='x86_64'),
    )

    assert resolver.resolve() == 'i686'
    assert resolver.attempted == [['-m32']]


def test_a_multilib_target_the_compiler_cannot_actually_build_is_refused():
    # The flag exists but the platform ships no 32-bit userland, so nothing
    # links. Asking is what tells the two apart.
    resolver = answering(
        make_resolver(arch='i686', builds=False),
        target_platform.CompilerTarget(arch='x86_64'),
    )

    with pytest.raises(RuntimeError, match=r'-m32'):
        resolver.resolve()


def test_a_target_no_flag_reaches_is_refused_without_asking():
    # No -m flag turns an x86_64 compiler into an ARM one, and the capability
    # table says so by carrying no flags at all. Nothing to try.
    resolver = answering(
        make_resolver(arch='aarch64', builds=True),
        target_platform.CompilerTarget(arch='x86_64'),
    )

    with pytest.raises(RuntimeError, match=r"builds for 'x86_64'"):
        resolver.resolve()

    assert resolver.attempted == []


def test_a_ruled_out_family_is_not_a_multilib_question():
    # The triple named no target, so there is nothing for a flag to reach
    # from. -m64 must not be tried, nor claimed to have been.
    resolver = answering(
        make_resolver(arch='x86_64'),
        target_platform.CompilerTarget.from_triple('arm-linux-gnueabihf', 'x86_64'),
    )

    with pytest.raises(RuntimeError, match=r"'arm' family") as raised:
        resolver.resolve()

    assert resolver.attempted == []
    assert '-m64' not in str(raised.value)


def test_msvc_is_never_asked_to_build_with_a_gnu_flag():
    # It takes no such flag, and its request already reached waf through
    # MSVC_TARGETS before detection ran.
    resolver = answering(
        make_resolver(arch='i686', msvc=True, builds=True),
        target_platform.CompilerTarget(arch='x86_64'),
    )

    with pytest.raises(RuntimeError, match=r"builds for 'x86_64'"):
        resolver.resolve()

    assert resolver.attempted == []


# --- A compiler that answered nothing ------------------------------------


def test_a_silent_compiler_is_still_asked_to_build_where_a_flag_can_ask(warnings):
    # It reported no target, but the request is one Golem has a flag for, so
    # there is a check available and taking it on trust would be a choice.
    resolver = answering(
        make_resolver(arch='i686', builds=True), target_platform.CompilerTarget()
    )

    assert resolver.resolve() == 'i686'
    assert resolver.attempted == [['-m32']]
    # Confirmed rather than trusted, so there is nothing to warn about.
    assert warnings == []


def test_a_silent_compiler_that_cannot_build_the_request_is_an_error():
    # Nothing supports the request: no target reported, and the one check
    # available failed. Naming the artifact anyway would be a plain lie.
    resolver = answering(
        make_resolver(arch='i686', builds=False), target_platform.CompilerTarget()
    )

    with pytest.raises(RuntimeError, match=r'no target of its own'):
        resolver.resolve()


def test_a_request_nothing_can_check_is_taken_on_trust(warnings):
    # An MSVC-like toolchain that reported nothing, which is waf's
    # no_autodetect(): it returns before writing DEST_CPU. No flag can put the
    # question to cl.exe either, so nothing checks the request. The other
    # silent case is a toolchain with no -dumpmachine.
    resolver = answering(
        make_resolver(arch='i686', msvc=True), target_platform.CompilerTarget()
    )

    assert resolver.resolve() == 'i686'
    assert resolver.attempted == []
    assert len(warnings) == 1
    assert "'i686' on request alone" in warnings[0]


def test_a_compiler_that_did_answer_is_not_second_guessed(warnings):
    # The warning is about nothing having checked the request, so a compiler
    # that agreed must not produce it.
    resolver = answering(
        make_resolver(arch='x86_64'), target_platform.CompilerTarget(arch='x86_64')
    )

    assert resolver.resolve() == 'x86_64'
    assert warnings == []


def test_a_coarse_answer_counts_as_an_answer(warnings):
    # The triple could not name a target, but it did rule things out, so the
    # request was held to something and is not being taken on trust.
    resolver = answering(
        make_resolver(arch='armv7-eabihf'),
        target_platform.CompilerTarget.from_triple('arm-linux-gnueabihf', 'x86_64'),
    )

    assert resolver.resolve() == 'armv7-eabihf'
    assert warnings == []


# --- Saying what it settled on -------------------------------------------


def test_the_settled_target_is_reported():
    # The answer reaches the slug, the advertisement and every arch condition,
    # so a build settling on the wrong one is wrong everywhere and visible
    # nowhere. On a host nobody has run Golem on, this line is the diagnosis.
    resolver = answering(
        make_resolver(), target_platform.CompilerTarget(arch='aarch64')
    )

    resolver.resolve()

    assert resolver.reported == [('Target architecture', 'aarch64')]


def test_a_target_that_could_not_be_settled_is_not_reported():
    resolver = answering(
        make_resolver(arch='x86_64'), target_platform.CompilerTarget(arch='aarch64')
    )

    with pytest.raises(RuntimeError):
        resolver.resolve()

    assert resolver.reported == []


def test_a_family_with_no_abi_says_which_targets_would_do():
    # riscv64 is the case: `riscv64-linux-gnu` covers lp64 and lp64d, uname
    # says `riscv64` as well, and neither has an ABI to give. The compiler did
    # answer, so saying it did not would be wrong -- and it would leave a user
    # on a native host with nothing to act on.
    resolver = answering(
        make_resolver(),
        target_platform.CompilerTarget.from_triple('riscv64-linux-gnu', 'riscv64'),
    )

    with pytest.raises(RuntimeError) as raised:
        resolver.resolve()

    message = str(raised.value)
    assert 'which riscv64 it builds for' in message
    assert 'riscv64-lp64, riscv64-lp64f, riscv64-lp64d' in message
    assert 'did not say' not in message
    # The reasoning is a comment's job. A message that says 'family', 'triple'
    # or 'ABI' is describing Golem to someone who wants to build something.
    assert not any(word in message for word in ('family', 'triple', 'ABI'))


def test_a_compiler_that_truly_said_nothing_still_says_so():
    resolver = answering(make_resolver(), target_platform.CompilerTarget())

    with pytest.raises(RuntimeError, match=r'the compiler did not say'):
        resolver.resolve()


def test_a_family_settled_by_a_request_is_not_an_error():
    resolver = answering(
        make_resolver(arch='riscv64-lp64d'),
        target_platform.CompilerTarget.from_triple('riscv64-linux-gnu', 'riscv64'),
    )

    assert resolver.resolve() == 'riscv64-lp64d'


# --- Asking the compiler what its triple left out ------------------------


def asking(resolver, triple, macros):
    resolver.compiler_triple = lambda: triple
    resolver.asked = []
    resolver.compiler_macros = lambda: resolver.asked.append(True) or macros
    return resolver


def test_a_triple_that_named_no_target_is_completed_from_the_macros():
    # riscv64-linux-gnu covers every RISC-V ABI and uname says riscv64 too, so
    # the compiler's own macros are the only source left.
    resolver = asking(
        make_resolver(),
        'riscv64-linux-gnu',
        {'__riscv_xlen': '64', '__riscv_float_abi_double': '1'},
    )

    assert resolver.resolve() == 'riscv64-lp64d'


def test_a_triple_that_named_a_target_is_not_asked_again():
    # Every configure would pay for the extra process, and the answer is
    # already there.
    resolver = asking(make_resolver(), 'x86_64-linux-gnu', {})

    assert resolver.resolve() == 'x86_64'
    assert resolver.asked == []


def test_a_compiler_with_no_triple_at_all_is_not_asked_either():
    # The macros are asked for what a triple left out. A compiler that said
    # nothing left nothing out, so there is no second guess at the whole
    # answer here.
    resolver = asking(make_resolver(), '', {})

    assert resolver.compiler_target() == target_platform.CompilerTarget()
    assert resolver.asked == []


def test_a_family_the_macros_cannot_complete_is_still_an_error():
    resolver = asking(make_resolver(), 'riscv64-linux-gnu', {})

    with pytest.raises(RuntimeError, match=r'which riscv64 it builds for'):
        resolver.resolve()

    assert resolver.asked == [True]


def test_msvc_is_never_asked_for_macros():
    # It takes no -dM -E, and DEST_CPU is already a whole answer.
    resolver = make_resolver(msvc=True, dest_cpu='x64')

    assert resolver.compiler_macros() == {}


def test_a_compiler_that_is_not_there_is_not_asked_for_macros():
    resolver = make_resolver()
    resolver.conf.env.CXX = []

    assert resolver.compiler_macros() == {}
