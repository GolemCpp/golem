import optparse

import pytest

from golemcpp.golem import resolved_toolchain
from golemcpp.golem.resolved_toolchain import ResolvedToolchain


def make_options(resolved_compiler=None, resolved_arch=None):
    # The request, which a told toolchain must not read as the result.
    return optparse.Values(
        dict(
            arch="riscv64",
            resolved_compiler=resolved_compiler,
            resolved_arch=resolved_arch,
        )
    )


@pytest.mark.parametrize(
    "value, name, version",
    [
        ("gcc-15.2.0", "gcc", ("15", "2", "0")),
        # Two hyphens: the split has to be on the last one.
        ("clang-cl-17.0.1", "clang-cl", ("17", "0", "1")),
        ("msvc-19.44", "msvc", ("19", "44")),
    ],
)
def test_a_resolved_compiler_splits_into_what_the_env_holds(value, name, version):
    assert resolved_toolchain.parse_compiler(value) == (name, version)


@pytest.mark.parametrize("value", ["gcc", "-15.2.0", "gcc-", ""])
def test_a_resolved_compiler_needs_both_halves(value):
    with pytest.raises(ValueError):
        resolved_toolchain.parse_compiler(value)


def test_the_told_toolchain_is_read_from_the_resolved_options_alone():
    told = ResolvedToolchain.from_options(
        make_options(resolved_compiler="gcc-15.2.0", resolved_arch="x86_64")
    )

    assert told == ResolvedToolchain(compiler="gcc-15.2.0", arch="x86_64")


def test_nothing_told_is_no_toolchain():
    # The root has no parent.
    assert ResolvedToolchain.from_options(make_options()) is None


@pytest.mark.parametrize(
    "resolved_compiler, resolved_arch", [("gcc-15.2.0", None), (None, "x86_64")]
)
def test_the_pair_travels_together(resolved_compiler, resolved_arch):
    with pytest.raises(ValueError):
        ResolvedToolchain.from_options(make_options(resolved_compiler, resolved_arch))


def test_the_arch_is_normalized_the_way_a_persisted_one_is():
    assert ResolvedToolchain(compiler="gcc-15.2.0", arch="x64").arch == "x86_64"


def test_the_found_toolchain_is_read_from_what_the_probe_left():
    env = ResolvedToolchain(compiler="clang-cl-17.0.1", arch="x86_64").environment()

    found = ResolvedToolchain.from_configure(env, "aarch64")

    assert found == ResolvedToolchain(compiler="clang-cl-17.0.1", arch="aarch64")


def test_the_environment_holds_the_compiler_and_nothing_else():
    # Everything a configure probes is absent, and waf's ConfigSet reads an
    # absent value as empty rather than failing, which is what condition
    # evaluation and the build slug rely on.
    env = ResolvedToolchain(compiler="gcc-15.2.0", arch="x86_64").environment()

    assert env.CXX_NAME == "gcc"
    assert env.CC_VERSION == ("15", "2", "0")
    assert env.CXX == []
    assert env.DEFINES == []


def test_a_toolchain_agreeing_with_its_parent_has_no_disagreement():
    told = ResolvedToolchain(compiler="gcc-15.2.0", arch="x64")
    found = ResolvedToolchain(compiler="gcc-15.2.0", arch="x86_64")

    assert found.disagreements(told) == []


def test_another_patch_level_is_another_compiler():
    # The slug embeds the full version, so exactness is the rule.
    told = ResolvedToolchain(compiler="gcc-15.2.0", arch="x86_64")
    found = ResolvedToolchain(compiler="gcc-15.2.1", arch="x86_64")

    assert found.disagreements(told) == [("the compiler", "gcc-15.2.1", "gcc-15.2.0")]


def test_both_can_disagree_and_both_are_named():
    told = ResolvedToolchain(compiler="gcc-15.2.0", arch="x86_64")
    found = ResolvedToolchain(compiler="clang-17.0.1", arch="aarch64")

    assert found.disagreements(told) == [
        ("the compiler", "clang-17.0.1", "gcc-15.2.0"),
        ("the architecture", "aarch64", "x86_64"),
    ]
