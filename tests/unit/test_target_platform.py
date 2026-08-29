import pytest

from golemcpp.golem import target_platform
from golemcpp.golem.target_platform import ArchCapability


def test_an_unknown_architecture_keeps_its_name_rather_than_becoming_nothing():
    # This is the whole point of the rewrite. The table this replaces returned
    # None for anything outside the x86 family, and that None travelled until
    # something concatenated it into a path.
    assert target_platform.normalize_arch('sparc64') == 'sparc64'
    assert target_platform.normalize_arch('something-nobody-has-built-yet')


def test_normalizing_is_idempotent():
    # A canonical name has to survive being normalized again, or a value that
    # passes through two entry points comes out different from one that passes
    # through one.
    spellings = (
        list(target_platform.ARCH_ALIASES)
        + list(target_platform.ARCH_FAMILY_DEFAULTS)
        + list(target_platform.CANONICAL_ARCHS)
    )
    for spelling in spellings:
        once = target_platform.normalize_arch(spelling)
        assert target_platform.normalize_arch(once) == once


def test_every_table_resolves_to_a_canonical_name():
    # An alias pointing at a name that is not in the vocabulary would be a typo
    # nobody notices until a build slug looks wrong.
    for table in (target_platform.ARCH_ALIASES, target_platform.ARCH_FAMILY_DEFAULTS):
        for canonical in table.values():
            assert canonical in target_platform.CANONICAL_ARCHS

    for known in target_platform.ARCH_CAPABILITIES:
        assert known in target_platform.CANONICAL_ARCHS


def test_the_spellings_of_one_architecture_agree():
    # These used to disagree: the raw option reached the build slug while a
    # normalized copy reached everything else, so --arch=amd64 and
    # --arch=x86_64 built into two different directories.
    assert (
        target_platform.normalize_arch('amd64')
        == target_platform.normalize_arch('x86_64')
        == target_platform.normalize_arch('x64')
        == 'x86_64'
    )


def test_arm_answers_to_both_of_its_names():
    # Apple says arm64 and GNU says aarch64. Both have to arrive somewhere.
    assert (
        target_platform.normalize_arch('arm64')
        == target_platform.normalize_arch('aarch64')
        == 'aarch64'
    )


def test_the_members_of_the_thirty_two_bit_family_stay_apart():
    # They are not spellings of one target. An i686 binary uses cmov and raises
    # SIGILL on a 486, and gcc has a -march for each, so collapsing them would
    # promise a compatibility that does not exist.
    family = ['i386', 'i486', 'i586', 'i686']
    assert [target_platform.normalize_arch(name) for name in family] == family
    assert len({target_platform.normalize_arch(name) for name in family}) == 4


def test_the_older_family_members_name_their_baseline():
    # -m32 alone gives the compiler's own 32-bit baseline, which is already i686
    # on anything modern, so only the older ones have to say so.
    assert target_platform.arch_capability('i686').gnu_flags == ('-m32',)
    assert '-march=i486' in target_platform.arch_capability('i486').gnu_flags
    assert '-march=i386' in target_platform.arch_capability('i386').gnu_flags


def test_a_family_name_resolves_to_a_documented_default():
    # x86 and ia32 name the 32-bit line rather than a member of it. Both land on
    # i686 because that is what every toolchain using those tokens means, and
    # anyone wanting 386 baseline can now say i386.
    assert target_platform.normalize_arch('x86') == 'i686'
    assert target_platform.normalize_arch('ia32') == 'i686'
    assert 'x86' not in target_platform.ARCH_ALIASES
    assert 'ia32' not in target_platform.ARCH_ALIASES


def test_an_ambiguous_abi_is_not_guessed():
    # riscv64 alone does not say whether floats go in registers, and the two
    # ABIs do not link together. Passing it through unchanged is honest; picking
    # one silently is not.
    assert target_platform.normalize_arch('riscv64') == 'riscv64'
    assert target_platform.arch_capability('riscv64') == ArchCapability()


def test_debian_port_names_are_not_accepted_as_architectures():
    # armhf and armel are how Debian spells a port, not what a target is. They
    # exist in the packaging direction only.
    assert 'armhf' not in target_platform.ARCH_ALIASES
    assert target_platform.arch_capability('armv7-eabihf').debian_arch == 'armhf'
    assert target_platform.arch_capability('armv7-eabi').debian_arch == 'armel'


def test_spelling_is_case_and_whitespace_insensitive():
    # platform.machine() reports AMD64 on Windows, and people paste with spaces.
    assert target_platform.normalize_arch('  AMD64 ') == 'x86_64'
    assert target_platform.normalize_arch('ARM64') == 'aarch64'


def test_nothing_normalizes_to_nothing():
    # An absent architecture is the caller's to default, not this function's to
    # invent, so it stays pure and hands back what it was given.
    assert target_platform.normalize_arch('') == ''
    assert target_platform.normalize_arch(None) == ''


def test_an_unknown_architecture_has_no_capability_rather_than_no_answer():
    # Empty means "say nothing and let the toolchain use its own default",
    # which is right for a native build. None would mean a crash later.
    capability = target_platform.arch_capability('sparc64')
    assert capability == ArchCapability()
    assert capability.gnu_flags == ()
    assert capability.vs_platform == ''


def test_capability_is_reached_through_an_alias():
    # Callers should not have to normalize before asking.
    assert target_platform.arch_capability('amd64').gnu_flags == ('-m64',)


def test_a_target_msvc_cannot_reach_says_so_by_staying_empty():
    # MSVC has no 80386 mode. Carrying GNU flags but no Visual Studio fields is
    # the accurate answer, rather than pretending x86 covers it.
    i386 = target_platform.arch_capability('i386')
    assert i386.gnu_flags
    assert i386.vs_platform == ''
    assert i386.msvc_target == ''


def test_thirty_two_bit_visual_studio_is_called_win32():
    # MSBuild's /p:Platform and CMake's -A both reject 'x86'. Golem passed it
    # for years because the arch vocabulary happened to spell it that way.
    assert target_platform.arch_capability('i686').vs_platform == 'Win32'
    assert target_platform.arch_capability('x86_64').vs_platform == 'x64'


def test_waf_and_vcvarsall_disagree_about_the_name_of_x86_64():
    # waf's all_msvc_platforms pairs them as ('x64', 'amd64'): the first is what
    # MSVC_TARGETS wants, the second is what vcvarsall.bat wants. Conflating
    # them is how one env var ended up holding two vocabularies.
    capability = target_platform.arch_capability('x86_64')
    assert capability.msvc_target == 'x64'
    assert capability.vcvars_arg == 'amd64'


def test_an_abi_can_be_recovered_from_the_name_that_carries_it():
    # ABI is folded into the canonical name so matching stays a string compare,
    # but it is spelled <isa>-<abi> so building a triple later needs no table.
    isa, _, abi = target_platform.ARCH_ARMV7_EABIHF.rpartition('-')
    assert isa == 'armv7'
    assert abi == 'eabihf'


def test_the_host_reports_an_operating_system_that_is_usable():
    # Not necessarily a name this file knows — Golem may be running somewhere
    # nobody anticipated — but it has to be stable and already canonical.
    osystem = target_platform.host_osystem()
    assert osystem
    assert target_platform.normalize_osystem(osystem) == osystem


def test_an_operating_system_version_never_reaches_the_name(monkeypatch):
    # sys.platform is version-suffixed on the BSDs and Solaris. Left alone, the
    # release would land in every build slug and an OS upgrade would invalidate
    # the entire cache.
    monkeypatch.setattr(target_platform.sys, 'platform', 'freebsd14')
    assert target_platform.host_osystem() == 'freebsd'

    monkeypatch.setattr(target_platform.sys, 'platform', 'openbsd7')
    assert target_platform.host_osystem() == 'openbsd'

    # Stripping the digits is also what lets sunos5 reach its alias, so Solaris
    # and illumos arrive at a canonical name rather than a stable-but-unknown
    # one.
    monkeypatch.setattr(target_platform.sys, 'platform', 'sunos5')
    assert target_platform.host_osystem() == 'solaris'

    # Somewhere genuinely unknown still gets a stable name rather than nothing.
    monkeypatch.setattr(target_platform.sys, 'platform', 'aix')
    assert target_platform.host_osystem() == 'aix'


def test_a_system_that_emulates_another_is_not_called_the_other(monkeypatch):
    # Cygwin looks like it should be 'windows' and must not be: its binaries
    # link cygwin1.dll and cannot run as native Windows ones, so the name would
    # promise a compatibility that does not exist.
    monkeypatch.setattr(target_platform.sys, 'platform', 'cygwin')
    assert target_platform.host_osystem() == 'cygwin'


def test_an_operating_system_answers_to_the_names_people_use():
    # 'osx' is what Golem itself said before the rename, so it has to keep
    # working, and 'iphoneos' is what the runtime code already reports.
    assert (
        target_platform.normalize_osystem('Darwin')
        == target_platform.normalize_osystem('osx')
        == target_platform.normalize_osystem('macOS')
        == 'macos'
    )
    assert target_platform.normalize_osystem('Win32') == 'windows'
    assert target_platform.normalize_osystem('iphoneos') == 'ios'


def test_an_isa_is_read_out_of_a_uname_string():
    # The trailing letter is byte order, not architecture. Fedora's 'h' is hard
    # float and worth keeping.
    assert target_platform.machine_isa('armv7l') == ('armv7', '')
    assert target_platform.machine_isa('armv6l') == ('armv6', '')
    assert target_platform.machine_isa('armv7hl') == ('armv7', 'eabihf')
    assert target_platform.machine_isa('x86_64') == ('x86_64', '')


def test_arm_extension_letters_are_not_mistaken_for_byte_order():
    # A real armv5 machine says armv5tel: 'te' are ISA extensions, 'l' is byte
    # order. Reading the tail as one thing would lose the version.
    assert target_platform.machine_isa('armv5tel') == ('armv5', '')
    assert target_platform.machine_isa('armv8l') == ('armv8', '')
    assert target_platform.machine_isa('armv7hl') == ('armv7', 'eabihf')


def test_armv5_lands_on_the_debian_port_that_matches_it():
    # Debian's armel port is armv5te, and armv5 predates VFP, so soft float is
    # the only ABI it has.
    assert target_platform.arch_capability('armv5-eabi').debian_arch == 'armel'


def test_a_target_must_be_told_both_halves():
    # No factory fills in the host for a missing half. Every such default was a
    # place a target could be named without anyone deciding it, and a target
    # nobody decided still reaches a build slug and an advertisement.
    assert not hasattr(target_platform.TargetPlatform, 'make')
    assert not hasattr(target_platform.TargetPlatform, 'host')

    with pytest.raises(TypeError):
        target_platform.TargetPlatform(osystem='linux')
    with pytest.raises(TypeError):
        target_platform.TargetPlatform(arch='x86_64')


def test_a_target_carries_its_own_capability():
    target = target_platform.TargetPlatform(osystem='linux', arch='amd64')
    assert target.capability.gnu_flags == ('-m64',)


def test_a_target_is_canonical_however_it_was_built():
    # The invariant has to hold for the plain constructor too, not just the
    # factories: a target holding 'x64' would put that spelling in a build slug
    # and undo the whole point of normalizing.
    target = target_platform.TargetPlatform(osystem='OSX', arch='  AMD64 ')
    assert target.osystem == 'macos'
    assert target.arch == 'x86_64'


def test_the_operating_system_vocabulary_reaches_past_what_golem_can_build():
    # Naming one is what lets a recipe restrict a target to it, which is useful
    # well before Golem can produce a binary for it.
    for osystem in ('freebsd', 'ios', 'android', 'emscripten'):
        assert osystem in target_platform.CANONICAL_OSYSTEMS

    for alias in target_platform.OS_ALIASES.values():
        assert alias in target_platform.CANONICAL_OSYSTEMS


# --- Composing an identity from a compiler's own triple ------------------


@pytest.mark.parametrize(
    'triple, machine, expected',
    [
        # The arch field is already canonical and carries no ABI to recover, so the
        # machine is not consulted at all.
        ('x86_64-pc-linux-gnu', 'x86_64', 'x86_64'),
        ('aarch64-unknown-linux-gnu', 'aarch64', 'aarch64'),
        ('i686-linux-gnu', 'i686', 'i686'),
        # The two halves: the triple settles the ABI, the machine the ISA level.
        # gcc says 'arm' whether it is armv6 or armv7, and uname says 'armv7l'
        # whether it is hard float or soft.
        ('arm-linux-gnueabihf', 'armv7l', 'armv7-eabihf'),
        ('arm-linux-gnueabi', 'armv7l', 'armv7-eabi'),
        ('arm-linux-gnueabihf', 'armv6l', 'armv6-eabihf'),
        ('arm-linux-musleabihf', 'armv6l', 'armv6-eabihf'),
        ('arm-linux-musleabi', 'armv5tel', 'armv5-eabi'),
        # A triple that names its own ISA level does not need the machine.
        ('armv7a-linux-gnueabihf', 'x86_64', 'armv7-eabihf'),
    ],
)
def test_a_compiler_triple_composes_an_identity(triple, machine, expected):
    assert target_platform.Triple.parse(triple).canonical_arch(machine) == expected


@pytest.mark.parametrize('triple', ['', '   ', '-'])
def test_a_triple_that_says_nothing_resolves_to_nothing(triple):
    # Empty rather than a guess, so the caller can fall back to the request.
    assert target_platform.Triple.parse(triple).canonical_arch('x86_64') == ''


def test_an_unrecognised_triple_still_yields_an_identity():
    # Totality again: no capability will be found for it, but it gets a name.
    assert (
        target_platform.Triple.parse('sparc64-unknown-linux-gnu').canonical_arch(
            'sparc64'
        )
        == 'sparc64'
    )


def test_a_family_field_is_not_an_identity():
    # 'arm' names the whole 32-bit line. Passing it through would put a name
    # that is not a target into a build slug, and would make an explicit
    # --arch=armv7-eabihf look like a disagreement with its own compiler.
    assert (
        target_platform.Triple.parse('arm-linux-gnuxyz').canonical_arch('armv7l') == ''
    )


def test_a_cross_triple_does_not_borrow_the_ISA_level_from_uname():
    # uname describes the machine running the compiler, which for a cross
    # toolchain is not the machine being built for. Splicing the two would
    # invent an identity out of two unrelated sources.
    assert (
        target_platform.Triple.parse('arm-linux-gnueabihf').canonical_arch('x86_64')
        == ''
    )
    # The same triple is fine where the compiler does target this machine.
    assert (
        target_platform.Triple.parse('arm-linux-gnueabihf').canonical_arch('armv7l')
        == 'armv7-eabihf'
    )


def test_the_bare_abi_spellings_are_understood():
    # What a toolchain outside the glibc/musl world reports. Recognising the
    # spelling is vocabulary; being able to build it is not, and the operating
    # system half of such a target is still unrepresentable.
    assert (
        target_platform.Triple.parse('arm-none-eabi').canonical_arch('armv7l')
        == 'armv7-eabi'
    )
    assert (
        target_platform.Triple.parse('arm-none-eabihf').canonical_arch('armv6l')
        == 'armv6-eabihf'
    )


@pytest.mark.parametrize(
    'triple, expected',
    [
        # Three of Android's four ABIs need nothing special: their triples put a
        # canonical name in the arch field and the -android suffix never has to be
        # read at all.
        ('aarch64-linux-android', 'aarch64'),
        ('x86_64-linux-android', 'x86_64'),
        ('i686-linux-android', 'i686'),
        # armeabi-v7a is the one that does, and it gets a name of its own rather
        # than borrowing eabi, because softfp links with neither of the other two.
        ('armv7a-linux-androideabi', 'armv7-androideabi'),
    ],
)
def test_androids_abis_resolve(triple, expected):
    # The host is x86_64 throughout: an NDK is always a cross toolchain, and
    # none of these may borrow an ISA level from the machine running it.
    assert target_platform.Triple.parse(triple).canonical_arch('x86_64') == expected


@pytest.mark.parametrize(
    'triple, expected',
    [
        ('aarch64-linux-android21', 'aarch64'),
        ('armv7a-linux-androideabi21', 'armv7-androideabi'),
    ],
)
def test_the_android_api_level_is_not_part_of_the_architecture(triple, expected):
    # The NDK puts minSdkVersion in the triple it is invoked with. It is a real
    # part of the target and belongs to its own axis, the way a macOS
    # deployment target does -- never folded into an architecture's name.
    assert target_platform.Triple.parse(triple).canonical_arch('x86_64') == expected


def test_androids_float_abi_is_not_confused_with_the_other_two():
    # softfp is neither, so these three must not collapse: an artifact built
    # for one links with neither of the others.
    assert (
        len(
            {
                target_platform.ARCH_ARMV7_EABI,
                target_platform.ARCH_ARMV7_EABIHF,
                target_platform.ARCH_ARMV7_ANDROIDEABI,
            }
        )
        == 3
    )
    assert target_platform.ARCH_ARMV7_ANDROIDEABI in target_platform.CANONICAL_ARCHS
    # Canonical for identity, empty for capability: nothing can select it with
    # a flag, because reaching it means using the NDK's own toolchain.
    assert (
        target_platform.arch_capability(target_platform.ARCH_ARMV7_ANDROIDEABI)
        is target_platform.NO_CAPABILITY
    )


@pytest.mark.parametrize(
    'triple, machine',
    [
        # riscv64-linux-gnu is the tuple for both lp64 and lp64d, and lp64 is soft
        # float, so the two do not link. The arch field is a family exactly as
        # `arm` is -- it is missing an ABI rather than an ISA level.
        ('riscv64-linux-gnu', 'riscv64'),
        ('mips64el-linux-gnuabi64', 'mips64el'),
    ],
)
def test_an_abi_the_triple_cannot_name_is_not_composed(triple, machine):
    # Even on the machine it describes, since the machine does not know either.
    assert target_platform.Triple.parse(triple).canonical_arch(machine) == ''


@pytest.mark.parametrize(
    'triple, arch, abi',
    [
        # Coarse enough that no identity can be composed, specific enough to bind
        # a request: this is the pair that keeps such a triple useful.
        ('arm-linux-gnueabihf', 'arm', 'eabihf'),
        ('arm-linux-gnueabi', 'arm', 'eabi'),
        ('arm-none-eabi', 'arm', 'eabi'),
        ('armv7a-linux-androideabi21', 'armv7a', 'androideabi'),
        # An ABI the table does not name leaves that half open rather than guessing.
        ('riscv64-linux-gnu', 'riscv64', ''),
        ('sparc64-unknown-linux-gnu', 'sparc64', ''),
    ],
)
def test_a_triple_constrains_even_when_it_cannot_name(triple, arch, abi):
    parsed = target_platform.Triple.parse(triple)
    assert parsed.arch == arch
    assert parsed.canonical_abi() == abi


@pytest.mark.parametrize('triple', ['', '   ', '-'])
def test_an_empty_triple_constrains_nothing(triple):
    parsed = target_platform.Triple.parse(triple)
    assert parsed.arch == ''
    assert parsed.suffix == ''
    assert parsed.canonical_abi() == ''


def test_the_arch_field_is_a_position_and_the_libc_is_not_an_abi():
    # The two ends are read as written; only the ABI crosses into Golem's
    # vocabulary, where glibc and musl are the same target.
    assert target_platform.Triple.parse('arm-linux-musleabihf').arch == 'arm'
    assert target_platform.Triple.parse('arm-linux-musleabihf').suffix == 'musleabihf'
    assert (
        target_platform.Triple.parse('arm-linux-musleabihf').canonical_abi() == 'eabihf'
    )
    assert (
        target_platform.Triple.parse('arm-linux-gnueabihf').canonical_abi() == 'eabihf'
    )


# --- One answer, checked and settled in one place ------------------------


ARM_CROSS = target_platform.CompilerTarget.from_triple('arm-linux-gnueabihf', 'x86_64')
NAMED = target_platform.CompilerTarget(arch='x86_64')
# A compiler Golem could get no answer out of, which is not MSVC: that one
# answers through DEST_CPU and lands in NAMED's shape.
SILENT = target_platform.CompilerTarget()


def test_a_compiler_that_named_its_target_admits_only_that_target():
    assert NAMED.settle('x86_64') == ('x86_64', None)
    assert NAMED.settle('') == ('x86_64', None)
    assert NAMED.settle('aarch64') == ('', target_platform.Refusal.ARCH)


RISCV = target_platform.CompilerTarget.from_triple('riscv64-linux-gnu', 'riscv64')


def test_an_abi_the_triple_left_open_is_supplied_by_the_request():
    # The same shape as 32-bit ARM, from the other direction: there the triple
    # withheld the ISA level, here it withholds the ABI. Either way the
    # compiler genuinely has not said, so the request settles exactly that.
    assert RISCV.settle('riscv64-lp64d') == ('riscv64-lp64d', None)
    assert RISCV.settle('riscv64-lp64') == ('riscv64-lp64', None)


def test_a_family_that_named_no_abi_still_refuses_another_family():
    assert RISCV.settle('x86_64') == ('', target_platform.Refusal.FAMILY)


def test_a_family_on_its_own_settles_nothing():
    # Nothing asked, and a triple that named only a family. Recording bare
    # 'riscv64' would claim an ABI the artifact may not have, so there is
    # nothing to record and the caller reports that.
    assert RISCV.settle('') == ('', None)


def test_a_coarse_answer_admits_what_it_did_not_rule_out():
    # It could not say armv6 or armv7 -- only uname knows and uname is
    # describing the host -- so the request settles exactly that much.
    assert ARM_CROSS.settle('armv7-eabihf') == ('armv7-eabihf', None)
    assert ARM_CROSS.settle('armv6-eabihf') == ('armv6-eabihf', None)


@pytest.mark.parametrize(
    'requested, expected',
    [
        ('armv7-eabi', target_platform.Refusal.ABI),
        ('aarch64', target_platform.Refusal.FAMILY),
        ('x86_64', target_platform.Refusal.FAMILY),
    ],
)
def test_a_coarse_answer_still_refuses_what_it_did_rule_out(requested, expected):
    # Which of the compiler's answers the request contradicts, not the words
    # someone will put around it.
    assert ARM_CROSS.settle(requested) == ('', expected)


def test_nothing_established_is_not_a_disagreement():
    # A compiler with no answer refuses nothing, so a request stands alone.
    assert SILENT.settle('i686') == ('i686', None)
    # And with no request either there is simply nothing to go on, which the
    # caller reports rather than this deciding for it.
    assert SILENT.settle('') == ('', None)


# --- What an incomplete answer still leaves open --------------------------


@pytest.mark.parametrize(
    'triple, machine, expected',
    [
        # A triple that named a target admits that target and nothing else.
        ('x86_64-linux-gnu', 'x86_64', ('x86_64',)),
        # riscv64's triple is the same one for every ABI in the family, and uname
        # says `riscv64` too, so neither source narrows it. All three survive.
        (
            'riscv64-linux-gnu',
            'riscv64',
            ('riscv64-lp64', 'riscv64-lp64f', 'riscv64-lp64d'),
        ),
        # The ABI was reported even though the ISA level was not, so the soft-float
        # members are already out.
        ('arm-linux-gnueabihf', 'x86_64', ('armv6-eabihf', 'armv7-eabihf')),
        ('arm-linux-gnueabi', 'x86_64', ('armv5-eabi', 'armv7-eabi')),
    ],
)
def test_an_answer_lists_the_targets_it_leaves_open(triple, machine, expected):
    target = target_platform.CompilerTarget.from_triple(triple, machine)

    assert target.admitted == expected


def test_what_is_left_open_is_exactly_what_would_be_accepted():
    # The list exists to be printed in a message telling someone what to ask
    # for, so it has to be the same rule that would then accept the answer.
    target = target_platform.CompilerTarget.from_triple('riscv64-linux-gnu', 'riscv64')

    for arch in target.admitted:
        assert target.settle(arch) == (arch, None)


def test_a_compiler_that_said_nothing_leaves_everything_open():
    target = target_platform.CompilerTarget()

    assert target.admitted == target_platform.CANONICAL_ARCHS


# --- Reading an identity off a compiler's own macros ----------------------


@pytest.mark.parametrize(
    'macros, expected',
    [
        ({'__riscv_xlen': '64', '__riscv_float_abi_double': '1'}, 'riscv64-lp64d'),
        ({'__riscv_xlen': '64', '__riscv_float_abi_single': '1'}, 'riscv64-lp64f'),
        ({'__riscv_xlen': '64', '__riscv_float_abi_soft': '1'}, 'riscv64-lp64'),
        ({'__riscv_xlen': '32', '__riscv_float_abi_double': '1'}, 'riscv32-ilp32d'),
        ({'__riscv_xlen': '32', '__riscv_float_abi_soft': '1'}, 'riscv32-ilp32'),
    ],
)
def test_a_compiler_names_the_abi_its_triple_could_not(macros, expected):
    assert target_platform.macro_arch(macros) == expected


@pytest.mark.parametrize(
    'macros',
    [
        {},
        # Not RISC-V at all. Its identity came off the triple already.
        {'__x86_64__': '1'},
        # The width without the float ABI is still not a target.
        {'__riscv_xlen': '64'},
        {'__riscv_xlen': '128', '__riscv_float_abi_double': '1'},
    ],
)
def test_macros_that_name_no_architecture_name_none(macros):
    assert target_platform.macro_arch(macros) == ''


def test_every_abi_a_compiler_can_report_has_a_canonical_name():
    # A name macro_arch can produce but the vocabulary does not carry would go
    # into a build slug without ever being listed as a choice.
    for xlen in ('32', '64'):
        for macro in target_platform.RISCV_FLOAT_ABI_MACROS:
            named = target_platform.macro_arch({'__riscv_xlen': xlen, macro: '1'})

            assert named in target_platform.CANONICAL_ARCHS


def test_a_second_source_completes_an_answer_that_named_no_target():
    target = target_platform.CompilerTarget.from_triple('riscv64-linux-gnu', 'riscv64')

    assert target.completed_by('riscv64-lp64d').arch == 'riscv64-lp64d'


def test_a_second_source_never_overrides_an_answer_that_did():
    target = target_platform.CompilerTarget(arch='x86_64')

    assert target.completed_by('aarch64') is target


def test_a_second_source_contradicting_the_triple_is_dropped():
    # The triple ruled the family out, so an arch from anywhere else is not a
    # refinement of it. Keeping the triple's answer leaves the request to
    # settle it, rather than trusting the newer source.
    target = target_platform.CompilerTarget.from_triple('riscv64-linux-gnu', 'riscv64')

    assert target.completed_by('armv7-eabihf') is target
