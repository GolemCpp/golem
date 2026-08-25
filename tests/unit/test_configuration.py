import pytest
from types import SimpleNamespace

from golemcpp.golem import configuration
from golemcpp.golem.configuration import Configuration
from golemcpp.golem.condition import Condition
from golemcpp.golem.context import Context
from golemcpp.golem.dependency import Dependency


def test_configuration_json_roundtrip_preserves_language_standards():
    original = Configuration(c_standard='11', cxx_standard='20')

    payload = Configuration.serialize_to_json(original, avoid_lists=True)
    restored = Configuration.unserialize_from_json(payload)

    assert restored.c_standard == '11'
    assert restored.cxx_standard == '20'


def test_configuration_roundtrip_preserves_no_defaults():
    original = Configuration(no_defaults=True)

    payload = Configuration.serialize_to_json(original, avoid_lists=True)
    restored = Configuration.unserialize_from_json(payload)

    assert payload['no_defaults'] is True
    assert restored.no_defaults is True


def test_configuration_roundtrip_preserves_arflags():
    original = Configuration(arflags=['/machine:x64', '/debug'])

    payload = Configuration.serialize_to_json(original, avoid_lists=True)
    restored = Configuration.unserialize_from_json(payload)

    assert payload['arflags'] == ['/machine:x64', '/debug']
    assert restored.arflags == ['/machine:x64', '/debug']


def test_condition_deserializes_legacy_runtime_into_runtime_link():
    restored = Condition.unserialize_from_json({'runtime': 'static'})

    assert restored.runtime_link == ['static']
    assert restored.runtime_variant == []


def test_dependency_deserializes_legacy_runtime_into_runtime_link():
    restored = Dependency.unserialize_from_json({
        'name': 'demo',
        'repository': 'https://example.com/demo.git',
        'runtime': 'static',
    })

    assert restored.runtime_link == ['static']
    assert restored.runtime_variant == []


def test_configuration_serializes_runtime_link_and_runtime_variant():
    original = Configuration(runtime_link='static', runtime_variant='release')

    payload = Configuration.serialize_to_json(original, avoid_lists=True)

    assert payload['runtime_link'] == 'static'
    assert payload['runtime_variant'] == 'release'
    assert 'runtime' not in payload


def test_configuration_roundtrip_preserves_runtime_link_and_runtime_variant():
    original = Configuration(runtime_link='shared', runtime_variant='release')

    payload = Configuration.serialize_to_json(original, avoid_lists=True)
    restored = Configuration.unserialize_from_json(payload)

    assert restored.runtime_link == ['shared']
    assert restored.runtime_variant == ['release']


def test_when_accepts_legacy_runtime_keyword():
    config = Configuration()

    nested = config.when(runtime='static', defines=['USE_STATIC_RUNTIME'])

    assert nested.runtime_link == ['static']
    assert nested.runtime_variant == []


def test_configuration_merge_matches_runtime_link_and_runtime_variant():
    context = SimpleNamespace(
        variant=lambda: 'debug',
        link=lambda: 'shared',
        runtime_link=lambda: 'shared',
        runtime_variant=lambda: 'release',
        osname=lambda: 'windows',
        get_arch=lambda: 'x86_64',
        compiler_name=lambda: 'msvc',
        distribution=lambda: None,
        release=lambda: None,
    )
    base = Configuration()
    override = Configuration(runtime_link='shared', runtime_variant='release', defines=['USE_RELEASE_CRT'])

    merged = base.merge_copy(context=context, configs=[override])

    assert 'USE_RELEASE_CRT' in merged.defines


def test_configuration_merge_rejects_non_matching_runtime_variant():
    context = SimpleNamespace(
        variant=lambda: 'debug',
        link=lambda: 'shared',
        runtime_link=lambda: 'shared',
        runtime_variant=lambda: 'debug',
        osname=lambda: 'windows',
        get_arch=lambda: 'x86_64',
        compiler_name=lambda: 'msvc',
        distribution=lambda: None,
        release=lambda: None,
    )
    base = Configuration()
    override = Configuration(runtime_link='shared', runtime_variant='release', defines=['USE_RELEASE_CRT'])

    merged = base.merge_copy(context=context, configs=[override])

    assert 'USE_RELEASE_CRT' not in merged.defines


def test_configuration_append_overrides_language_standards():
    base = Configuration(c_standard='11', cxx_standard='17')
    override = Configuration(c_standard='17', cxx_standard='20')

    base.append(override)

    assert base.c_standard == '17'
    assert base.cxx_standard == '20'


def test_configuration_append_keeps_no_defaults_when_any_input_enables_it():
    base = Configuration(no_defaults=False)

    base.append(Configuration(no_defaults=True))

    assert base.no_defaults is True


def test_configuration_merge_copy_keeps_no_defaults_when_any_match_enables_it():
    context = SimpleNamespace(
        variant=lambda: 'debug',
        link=lambda: 'shared',
        runtime_link=lambda: 'shared',
        runtime_variant=lambda: 'debug',
        osname=lambda: 'linux',
        get_arch=lambda: 'x86_64',
        compiler_name=lambda: 'gcc',
        distribution=lambda: None,
        release=lambda: None,
    )
    base = Configuration()
    override = Configuration(variant='debug', no_defaults=True)

    merged = base.merge_copy(context=context, configs=[override])

    assert merged.no_defaults is True


def test_configuration_append_merges_arflags():
    base = Configuration(arflags=['/machine:x64'])

    base.append(Configuration(arflags=['/debug']))

    assert base.arflags == ['/machine:x64', '/debug']


@pytest.mark.parametrize(
    ('standard', 'compiler_name', 'expected_flag'),
    [
        ('11', 'gcc', '-std=c11'),
        ('gnu17', 'clang', '-std=gnu17'),
        ('17', 'msvc', '/std:c17'),
        ('latest', 'clang-cl', '/std:clatest'),
    ],
)
def test_make_c_standard_flag(standard, compiler_name, expected_flag):
    assert Context.make_c_standard_flag(standard, compiler_name) == expected_flag


@pytest.mark.parametrize(
    ('standard', 'compiler_name', 'expected_flag'),
    [
        ('20', 'gcc', '-std=c++20'),
        ('gnu++23', 'clang', '-std=gnu++23'),
        ('17', 'msvc', '/std:c++17'),
        ('23', 'clang-cl', '/std:c++latest'),
    ],
)
def test_make_cxx_standard_flag(standard, compiler_name, expected_flag):
    assert Context.make_cxx_standard_flag(standard, compiler_name) == expected_flag


def test_strip_language_standard_flags_removes_existing_standard_flags():
    flags = ['-O2', '-std=c++17', '/std:c++20', '-Wall']

    assert Context.strip_language_standard_flags(flags, language='cxx') == ['-O2', '-Wall']


def test_make_cxx_standard_flag_rejects_unsupported_msvc_standard():
    with pytest.raises(RuntimeError, match=r"Unsupported C\+\+ standard"):
        Context.make_cxx_standard_flag('12', 'msvc')

# --- The condition vocabulary ------------------------------------------


def make_matching_context(*, osname, arch):
    return SimpleNamespace(
        variant=lambda: 'debug',
        link=lambda: 'shared',
        runtime_link=lambda: 'shared',
        runtime_variant=lambda: 'debug',
        osname=lambda: osname,
        get_arch=lambda: arch,
        compiler_name=lambda: 'gcc',
        distribution=lambda: None,
        release=lambda: None,
    )


@pytest.mark.parametrize('written, canonical', [
    ('x64', 'x86_64'),
    ('amd64', 'x86_64'),
    ('arm64', 'aarch64'),
    ('x86', 'i686'),
])
def test_an_architecture_condition_is_stored_canonically(written, canonical):
    # A condition and a build meet only as strings, so a recipe saying x64 has
    # to become the word the context reports or it silently stops matching.
    assert Condition(arch=[written]).arch == [canonical]


@pytest.mark.parametrize('written, canonical', [
    ('osx', 'macos'),
    ('darwin', 'macos'),
    ('Windows', 'windows'),
])
def test_an_operating_system_condition_is_stored_canonically(written,
                                                             canonical):
    assert Condition(osystem=[written]).osystem == [canonical]


def test_the_keyword_form_normalizes_too():
    # when(arch=...) reaches parse_entry rather than the constructor, and it
    # is the form every recipe actually uses.
    condition = Condition()
    condition.parse_entry('arch', 'x64')
    condition.parse_entry('osystem', 'osx')

    assert condition.arch == ['x86_64']
    assert condition.osystem == ['macos']


def test_a_condition_written_before_the_rename_still_matches():
    # Restoring from JSON goes through parse_entry as well, so a cookbook or
    # artifact recorded with the old spelling is normalized on the way in
    # instead of needing a migration.
    condition = Condition.unserialize_from_json({
        'arch': ['x64'],
        'osystem': 'osx',
    })

    assert condition.arch == ['x86_64']
    assert condition.osystem == ['macos']


def test_a_serialized_configuration_normalizes_on_the_way_back_in():
    # Configuration.read_json delegates to Condition's before its own, so a
    # cookbook or artifact recorded with the old spelling needs no migration.
    config = Configuration.unserialize_from_json({
        'arch': ['x64'],
        'osystem': ['osx'],
        'defines': ['D'],
    })

    assert config.arch == ['x86_64']
    assert config.osystem == ['macos']


def test_an_old_spelling_still_selects_a_configuration():
    # The whole point, end to end: an unmigrated recipe against a context that
    # now reports the canonical names.
    context = make_matching_context(osname='macos', arch='x86_64')
    override = Configuration(osystem=['osx'], arch=['x64'],
                             defines=['LEGACY_SPELLING'])

    merged = Configuration().merge_copy(context=context, configs=[override])

    assert 'LEGACY_SPELLING' in merged.defines


@pytest.mark.parametrize('key, arch, osystem', [
    ('?x64', ['x86_64'], []),
    ('?aarch64', ['aarch64'], []),
    ('?arm64+linux', ['aarch64'], ['linux']),
    ('?osx', [], ['macos']),
])
def test_the_shorthand_form_reads_the_whole_vocabulary(key, arch, osystem):
    # It used to know four words: x86, x64, windows, linux and osx. Anything
    # else fell through and the condition quietly did nothing.
    config = Configuration().parse_special_entry(key, {})[0]

    assert config.arch == arch
    assert config.osystem == osystem


def test_a_negated_architecture_stays_negated():
    # arch was the only axis of nine appending the modifier-stripped word, so
    # '?!x64' recorded 'x64' and matched exactly what it excluded.
    config = Configuration().parse_special_entry('?!x64', {})[0]

    assert config.arch == ['!x86_64']


def test_an_unknown_condition_is_reported_rather_than_dropped(monkeypatch):
    # Silence here means a condition nobody can satisfy, and if it is the only
    # entry the whole block goes with it.
    warnings = []
    monkeypatch.setattr(configuration.Logs, 'warn',
                        lambda message, *args: warnings.append(message))

    assert Configuration().parse_special_entry('?sparc99', {}) == []
    assert len(warnings) == 1
    assert 'sparc99' in warnings[0]


def test_an_expression_is_left_for_the_evaluator():
    # Normalizing a whole value would mangle it. No recipe writes one, and
    # intersection() composes them out of values normalized on the way in.
    assert Condition(arch=['(x64+arm64)']).arch == ['(x64+arm64)']
