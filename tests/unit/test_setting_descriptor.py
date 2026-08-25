import pytest

from golemcpp.golem.setting_descriptor import has_value
from golemcpp.golem.setting_descriptor import SettingDescriptor
from golemcpp.golem.setting_descriptor import SettingType


def _setting(value_type=SettingType.STRING, **kwargs):
    return SettingDescriptor(
        key='cache.directory',
        env_name='GOLEM_CACHE_DIRECTORY',
        option_name='cache_directory',
        description='',
        value_type=value_type,
        **kwargs)


def test_names_list_the_current_spelling_first():
    setting = _setting(
        legacy_keys=('cache.dir',),
        legacy_env_names=('GOLEM_CACHE_DIR',),
        legacy_option_names=('cache_dir',))

    assert setting.keys == ('cache.directory', 'cache.dir')
    assert setting.env_names == ('GOLEM_CACHE_DIRECTORY', 'GOLEM_CACHE_DIR')
    assert setting.option_names == ('cache_directory', 'cache_dir')
    assert setting.option_flag == '--cache-directory'


def test_a_setting_without_an_option_has_no_option_name_nor_flag():
    setting = SettingDescriptor(key='example.setting', env_name='GOLEM_EXAMPLE_SETTING',
                      description='')

    assert setting.option_names == ()
    assert setting.option_flag == ''


def test_get_default_calls_a_callable_default():
    calls = []

    def default():
        calls.append(1)
        return '/computed/cache'

    setting = _setting(default=default)

    assert setting.get_default() == '/computed/cache'
    assert setting.get_default() == '/computed/cache'
    # Resolved on each read, so it follows the environment it depends on.
    assert len(calls) == 2


def test_get_default_copies_a_sequence_default():
    setting = _setting(value_type=SettingType.LIST, default=('https://recipes.git',))

    default = setting.get_default()
    default.append('mutated')

    assert setting.get_default() == ['https://recipes.git']


def test_parse_string():
    setting = _setting()

    assert setting.parse('/some/cache') == '/some/cache'
    assert setting.parse(None) is None


def test_parse_bool_accepts_the_on_and_off_spellings():
    setting = _setting(value_type=SettingType.BOOL)

    for value in ('off', 'OFF', ' false ', '0', 'no', False):
        assert setting.parse(value) is False, value
    for value in ('on', 'ON', ' true ', '1', 'yes', True):
        assert setting.parse(value) is True, value


def test_parse_rejects_a_value_the_type_cannot_hold():
    with pytest.raises(ValueError) as error:
        _setting(value_type=SettingType.INT).parse('not-a-number')
    # The message names the setting, what it expects and what it got, whichever
    # source the value came from.
    assert str(error.value) == "cache.directory expects an integer, got 'not-a-number'"

    with pytest.raises(ValueError, match='on, true'):
        _setting(value_type=SettingType.BOOL).parse('maybe')

    with pytest.raises(ValueError, match='separated by'):
        _setting(value_type=SettingType.LIST).parse(16)

    with pytest.raises(ValueError, match='a single text value'):
        _setting().parse(['/first', '/second'])


def test_parse_int():
    setting = _setting(value_type=SettingType.INT)

    assert setting.parse('16') == 16
    assert setting.parse(16) == 16


def test_parse_list_splits_a_packed_string_and_keeps_a_sequence():
    setting = _setting(value_type=SettingType.LIST)

    assert setting.parse('/first|/second=github') == ['/first', '/second=github']
    assert setting.parse(['/first', '/second']) == ['/first', '/second']
    # Empty entries are dropped, from both spellings.
    assert setting.parse('/first||') == ['/first']
    assert setting.parse(['/first', '']) == ['/first']


def test_format_value_is_the_reverse_of_parse():
    assert _setting().format_value('/some/cache') == '/some/cache'
    assert _setting().format_value(None) == ''

    boolean = _setting(value_type=SettingType.BOOL)
    assert boolean.format_value(True) == 'on'
    assert boolean.format_value(False) == 'off'
    assert boolean.parse(boolean.format_value(False)) is False

    listed = _setting(value_type=SettingType.LIST)
    assert listed.format_value(['/first', '/second']) == '/first|/second'
    assert listed.parse(listed.format_value(['/first', '/second'])) == ['/first', '/second']


def test_has_value_treats_a_boolean_as_an_answer_and_falsy_as_unset():
    assert has_value(False) is True
    assert has_value(True) is True

    assert has_value(None) is False
    assert has_value('') is False
    assert has_value([]) is False
    assert has_value(0) is False

    assert has_value('/some/cache') is True
    assert has_value(['/some/cache']) is True
    assert has_value(8) is True
