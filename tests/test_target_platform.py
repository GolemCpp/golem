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
    spellings = list(target_platform.ARCH_ALIASES) + \
        list(target_platform.ARCH_FAMILY_DEFAULTS) + \
        list(target_platform.CANONICAL_ARCHS)
    for spelling in spellings:
        once = target_platform.normalize_arch(spelling)
        assert target_platform.normalize_arch(once) == once


def test_every_table_resolves_to_a_canonical_name():
    # An alias pointing at a name that is not in the vocabulary would be a typo
    # nobody notices until a build slug looks wrong.
    for table in (target_platform.ARCH_ALIASES,
                  target_platform.ARCH_FAMILY_DEFAULTS):
        for canonical in table.values():
            assert canonical in target_platform.CANONICAL_ARCHS

    for known in target_platform.ARCH_CAPABILITIES:
        assert known in target_platform.CANONICAL_ARCHS


def test_the_spellings_of_one_architecture_agree():
    # These used to disagree: the raw option reached the build slug while a
    # normalized copy reached everything else, so --arch=amd64 and
    # --arch=x86_64 built into two different directories.
    assert target_platform.normalize_arch('amd64') == \
        target_platform.normalize_arch('x86_64') == \
        target_platform.normalize_arch('x64') == 'x86_64'


def test_arm_answers_to_both_of_its_names():
    # Apple says arm64 and GNU says aarch64. Both have to arrive somewhere.
    assert target_platform.normalize_arch('arm64') == \
        target_platform.normalize_arch('aarch64') == 'aarch64'


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


def test_the_host_reports_something_usable():
    # Whatever this machine is, it has to have a name and it has to be canonical.
    arch = target_platform.host_arch()
    assert arch
    assert target_platform.normalize_arch(arch) == arch

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
    assert target_platform.normalize_osystem('Darwin') == \
        target_platform.normalize_osystem('osx') == \
        target_platform.normalize_osystem('macOS') == 'macos'
    assert target_platform.normalize_osystem('Win32') == 'windows'
    assert target_platform.normalize_osystem('iphoneos') == 'ios'


def arm_host(monkeypatch, machine, multiarch=None, loaders=()):
    '''A machine reporting `machine`, with whatever ABI evidence is given.'''
    monkeypatch.setattr(target_platform.platform, 'machine', lambda: machine)
    monkeypatch.setattr(target_platform.sysconfig, 'get_config_var',
                        lambda name: multiarch if name == 'MULTIARCH' else None)
    monkeypatch.setattr(target_platform.os.path, 'exists',
                        lambda path: path in loaders)


def test_an_isa_is_read_out_of_a_uname_string():
    # The trailing letter is byte order, not architecture. Fedora's 'h' is hard
    # float and worth keeping.
    assert target_platform.machine_isa('armv7l') == ('armv7', '')
    assert target_platform.machine_isa('armv6l') == ('armv6', '')
    assert target_platform.machine_isa('armv7hl') == ('armv7', 'eabihf')
    assert target_platform.machine_isa('x86_64') == ('x86_64', '')


# Measured, not invented: each row was read off a real userland running under
# QEMU, and the mappings they exercise were written from documentation. Keeping
# the observed values is what tells the two apart later.
#
#   image                          machine   MULTIARCH               loader
MEASURED_HOSTS = [
    ('arm32v7/python:3', 'armv7l', 'arm-linux-gnueabihf',
     '/lib/ld-linux-armhf.so.3', 'armv7-eabihf'),
    # The arm/v5 platform, which QEMU reports as armv7l regardless of the
    # image's baseline. It tests something better than armv5 as a result: the
    # same uname string as the row above with a different ABI, which is the
    # whole reason the two are worked out separately.
    ('arm32v5/python:3', 'armv7l', 'arm-linux-gnueabi',
     '/lib/ld-linux.so.3', 'armv7-eabi'),
    ('arm32v7/python:3-alpine', 'armv7l', 'arm-linux-musleabihf',
     '/lib/ld-musl-armhf.so.1', 'armv7-eabihf'),
    # RISC-V leaves the ABI out of the tuple — it is `riscv64-linux-gnu` either
    # way — and puts it in the loader's name instead.
    ('riscv64/python:3', 'riscv64', 'riscv64-linux-gnu',
     '/lib/ld-linux-riscv64-lp64d.so.1', 'riscv64-lp64d'),
    # The same arm/v5 platform as above, but with QEMU_CPU=arm926 so the
    # emulator stops claiming to be an ARMv7 part. This is what real armv5
    # hardware reports, and it is the row that earns the extension-letter
    # parsing: 'te' names ISA extensions and only the final 'l' is byte order.
    ('arm32v5/python:3 (QEMU_CPU=arm926)', 'armv5tel', 'arm-linux-gnueabi',
     '/lib/ld-linux.so.3', 'armv5-eabi'),
    # QEMU_CPU=arm1176 is the Raspberry Pi 1 core.
    ('arm32v6/alpine (QEMU_CPU=arm1176)', 'armv6l', 'arm-linux-musleabihf',
     '/lib/ld-musl-armhf.so.1', 'armv6-eabihf'),
]


@pytest.mark.parametrize('image, machine, multiarch, loader, expected',
                         MEASURED_HOSTS)
def test_a_real_userland_resolves(monkeypatch, image, machine, multiarch,
                                  loader, expected):
    arm_host(monkeypatch, machine, multiarch=multiarch, loaders=(loader,))
    assert target_platform.probe_host_arch() == expected, image


def test_the_loader_alone_is_enough_where_the_tuple_says_nothing(monkeypatch):
    # RISC-V is the case that proves the loader is not merely a fallback: its
    # multiarch tuple carries no ABI at all, so nothing else could answer.
    arm_host(monkeypatch, 'riscv64', multiarch='riscv64-linux-gnu',
             loaders=('/lib/ld-linux-riscv64-lp64d.so.1',))
    assert target_platform.multiarch_abi() == ''
    assert target_platform.probe_host_arch() == 'riscv64-lp64d'


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


def test_a_multiarch_tuple_settles_the_abi(monkeypatch):
    # Debian-family Python knows what it was built against, and it costs nothing
    # to ask.
    arm_host(monkeypatch, 'armv7l', multiarch='arm-linux-gnueabihf')
    assert target_platform.probe_host_arch() == 'armv7-eabihf'

    arm_host(monkeypatch, 'armv7l', multiarch='arm-linux-gnueabi')
    assert target_platform.probe_host_arch() == 'armv7-eabi'


def test_the_dynamic_loader_settles_it_where_the_tuple_is_absent(monkeypatch):
    # A system's loader is named for the ABI its binaries use, so its presence
    # is evidence rather than inference.
    arm_host(monkeypatch, 'armv6l', loaders=('/lib/ld-linux-armhf.so.3',))
    assert target_platform.probe_host_arch() == 'armv6-eabihf'

    arm_host(monkeypatch, 'armv7l', loaders=('/lib/ld-linux.so.3',))
    assert target_platform.probe_host_arch() == 'armv7-eabi'


def test_riscv_is_worked_out_the_same_way(monkeypatch):
    arm_host(monkeypatch, 'riscv64',
             loaders=('/lib/ld-linux-riscv64-lp64d.so.1',))
    assert target_platform.probe_host_arch() == 'riscv64-lp64d'


def test_an_abi_that_was_worked_out_is_not_thrown_away(monkeypatch):
    # riscv64-lp64 is a name this module knows and has nothing to say about:
    # no flags, no package name. That is no reason to discard it — the ABI was
    # established, and dropping back to a bare 'riscv64' would put the machine
    # under one identity while the same target asked for by name got another,
    # which is the confusion the probing exists to end.
    arm_host(monkeypatch, 'riscv64', multiarch='riscv64-linux-gnu',
             loaders=('/lib/ld-linux-riscv64-lp64.so.1',))

    assert target_platform.probe_host_arch() == 'riscv64-lp64'
    assert 'riscv64-lp64' not in target_platform.ARCH_CAPABILITIES


def test_a_machine_that_gives_up_nothing_keeps_its_own_name(monkeypatch):
    # No tuple, no loader, no hint in the uname string. Falling back to the raw
    # name is still a stable identity, which is all totality promises.
    arm_host(monkeypatch, 'armv7l')
    assert target_platform.probe_host_arch() == 'armv7l'


def test_an_unambiguous_machine_is_never_probed(monkeypatch):
    # x86_64 says everything about itself. Touching the filesystem to confirm it
    # would be work done for nothing on every single build.
    def fail(path):
        raise AssertionError('probed the filesystem for an unambiguous host')

    monkeypatch.setattr(target_platform.platform, 'machine', lambda: 'x86_64')
    monkeypatch.setattr(target_platform.os.path, 'exists', fail)
    assert target_platform.probe_host_arch() == 'x86_64'


def test_a_target_defaults_each_half_to_the_host():
    host = target_platform.TargetPlatform.host()

    assert target_platform.TargetPlatform.make() == host
    assert target_platform.TargetPlatform.make(arch=host.arch) == host
    # Spellings resolve on the way in, so asking by an alias is still the host.
    assert target_platform.TargetPlatform.make(
        osystem='darwin').osystem == 'macos'


def test_building_natively_is_fine_whatever_the_machine_is():
    # An architecture nobody here has heard of needs no flags to be built for,
    # because the compiler on it already targets it.
    host = target_platform.TargetPlatform.host()
    assert host.unsupported_reason() is None

    exotic = target_platform.TargetPlatform(osystem=target_platform.host_osystem(),
                                            arch=target_platform.host_arch())
    assert exotic.unsupported_reason() is None


def test_asking_for_an_architecture_golem_cannot_select_is_refused():
    # Without flags to select it the compiler would build for the host anyway,
    # and the artifact would carry the name of something that was never built.
    target = target_platform.TargetPlatform(
        osystem=target_platform.host_osystem(), arch='sparc64')

    reason = target.unsupported_reason()
    assert reason
    assert 'sparc64' in reason


def test_the_word_is_what_the_host_toolchain_can_select_not_any_toolchain(
        monkeypatch):
    # aarch64 has an MSVC mode but no GNU flag, because a native aarch64
    # compiler needs no flag and a cross one is chosen rather than told. Asking
    # for it on an x86_64 Linux host has to be refused: it is gcc that is about
    # to run, and gcc would quietly produce an x86_64 binary.
    monkeypatch.setattr(target_platform, 'host_osystem', lambda: 'linux')
    monkeypatch.setattr(target_platform, 'host_arch', lambda: 'x86_64')

    refused = target_platform.TargetPlatform(osystem='linux', arch='aarch64')
    assert refused.unsupported_reason()

    # Multilib is a different matter: -m32 does select it, so it stays allowed.
    allowed = target_platform.TargetPlatform(osystem='linux', arch='i686')
    assert allowed.unsupported_reason() is None


def test_msvc_cross_modes_stay_available_on_windows(monkeypatch):
    # MSVC really can target arm64 from an x64 host, so the same request that
    # is refused on Linux is fine here.
    monkeypatch.setattr(target_platform, 'host_osystem', lambda: 'windows')
    monkeypatch.setattr(target_platform, 'host_arch', lambda: 'x86_64')

    assert target_platform.TargetPlatform(
        osystem='windows', arch='aarch64').unsupported_reason() is None
    # i386 has no MSVC mode at all, so it is refused rather than quietly
    # becoming the i686 build MSVC would actually produce.
    assert target_platform.TargetPlatform(
        osystem='windows', arch='i386').unsupported_reason()


def test_asking_for_another_operating_system_is_refused_for_now():
    other = 'freebsd' if target_platform.host_osystem() != 'freebsd' else 'linux'
    target = target_platform.TargetPlatform(osystem=other, arch=target_platform.host_arch())

    reason = target.unsupported_reason()
    assert reason
    assert other in reason


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
