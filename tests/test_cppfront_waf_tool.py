from waflib.Tools import cppfront as waf_cppfront_tool


def test_parse_cpp_standard_major_digit_supports_previous_and_latest_and_future_aliases():
    assert waf_cppfront_tool.parse_cpp_standard_major_digit('/std:c++latest') == 'latest'
    assert waf_cppfront_tool.parse_cpp_standard_major_digit('-std=c++2b') == 2
    assert waf_cppfront_tool.parse_cpp_standard_major_digit('-std=gnu++2c') == 2
    assert waf_cppfront_tool.parse_cpp_standard_major_digit('/std:c++23') == 2
    assert waf_cppfront_tool.parse_cpp_standard_major_digit('/std:c++3y') == 3
    assert waf_cppfront_tool.parse_cpp_standard_major_digit('/std:c++17') == 1


def test_normalize_cppfront_cxxflags_removes_older_standards_and_preserves_supported_ones():
    flags = ['-O2', '-std=c++17', '/std:c++latest', '-Wall']

    normalized = waf_cppfront_tool.normalize_cppfront_cxxflags(flags, compiler_name='clang-cl')

    assert normalized == ['-O2', '/std:c++latest', '-Wall']


def test_normalize_cppfront_cxxflags_defaults_to_latest_for_msvc_like_compilers():
    flags = ['-O2', '/permissive-']

    normalized = waf_cppfront_tool.normalize_cppfront_cxxflags(flags, compiler_name='msvc')

    assert normalized == ['-O2', '/permissive-', '/std:c++20']


def test_normalize_cppfront_cxxflags_defaults_to_latest_equivalent_for_gnu_like_compilers():
    flags = ['-O2', '-Wall']

    normalized = waf_cppfront_tool.normalize_cppfront_cxxflags(flags, compiler_name='gcc')

    assert normalized == ['-O2', '-Wall', '-std=c++20']