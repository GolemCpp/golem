import pytest
from types import SimpleNamespace

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
        arch=lambda: 'x64',
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
        arch=lambda: 'x64',
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