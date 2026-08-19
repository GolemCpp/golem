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
  default. That is a convenience for a person typing one only.
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

import enum
import platform
import re
import sys
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
# Android's armeabi-v7a, which is a third float ABI.
# It carries its own name rather than borrowing `eabi` so that a canonical name
# keeps fully determining ABI compatibility, without having to be read
# alongside the operating system to be understood.
ARCH_ARMV7_ANDROIDEABI = 'armv7-androideabi'
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
    ARCH_ARMV7_ANDROIDEABI,
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


# --- Reading an identity off a compiler's triple -------------------------


# The ABI a triple's last field names. A multiarch tuple is a triple too, so
# the same table serves `multiarch_abi` at the bottom of this file.
#
# The bare spellings are what a toolchain outside the glibc/musl world reports:
# `arm-none-eabi-gcc -dumpmachine` says `arm-none-eabi`. Listing a spelling is
# vocabulary and says nothing about whether the target can be built yet.
ABI_BY_TRIPLE_SUFFIX = {
    'gnueabihf': 'eabihf',
    'musleabihf': 'eabihf',
    'eabihf': 'eabihf',
    'gnueabi': 'eabi',
    'musleabi': 'eabi',
    'eabi': 'eabi',
    'androideabi': 'androideabi',
}

# Android writes the API level into the triple it is invoked with, e.g.
# `armv7a-linux-androideabi21`. That is a real part of the target, but it is a
# *different axis* from the ABI. The same shape as a macOS deployment target
# or a _WIN32_WINNT floor. So it is removed before this lookup rather than
# folded into an architecture's name.
#
# Not verified against a real NDK: it costs nothing if -dumpmachine turns out
# to echo the triple back without the level.
TRIPLE_SUFFIX_LEVEL = re.compile(r'\d+$')

# Arch fields that name a *family* and are never a target on their own, for
# two different reasons.
#
# `arm` is the whole 32-bit line at once: a triple saying it has not said
# whether it means armv5, armv6 or armv7, and no capability could be selected
# from it. What it is missing is an ISA level, which uname can supply.
#
# The rest are missing an *ABI*, and their triples cannot supply one either:
# `riscv64-linux-gnu` is the tuple for both lp64 and lp64d, and lp64 is soft
# float, so the two do not link. Passing the bare name through would put a
# target into a build slug that is not a target, and would refuse an explicit
# --arch=riscv64-lp64d for disagreeing with its own compiler.
FAMILY_ARCH_FIELDS = ('arm', 'mips64el', 'riscv32', 'riscv64')

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


@dataclass(frozen=True)
class Triple:
    '''
    A target triple, split into the fields Golem reads.

    Four fields despite the name, `<arch>-<vendor>-<sys>-<abi>`: the
    three-field form came first, the vendor was added later, and the name
    stayed.

    TODO: Only the two ends are named here, because three fields is the common
    form and it is ambiguous. `x86_64-linux-gnu` leaves out the vendor,
    `aarch64-apple-darwin` the ABI, `arm-none-eabi` the system, and telling
    those apart needs tables of the vendors and systems that exist.
    '''

    fields: tuple = ()

    @staticmethod
    def parse(triple):
        '''Split what a compiler reported into its fields.'''
        fields = str(triple).strip().lower().split('-')
        return Triple(fields=tuple(fields) if fields[0] else ())

    @property
    def arch(self):
        '''
        The triple's arch field, which is a position rather than a claim.

        `arm` sits there as readily as `x86_64` does, so it may name a family
        that is not a target at all.
        '''
        return self.fields[0] if self.fields else ''

    @property
    def suffix(self):
        '''The last field, whichever of vendor, system and ABI it turned out to be.'''
        return self.fields[-1] if self.fields else ''

    def canonical_abi(self):
        '''
        Name the ABI in Golem's vocabulary, or '' where the suffix names none.

        The two vocabularies differ, and the difference is the C library: a
        triple says `gnueabihf` and `musleabihf` where Golem says `eabihf` for
        both, because which libc was linked is not part of an architecture.

        What is left keeps a coarse triple useful rather than merely unusable.
        Cross-compiling to 32-bit ARM is the case that needs it: `arm-linux-
        gnueabihf` cannot say whether it means armv6 or armv7, so a request has
        to supply that, but it is emphatic about hard float and a request
        claiming soft float against it is wrong.
        '''
        return ABI_BY_TRIPLE_SUFFIX.get(
            TRIPLE_SUFFIX_LEVEL.sub('', self.suffix), '')

    def canonical_arch(self, machine=None):
        '''
        Compose the canonical architecture this triple names, or '' for none.

        Two sources, because neither is enough alone. `-dumpmachine` on an
        armv7 toolchain answers `arm-linux-gnueabihf`: it settles the ABI,
        which uname cannot report, and gives only `arm` for the ISA level,
        which uname does. So the ABI comes from the triple and the ISA level
        from the machine, which is the split `<isa>-<abi>` was spelled for.

        Borrowing the ISA level from uname is only sound while the compiler
        builds for the machine running it, therefore a cross toolchain, whose
        triple describes one machine and uname another, gets nothing.

        An architecture that is complete but simply not one of Golem's
        canonical names passes through unchanged: `sparc64` is an identity,
        `arm` is not.
        '''
        field = self.arch
        if not field:
            return ''

        named = normalize_arch(field)
        # A triple whose arch field is already a canonical name needs nothing
        # else: x86_64, aarch64 and i686 carry no ABI to recover.
        if named in CANONICAL_ARCHS:
            return named

        # What to say if the pieces do not come together: a name for a field
        # that stands on its own, nothing for one that names a family.
        incomplete = '' if field in FAMILY_ARCH_FIELDS else named

        # The triple's own arch field wins where it carries an ISA level of its
        # own (`armv7a-...`); otherwise only uname knows which one this is, and
        # only when it is describing the machine being built for.
        isa, _ = machine_isa(field)
        if isa == field and field in FAMILY_ARCH_FIELDS:
            isa, _ = machine_isa(
                platform.machine() if machine is None else machine)
            if not isa.startswith(field):
                return incomplete

        abi = self.canonical_abi()
        if not abi:
            return incomplete

        resolved = normalize_arch('{}-{}'.format(isa, abi))
        return resolved if resolved in CANONICAL_ARCHS else incomplete


class Refusal(enum.Enum):
    '''
    Why a compiler will not build a requested architecture.

    A discriminant and nothing more. The words belong to whoever is writing the
    message, and the value each one is about is a field of `CompilerTarget`.
    '''

    # It named its target outright, and the request is a different target.
    ARCH = enum.auto()
    # It named a family, and the request belongs to another one.
    FAMILY = enum.auto()
    # It named an ABI, and the request wants the other. This is not a
    # preference: objects built for one ABI do not link with objects built for
    # the other, so there is no artifact that would satisfy both.
    ABI = enum.auto()


@dataclass(frozen=True)
class CompilerTarget:
    '''
    What the selected compiler said about what it builds for.

    Three fields because a compiler answers at three levels of precision and
    every one of them is usable. `x86_64-linux-gnu` names a target outright.
    `arm-linux-gnueabihf` names a family and an ABI but no ISA level, since
    only uname has that and uname may be describing another machine. Empty is
    a compiler that could not be got to answer at all, which is a state too.
    '''

    arch: str = ''
    family: str = ''
    abi: str = ''

    @staticmethod
    def from_triple(triple, machine=None):
        parsed = Triple.parse(triple)
        return CompilerTarget(arch=parsed.canonical_arch(machine),
                              family=parsed.arch,
                              abi=parsed.canonical_abi())

    @property
    def answered(self):
        '''Whether the compiler said anything at all about what it builds for.'''
        return bool(self.arch or self.family or self.abi)

    @staticmethod
    def from_arch(arch):
        '''
        For a compiler that reports its target without a triple.

        MSVC is the case: waf records the target of the installation it found,
        which is a whole answer rather than a partial one.
        '''
        return CompilerTarget(arch=normalize_arch(arch))

    def refusal(self, arch):
        '''
        Say why this compiler will not build `arch`, or None if it will.

        One rule read at whatever precision is available. A compiler that named
        its target admits only that target. One that named a family and an ABI
        admits anything in the family sharing the ABI, which is how a request
        supplies an ISA level that a cross toolchain's triple could not.
        '''
        if self.arch:
            return Refusal.ARCH if arch != self.arch else None

        isa, carries_abi, abi = arch.rpartition('-')

        if self.family and not (isa or abi).startswith(self.family):
            return Refusal.FAMILY

        if self.abi and (abi if carries_abi else '') != self.abi:
            return Refusal.ABI

        return None

    def settle(self, requested):
        '''
        Reconcile what the compiler reported with what was requested.

        Returns an architecture when the two are compatible
        
        Returns a refusal when they aren't compatible.
        
        There is no refusal if both are empty, because the request settles
        what the compiler left open.
        '''
        if requested:
            refusal = self.refusal(requested)
            if refusal:
                return '', refusal

        return self.arch or requested, None


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

    Both halves are required, because there is no valid default. A target that
    was never decided in the first place reaches a build slug and an advertisement,
    where it becomes a claim about an artifact that may not be true.
    '''

    osystem: str
    arch: str

    def __post_init__(self):
        # Normalizing in the constructor rather than around it is what makes the
        # canonical form an invariant of the type: a target built any other way
        # cannot carry a spelling that would reach a build slug unnormalized,
        # which is the failure this whole model exists to remove.
        object.__setattr__(self, 'osystem', normalize_osystem(self.osystem))
        object.__setattr__(self, 'arch', normalize_arch(self.arch))

    @property
    def capability(self):
        return arch_capability(self.arch)
