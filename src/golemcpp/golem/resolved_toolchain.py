"""
The toolchain a build was configured for, as a value rather than a `c4che/`.

When a project (parent) processes its dependencies (child), here is what happens:

1. A parent's configure finds its compiler and settles its arch. Then it hands down
both as `--resolved-compiler` and `--resolved-arch`.

2. A child's resolve uses them. No configure is performed yet.

3. A child's configure, needed before a build, must agree with what the parent handed
down before.

The root project has no parent, so nothing is told and nothing is checked. Its resolve
reads the `c4che/` its own configure wrote.
"""

from dataclasses import dataclass

from waflib.ConfigSet import ConfigSet

from golemcpp.golem import target_platform


def parse_compiler(value):
    """
    Parse the compiler name and version out of `gcc-15.2.0`, as `compiler()` renders it.

    The split is on the last `-`, since `clang-cl-17.0.1` has two.

    The version is returned the way waf's `CC_VERSION` holds it, a tuple of strings.
    """
    name, separator, version = value.rpartition("-")
    if not separator or not name or not version:
        raise ValueError(
            "A resolved compiler is spelled <name>-<version>, got {!r}".format(value)
        )
    return name, tuple(version.split("."))


@dataclass(frozen=True)
class ResolvedToolchain:
    # As `compiler()` renders it: <name>-<version>, the slug's compiler field.
    compiler: str
    # Canonical, the way `restore_options_env` normalizes one read back from
    # `c4che/`, so nothing downstream parses it again.
    arch: str

    def __post_init__(self):
        parse_compiler(self.compiler)
        if not self.arch:
            raise ValueError(
                "A resolved toolchain needs both its compiler and its arch, "
                "got {!r} and nothing".format(self.compiler)
            )
        object.__setattr__(self, "arch", target_platform.normalize_arch(self.arch))

    @classmethod
    def from_options(cls, options):
        """
        What the parent found, as told:
        - `--resolved-compiler`
        - `--resolved-arch`

        None when nothing was told, which is what happens for the root project.

        Not `--arch`, since that one is the request the child's configure confirms.
        """
        if not options.resolved_compiler and not options.resolved_arch:
            return None
        if not options.resolved_compiler or not options.resolved_arch:
            raise ValueError(
                "--resolved-compiler and --resolved-arch travel together: the "
                "parent settles both at configure and hands both down"
            )
        return cls(compiler=options.resolved_compiler, arch=options.resolved_arch)

    @classmethod
    def from_configure(cls, env, arch):
        """
        What this configure found:
        - the compiler waf probed into the env
        - the arch settled against it
        """
        return cls(compiler=env.CXX_NAME + "-" + ".".join(env.CC_VERSION), arch=arch)

    def environment(self):
        """
        The `ConfigSet` a resolve reads the compiler from.

        `CXX_NAME` and `CC_VERSION` are all what the condition evaluations and the
        build slug read.
        """
        name, version = parse_compiler(self.compiler)
        env = ConfigSet()
        env.CXX_NAME = name
        env.CC_VERSION = version
        return env

    def disagreements(self, other):
        """
        Where this toolchain differs from `other`, as `(name, mine, theirs)` triples,
        empty when they agree.
        """
        found = []
        if self.compiler != other.compiler:
            found.append(("the compiler", self.compiler, other.compiler))
        if self.arch != other.arch:
            found.append(("the architecture", self.arch, other.arch))
        return found
