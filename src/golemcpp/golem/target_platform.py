'''
What a build is *for*: an operating system and an architecture.

**Identity** is the canonical name. It is *total*: every input maps to a stable
string, and an architecture nobody here has heard of keeps its own name rather
than becoming nothing. Identity is what ends up in a build slug and in what a
built artifact advertises about itself, so it has to exist for every target,
including the ones this file does not recognise.

**Capability** is what a target implies for the toolchain. E.g. which flags
select it, what the linker calls it, how a package manager spells it. It is
*partial* by nature, and an unknown architecture simply has none. That is a
sound answer rather than a missing one: a compiler invoked with no architecture
flag builds for its own default, which on a native build is exactly what was
wanted.

Canonical names follow LLVM triple spelling, because that is the vocabulary
cross toolchains actually accept. Where an ABI is part of a target's identity
it is folded into the name as `<isa>-<abi>`, so the two can be recovered later
by splitting on the last hyphen without consulting a table.

Three ways a name can be many-to-one, and only the first is an alias:

- **Spellings** of one target. `amd64`, `x64` and `EM64T` are all `x86_64`;
  Apple says `arm64` where GNU says `aarch64`. Nothing is lost.
- **Family names**, which are not targets at all. `x86` and `ia32` name the
  32-bit line rather than a member of it, so they resolve to a documented
  default. That is a convenience, not an equivalence.
- **Sub-architectures**, which are *not* interchangeable and so are not
  collapsed. i486 adds `xadd` and `bswap`, i586 adds `cmpxchg8b`, i686 adds
  `cmov`; an i686 binary raises SIGILL on a 486, and a cross toolchain exists
  for each. The same care applies to ABI variants: `riscv64` alone does not say
  whether floats go in registers, and guessing picks a link-incompatible answer.

A note for when several architectures are built at once, since it is the reason
this model stays scalar rather than becoming a list: **Golem never merges.**
Clang takes several `-arch` flags in one invocation, compiles each slice itself
and emits a single fat binary, so a universal target is just one more
architecture whose capability happens to name two. Where a toolchain cannot do
that on its own and would need a separate merge step, the scenario is
unsupported rather than reimplemented here.
'''

import os
import platform
import re
import sys
import sysconfig
from dataclasses import dataclass


# --- Operating system ---------------------------------------------------

OS_WINDOWS = 'windows'
OS_LINUX = 'linux'
OS_MACOS = 'macos'
OS_IOS = 'ios'
OS_TVOS = 'tvos'
OS_WATCHOS = 'watchos'
OS_ANDROID = 'android'
OS_FREEBSD = 'freebsd'
OS_OPENBSD = 'openbsd'
OS_NETBSD = 'netbsd'
OS_SOLARIS = 'solaris'
OS_WASI = 'wasi'
OS_EMSCRIPTEN = 'emscripten'

# Every operating system that can be named, whether or not Golem can currently
# build for it. Naming one is what lets a recipe say a target is only for that
# system, so the vocabulary is useful ahead of the toolchain support.
CANONICAL_OSYSTEMS = (
    OS_WINDOWS,
    OS_LINUX,
    OS_MACOS,
    OS_IOS,
    OS_TVOS,
    OS_WATCHOS,
    OS_ANDROID,
    OS_FREEBSD,
    OS_OPENBSD,
    OS_NETBSD,
    OS_SOLARIS,
    OS_WASI,
    OS_EMSCRIPTEN,
)

# Spellings a person might reasonably type, or another tool might report. 'osx'
# is what Golem itself said before macOS was renamed, so it has to keep working.
#
# Note what is deliberately absent. There is no `cygwin` here: a Cygwin binary
# links cygwin1.dll but cannot run as a native Windows one. Leaving it to pass
# through under its own name, and the same holds for anything else that emulates
# a system rather than being it.
OS_ALIASES = {
    'win': OS_WINDOWS,
    'win32': OS_WINDOWS,
    'win64': OS_WINDOWS,
    'osx': OS_MACOS,
    'macosx': OS_MACOS,
    'mac': OS_MACOS,
    'darwin': OS_MACOS,
    'iphoneos': OS_IOS,
    # What Solaris and its illumos descendants report once the release
    # digits are off `sunos5`.
    'sunos': OS_SOLARIS,
}


def normalize_osystem(name):
    '''The canonical name for an operating system. Total, like normalize_arch.'''
    if not name:
        return ''
    cleaned = str(name).strip().lower()
    return OS_ALIASES.get(cleaned, cleaned)


def host_osystem():
    '''
    The operating system Golem is running on.

    `sys.platform` carries a version on several systems (e.g. freebsd14, openbsd7,
    sunos5) and a version has no business in an operating system's name. The digits
    are dropped.
    '''
    if sys.platform.startswith('win32'):
        return OS_WINDOWS
    if sys.platform.startswith('linux'):
        return OS_LINUX
    if sys.platform.startswith('darwin'):
        return OS_MACOS
    return normalize_osystem(sys.platform.rstrip('0123456789'))


# --- Architecture -------------------------------------------------------

ARCH_X86_64 = 'x86_64'
ARCH_I386 = 'i386'
ARCH_I486 = 'i486'
ARCH_I586 = 'i586'
ARCH_I686 = 'i686'
ARCH_AARCH64 = 'aarch64'
ARCH_AARCH64_ILP32 = 'aarch64-ilp32'
ARCH_ARMV5_EABI = 'armv5-eabi'
ARCH_ARMV6_EABIHF = 'armv6-eabihf'
ARCH_ARMV7_EABI = 'armv7-eabi'
ARCH_ARMV7_EABIHF = 'armv7-eabihf'
ARCH_RISCV32_ILP32 = 'riscv32-ilp32'
ARCH_RISCV64_LP64 = 'riscv64-lp64'
ARCH_RISCV64_LP64D = 'riscv64-lp64d'
ARCH_PPC64LE = 'ppc64le'
ARCH_S390X = 's390x'
ARCH_MIPS64EL_N64 = 'mips64el-n64'
ARCH_WASM32 = 'wasm32'
ARCH_LOONGARCH64 = 'loongarch64'

CANONICAL_ARCHS = (
    ARCH_X86_64,
    ARCH_I386,
    ARCH_I486,
    ARCH_I586,
    ARCH_I686,
    ARCH_AARCH64,
    ARCH_AARCH64_ILP32,
    ARCH_ARMV5_EABI,
    ARCH_ARMV6_EABIHF,
    ARCH_ARMV7_EABI,
    ARCH_ARMV7_EABIHF,
    ARCH_RISCV32_ILP32,
    ARCH_RISCV64_LP64,
    ARCH_RISCV64_LP64D,
    ARCH_PPC64LE,
    ARCH_S390X,
    ARCH_MIPS64EL_N64,
    ARCH_WASM32,
    ARCH_LOONGARCH64,
)

# Different spellings of the same target, nothing more. This serves two callers
# that used to have separate code paths: what `platform.machine()` reports about
# the host, and what a person types after `--arch`.
#
# Note what is absent. There is no `riscv64` here, because the bare name does
# not say which floating-point ABI is meant and the two do not link together.
# There is no `armhf` or `armel` either: those are Debian *port* names, and they
# belong in the packaging direction only.
ARCH_ALIASES = {
    'x86-64': ARCH_X86_64,
    'x64': ARCH_X86_64,
    'amd64': ARCH_X86_64,
    'em64t': ARCH_X86_64,

    'arm64': ARCH_AARCH64,

    'powerpc64le': ARCH_PPC64LE,
}

# Names for a *family* rather than a member of it, resolved to a documented
# default. Kept apart from the aliases above because this is a convenience and
# not a statement that the names mean the same thing.
#
# Both point at i686 despite `ia32` reading, etymologically, like the whole
# 32-bit line starting at the 386. Every toolchain that uses the token in
# practice (e.g. Node's process.arch, Electron's --arch, Chromium's target_cpu)
# means i686-class, and splitting the two would let names the ecosystem treats
# as synonyms produce silently incompatible builds. Anyone who wants 386
# baseline can now say `i386` and get exactly that.
ARCH_FAMILY_DEFAULTS = {
    'x86': ARCH_I686,
    'ia32': ARCH_I686,
}


def normalize_arch(name):
    '''
    The canonical name for an architecture.

    Total by design. An architecture this file has never heard of keeps its own
    lowercased name instead of becoming None, because identity has to exist for
    every target even where capability does not.
    '''
    if not name:
        return ''
    cleaned = str(name).strip().lower()
    if cleaned in ARCH_ALIASES:
        return ARCH_ALIASES[cleaned]
    return ARCH_FAMILY_DEFAULTS.get(cleaned, cleaned)


def host_arch():
    '''
    The canonical architecture Golem is running on, as the machine reports it.

    Deliberately no more than that. Where an architecture's identity includes an
    ABI, uname cannot supply one, and the answer comes from the compiler that
    ends up being used rather than from anything guessed here.
    '''
    return normalize_arch(platform.machine())


@dataclass(frozen=True)
class ArchCapability:
    '''
    What an architecture implies for the tools that build for it.

    Every field is optional. An architecture with no entry gets an instance of
    this with everything empty, which means "say nothing and let the toolchain
    use its own default".

    Empty is also the honest answer where a toolchain genuinely cannot reach a
    target: MSVC has no 80386 mode, so i386 carries GNU flags and a package name
    but none of the Visual Studio fields.
    '''

    # Selects the architecture for gcc and clang, on both compile and link.
    #
    # Empty does not mean no such flag exists. For ARM and RISC-V one does.
    # It means the platform ships no userland for the other target, so the flag
    # would compile something that cannot then be linked. Whether a flag
    # belongs here is a question about how a platform is deployed, not about
    # what its compiler accepts. See the aarch64 and armv7 entries.
    gnu_flags: tuple = ()
    # waf's MSVC_TARGETS value: the first element of its all_msvc_platforms
    # pairs, not the second.
    msvc_target: str = ''
    # The argument vcvarsall.bat wants, which is the *second* element of those
    # same pairs and is spelled differently from the first for x86_64.
    vcvars_arg: str = ''
    # Suffix for the MSVC linker's /MACHINE: flag.
    msvc_machine: str = ''
    # Visual Studio's own name for the platform, used by MSBuild's /p:Platform
    # and by CMake's -A. Note 32-bit is 'Win32' here and nothing else.
    vs_platform: str = ''
    # How Debian and the packaging tools that follow it spell this.
    debian_arch: str = ''


# A selecting flag belongs here exactly when the toolchain ships libraries for
# the target it selects. E.g. an x86 distribution installs a 32-bit userland
# beside the 64-bit one, so `-m32` has somewhere to link, while an ARM
# distribution ships two separate toolchains instead, so the equivalent flag
# would compile something with nothing to link against. A multilib bare-metal
# toolchain would flip ARM back the other way. See the armv7 entry.
#
# `-m32` on its own gives the compiler's own 32-bit baseline, which on anything
# modern is already i686. So only the older members of the family need to name
# a baseline explicitly.
ARCH_CAPABILITIES = {
    ARCH_X86_64: ArchCapability(
        gnu_flags=('-m64',),
        msvc_target='x64',
        vcvars_arg='amd64',
        msvc_machine='X64',
        vs_platform='x64',
        debian_arch='amd64',
    ),
    ARCH_I686: ArchCapability(
        gnu_flags=('-m32',),
        msvc_target='x86',
        vcvars_arg='x86',
        msvc_machine='X86',
        vs_platform='Win32',
        debian_arch='i386',
    ),
    ARCH_I586: ArchCapability(
        gnu_flags=('-m32', '-march=i586'),
        debian_arch='i386',
    ),
    ARCH_I486: ArchCapability(
        gnu_flags=('-m32', '-march=i486'),
        debian_arch='i386',
    ),
    ARCH_I386: ArchCapability(
        gnu_flags=('-m32', '-march=i386'),
        debian_arch='i386',
    ),
    ARCH_AARCH64: ArchCapability(
        # No GNU flag, and not for want of one existing. What decides an
        # aarch64 build is which compiler was found: distributions ship a
        # separate toolchain rather than a multilib one, so there is no aarch64
        # userland sitting beside an x86_64 one for a flag to reach.
        #
        # MSVC is the other way round, which is why its fields are filled in:
        # one installation carries several targets and MSVC_TARGETS picks among
        # them, so naming one selects a toolchain that is really there.
        msvc_target='arm64',
        vcvars_arg='arm64',
        msvc_machine='ARM64',
        vs_platform='ARM64',
        debian_arch='arm64',
    ),
    # -mfloat-abi=hard, soft and softfp all exist and none of them belongs here,
    # which is a statement about Linux rather than about ARM. A distribution's
    # arm-linux-gnueabihf-gcc ships one set of libraries, so overriding its
    # default compiles cleanly and then fails to link, and a flag that produces
    # an unlinkable object is worse than no flag at all.
    #
    # The same flag is essential on a multilib toolchain, where it is not an
    # override but the ordinary way to choose: arm-none-eabi-gcc carries libgcc
    # and newlib built several times over and -mfloat-abi picks which set is
    # linked, exactly as -m32 does on x86 above. Should Golem ever target bare
    # metal, these entries gain flags rather than the rule changing.
    ARCH_ARMV7_EABIHF: ArchCapability(debian_arch='armhf'),
    ARCH_ARMV7_EABI: ArchCapability(debian_arch='armel'),
    ARCH_ARMV6_EABIHF: ArchCapability(debian_arch='armhf'),
    # Debian's armel port is armv5te and assumes no FPU, so soft float is the
    # only ABI it has.
    ARCH_ARMV5_EABI: ArchCapability(debian_arch='armel'),
    # -mabi=lp64 and -mabi=lp64d are the RISC-V equivalents, left out for the
    # same reason and subject to the same exception.
    ARCH_RISCV64_LP64D: ArchCapability(debian_arch='riscv64'),
    ARCH_PPC64LE: ArchCapability(debian_arch='ppc64el'),
    ARCH_S390X: ArchCapability(debian_arch='s390x'),
    ARCH_MIPS64EL_N64: ArchCapability(debian_arch='mips64el'),
    ARCH_LOONGARCH64: ArchCapability(debian_arch='loong64'),
}

NO_CAPABILITY = ArchCapability()


def arch_capability(arch):
    '''
    What is known about an architecture, or nothing at all.

    Never raises and never returns None: an unrecognised architecture gets an
    empty capability.
    '''
    return ARCH_CAPABILITIES.get(normalize_arch(arch), NO_CAPABILITY)


# --- The target ---------------------------------------------------------


@dataclass(frozen=True)
class TargetPlatform:
    '''
    What this build is for, as one value.

    It defaults to the host, and for now it can differ from the host only where
    the host's own compiler can be pointed somewhere else: a 32-bit build on a
    64-bit toolchain, one of MSVC's cross modes. Reaching a target that needs a
    *different* compiler is cross-compilation proper, and that waits until
    choosing the toolchain is part of configuring the build.

    Note this describes the target, not whether it happens to be reachable.
    `unsupported_reason` is the part that knows what Golem can currently do, and
    it is the part that will change as that grows.
    '''

    osystem: str
    arch: str

    def __post_init__(self):
        # Normalizing here rather than in the factories below is what makes the
        # canonical form an invariant of the type: a target built any other way
        # cannot carry a spelling that would reach a build slug unnormalized,
        # which is the failure this whole model exists to remove.
        object.__setattr__(self, 'osystem', normalize_osystem(self.osystem))
        object.__setattr__(self, 'arch', normalize_arch(self.arch))

    @staticmethod
    def host():
        return TargetPlatform(osystem=host_osystem(), arch=host_arch())

    @staticmethod
    def make(osystem=None, arch=None):
        '''
        A target from what was asked for, falling back to the host for whatever
        was not.
        '''
        return TargetPlatform(
            osystem=normalize_osystem(osystem) or host_osystem(),
            arch=normalize_arch(arch) or host_arch())

    @property
    def capability(self):
        return arch_capability(self.arch)

    def is_host(self):
        return self == TargetPlatform.host()

    def unsupported_reason(self):
        '''
        Why this target cannot be built, or None when it can.

        Building for the host is always fine, whatever the host is. A native
        compiler already targets its own machine.

        Building for anything else is only possible where the compiler that is
        actually going to run can be *told* to do it. E.g. `-m32` on a GNU
        multilib toolchain, one of MSVC's cross modes on Windows. Where it
        cannot, the request has to be refused rather than honoured silently.

        Which is why this asks what the *host's* toolchain can select, not
        whether any toolchain anywhere could. An aarch64 request on an x86_64
        Linux host is refused even though MSVC has an arm64 mode, because it is
        gcc that is about to run.

        This is everything that can be known before a compiler has been chosen,
        which is less than everything: the host's architecture is inferred here,
        and only the compiler finally selected can confirm it.
        '''
        if self.osystem != host_osystem():
            return (
                "Cannot build for '{}' on '{}': cross-compiling to another "
                "operating system is not supported yet".format(
                    self.osystem, host_osystem()))

        if self.arch == host_arch():
            return None

        capability = self.capability

        if host_osystem() == OS_WINDOWS:
            if not capability.msvc_target:
                return (
                    "Cannot build for '{}' on '{}': MSVC has no mode for that "
                    "architecture".format(self.arch, host_arch()))
            return None

        if not capability.gnu_flags:
            return (
                "Cannot build for '{}' on '{}': there is no compiler flag that "
                "selects it, so it would need a cross toolchain, which is not "
                "supported yet".format(self.arch, host_arch()))

        return None


# --- Working out the host's ABI without a compiler ----------------------
#
# None of this is called. It is kept on purpose.
#
# Eight of the canonical names carry an ABI and `platform.machine()` cannot
# report one: nothing in `armv7l` says whether floats travel in registers. This
# works it out from evidence the system already carries, using only a dictionary
# lookup and a stat, and it is right on every userland it was measured against.
#
# Instead of this heuristic, a compiler can be asked directly with `-dumpmachine`,
# and the compiler is the thing that decides, so once one has been found there is
# nothing left to infer. Keeping the heuristic costs nothing and answers the
# question in the one situation where asking is not possible: before any compiler
# exists.
#
# `machine_isa` will come back into use when the compiler is wired in, because
# `-dumpmachine` reports `arm-linux-gnueabihf`, whose first field is `arm` rather
# than `armv7`. The compiler settles the ABI; the ISA level still comes from
# uname.

# The ABI part of a multiarch tuple, e.g. 'arm-linux-gnueabihf'.
ABI_BY_MULTIARCH_SUFFIX = {
    'gnueabihf': 'eabihf',
    'musleabihf': 'eabihf',
    'gnueabi': 'eabi',
    'musleabi': 'eabi',
}

# A system's dynamic loader is named after the ABI its binaries use, so its
# presence is direct evidence rather than an inference.
ARM_LOADERS = (
    ('/lib/ld-linux-armhf.so.3', 'eabihf'),
    ('/lib/ld-musl-armhf.so.1', 'eabihf'),
    ('/lib/ld-linux.so.3', 'eabi'),
    ('/lib/ld-musl-arm.so.1', 'eabi'),
)

ABI_BY_LOADER = {
    'armv5': ARM_LOADERS,
    'armv6': ARM_LOADERS,
    'armv7': ARM_LOADERS,
    # RISC-V puts the ABI in the loader's own name and leaves it out of the
    # multiarch tuple, which is `riscv64-linux-gnu` either way — so here the
    # loader is not a fallback, it is the only thing that knows.
    'riscv64': (('/lib/ld-linux-riscv64-lp64d.so.1', 'lp64d'),
                ('/lib/ld-linux-riscv64-lp64.so.1', 'lp64')),
    'riscv32': (('/lib/ld-linux-riscv32-ilp32d.so.1', 'ilp32'),
                ('/lib/ld-linux-riscv32-ilp32.so.1', 'ilp32')),
}

# Only these have to be worked out. An architecture whose uname string is
# already canonical is left alone.
DEFAULT_ABI = {
    'mips64el': 'n64',
}

MACHINE_ISA_PATTERN = re.compile(r'^arm(v\d+)([a-z]*)$')


def machine_isa(machine):
    '''
    The instruction set a uname machine string names, and any ABI it lets slip.

    32-bit ARM is reported with a tail of letters that are not all the same kind
    of thing. `armv7l` ends in byte order. `armv5tel` names two ISA extensions
    before it. `armv7hl` slips in an `h` that says hard float outright, which is
    the only one of them worth keeping.
    '''
    cleaned = str(machine).strip().lower()
    match = MACHINE_ISA_PATTERN.match(cleaned)
    if not match:
        return cleaned, ''

    version, extensions = match.groups()
    if extensions.endswith(('l', 'b')):
        extensions = extensions[:-1]
    return 'arm' + version, 'eabihf' if extensions.endswith('h') else ''


def multiarch_abi():
    '''The ABI named by the tuple Python itself was built against, if any.'''
    for name in ('MULTIARCH', 'HOST_GNU_TYPE'):
        tuple_name = sysconfig.get_config_var(name)
        if not tuple_name:
            continue
        suffix = str(tuple_name).rsplit('-', 1)[-1].lower()
        if suffix in ABI_BY_MULTIARCH_SUFFIX:
            return ABI_BY_MULTIARCH_SUFFIX[suffix]
    return ''


def loader_abi(isa):
    '''The ABI of whichever dynamic loader this system actually has.'''
    for path, abi in ABI_BY_LOADER.get(isa, ()):
        if os.path.exists(path):
            return abi
    return ''


def probe_host_arch():
    '''
    What `host_arch` would say if the ABI had to be inferred rather than asked.

    The whole heuristic in one place, so it stays exercised and stays honest.
    '''
    machine = platform.machine()
    named = normalize_arch(machine)
    # Knowing the name is the question, not knowing what to do with it: an
    # architecture can be perfectly well named here and carry no capability,
    # and gating on the capabilities would throw away an ABI just worked out.
    if named in CANONICAL_ARCHS:
        return named

    isa, abi_from_machine = machine_isa(machine)
    abi = (abi_from_machine or multiarch_abi() or loader_abi(isa)
           or DEFAULT_ABI.get(isa, ''))
    if not abi:
        return named

    resolved = normalize_arch('{}-{}'.format(isa, abi))
    return resolved if resolved in CANONICAL_ARCHS else named
