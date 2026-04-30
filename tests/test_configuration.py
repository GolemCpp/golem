import pytest

from golemcpp.golem.configuration import Configuration
from golemcpp.golem.context import Context


def test_configuration_json_roundtrip_preserves_language_standards():
    original = Configuration(c_standard='11', cxx_standard='20')

    payload = Configuration.serialize_to_json(original, avoid_lists=True)
    restored = Configuration.unserialize_from_json(payload)

    assert restored.c_standard == '11'
    assert restored.cxx_standard == '20'


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