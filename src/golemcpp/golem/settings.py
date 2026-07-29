import json
import os

from golemcpp.golem import cache_directory
from golemcpp.golem import cache_resolution_policy
from golemcpp.golem import config_store
from golemcpp.golem import helpers
from golemcpp.golem.setting_descriptor import has_value
from golemcpp.golem.setting_descriptor import require_positive
from golemcpp.golem.setting_descriptor import SettingDescriptor
from golemcpp.golem.setting_descriptor import SettingProcessingContext
from golemcpp.golem.setting_descriptor import SettingType


# Default recipes repository used when nothing is configured.
DEFAULT_RECIPES_REPOSITORY = 'https://github.com/GolemCpp/recipes.git'


def get_default_cache_directory_path():
    home_directory = helpers.get_environ('HOME') or os.path.expanduser('~')
    return os.path.join(home_directory, '.cache', 'golem')


# Single source of truth for the settings Golem understands. Keeping every name
# of a setting here lets the `golem config` command, the CLI options and the
# settings consumers agree, and makes Settings the one place that reads a
# setting whatever the source it comes from.
SETTINGS = (
    SettingDescriptor(
        key='cache.directory',
        env_name='GOLEM_CACHE_DIRECTORY',
        option_name='cache_directory',
        description='Directory used as the writable dependency cache.',
        default=get_default_cache_directory_path,
        is_path=True,
        deserialize=cache_directory.parse_location,
        serialize=cache_directory.format_entry,
    ),
    SettingDescriptor(
        key='cache.additional-directories',
        env_name='GOLEM_ADDITIONAL_CACHE_DIRECTORIES',
        option_name='additional_cache_directory',
        description='Additional writable cache directories (pipe-separated PATH[=URL_REGEX]).',
        value_type=SettingType.LIST,
        default=(),
        is_path=True,
        deserialize=cache_directory.parse_writable_entry,
        serialize=cache_directory.format_entry,
    ),
    SettingDescriptor(
        key='cache.additional-read-only-directories',
        env_name='GOLEM_ADDITIONAL_READ_ONLY_CACHE_DIRECTORIES',
        option_name='additional_read_only_cache_directory',
        description='Additional read-only cache directories (pipe-separated PATH[=URL_REGEX]).',
        value_type=SettingType.LIST,
        default=(),
        is_path=True,
        deserialize=cache_directory.parse_read_only_entry,
        serialize=cache_directory.format_entry,
    ),
    SettingDescriptor(
        key='cache.resolution-policy',
        env_name='GOLEM_CACHE_RESOLUTION_POLICY',
        option_name='cache_resolution_policy',
        description='Cache resolution policy (strict or weak).',
        default='strict',
        deserialize=cache_resolution_policy.parse_policy,
        serialize=cache_resolution_policy.format_policy,
    ),
    SettingDescriptor(
        key='cache.minimization.enabled',
        env_name='GOLEM_CACHE_MINIMIZATION_ENABLED',
        option_name='cache_minimization_enabled',
        description='Store cached resources under short hashed flat paths to avoid long-path '
                    'limits (e.g. Windows CL.exe). on/off, default on.',
        value_type=SettingType.BOOL,
        default=True,
    ),
    SettingDescriptor(
        key='cache.minimization.length',
        env_name='GOLEM_CACHE_MINIMIZATION_LENGTH',
        option_name='cache_minimization_length',
        description='Number of hash characters used for minimized cache resource names '
                    '(default 8).',
        value_type=SettingType.INT,
        default=8,
        deserialize=require_positive,
    ),
    SettingDescriptor(
        key='recipes.repositories',
        env_name='GOLEM_RECIPES_REPOSITORIES',
        description='Recipe repositories used to resolve dependencies.',
        value_type=SettingType.LIST,
        default=(DEFAULT_RECIPES_REPOSITORY,),
    ),
    SettingDescriptor(
        key='overrides.configuration',
        env_name='GOLEM_OVERRIDES_CONFIGURATION',
        option_name='overrides_configuration',
        project_attribute='overrides_configuration',
        description='Path to an overrides configuration file.',
        default='',
        is_path=True,
    ),
    SettingDescriptor(
        key='overrides.repository',
        env_name='GOLEM_OVERRIDES_REPOSITORY',
        project_attribute='overrides_repository',
        description='Repository providing an overrides configuration.',
        default='',
    ),
)


def _index_settings(name_getter):
    index = {}
    for setting in SETTINGS:
        for name in name_getter(setting):
            index[name] = setting
    return index


# Lookups turning any name a setting answers to -- including the legacy ones --
# back into its definition.
SETTINGS_BY_KEY = _index_settings(lambda setting: setting.keys)
SETTINGS_BY_ENV = _index_settings(lambda setting: setting.env_names)
SETTINGS_BY_OPTION = _index_settings(lambda setting: setting.option_names)


def get_setting(name):
    '''
    The setting a name refers to, whatever namespace the name belongs to: an
    environment variable, a dotted configuration key or a CLI option dest, in
    their current or legacy spelling. Returns None for an unknown name.
    '''
    if isinstance(name, SettingDescriptor):
        return name
    return (SETTINGS_BY_ENV.get(name)
            or SETTINGS_BY_KEY.get(name)
            or SETTINGS_BY_OPTION.get(name))


def get_setting_by_env(env_name):
    return SETTINGS_BY_ENV.get(env_name)


def get_setting_by_key(key):
    return SETTINGS_BY_KEY.get(key)


def known_settings():
    return sorted(SETTINGS, key=lambda setting: setting.key)


def is_known_key(key):
    # Only the current keys are settable through `golem config`; the legacy ones
    # stay readable (see Settings.get) but are not advertised any more.
    return any(key == setting.key for setting in SETTINGS)


def known_keys():
    return sorted(setting.key for setting in SETTINGS)


def get_persisted_configure_options(build_dir):
    '''
    The options `golem configure` persisted in the waf env cache (see
    Context.save_options), so a native command honours what the project was
    configured with. None when nothing is persisted or waf is unavailable.
    '''
    if not build_dir:
        return None

    c4che_path = os.path.join(build_dir, 'golem', 'obj', 'c4che', 'main_cache.py')
    if not os.path.isfile(c4che_path):
        return None

    try:
        from waflib.ConfigSet import ConfigSet
    except ImportError:
        return None

    try:
        env = ConfigSet()
        env.load(c4che_path)
        options_json = getattr(env, 'OPTIONS', None)
        if not options_json:
            return None
        return json.loads(options_json)
    except Exception:
        return None


class Settings:
    '''
    The single way to read a setting. Binds the sources once so a caller reading
    several settings does not re-pass them. Holds no resolved value: every get()
    re-reads its sources, so a `golem config` write is picked up right away.
    '''

    def __init__(self, options=None, build_dir=None, project_dir=None, project=None):
        self.options = options
        self.build_dir = build_dir
        self.project_dir = project_dir
        self.project = project
        self.context = SettingProcessingContext(project_dir=project_dir)

    def __str__(self):
        return helpers.print_obj(self)

    def get_setting(self, name):
        return get_setting(name)

    def get(self, name):
        '''
        The value of a setting: converted to its type, deserialized into the
        object it denotes, or the built-in default. None for an unknown name.
        Precedence, highest first: CLI option -> persisted `golem configure`
        option -> project -> environment -> local configuration store -> global
        configuration store -> built-in default.
        '''
        setting = get_setting(name)
        if setting is None:
            return None

        raw = self._find_raw_value(setting)
        value = setting.parse(raw) if raw is not None else None
        if value is None:
            value = setting.get_default()

        return self._process(setting, value)

    def get_default(self, name):
        '''
        The built-in default of a setting, processed the way a resolved value
        is, so a caller reads the same kind of object either way.
        '''
        setting = get_setting(name)
        if setting is None:
            return None

        return self._process(setting, setting.get_default())

    def _process(self, setting, value):
        if isinstance(value, list):
            return [self._deserialize(setting, entry) for entry in value]
        return self._deserialize(setting, value)

    def _deserialize(self, setting, value):
        # An unset value has nothing to read: it stays as it is rather than
        # going through a parser that would reject it. A zero is a value, and a
        # setting that refuses it says so itself.
        if value is None or value == '':
            return value

        if setting.deserialize:
            return setting.deserialize(value, self.context)

        if setting.is_path:
            return helpers.make_absolute_path(value, self.context.project_dir)

        return value

    def make_flag(self, name):
        '''
        The command-line flags carrying a resolved setting to another golem
        command. A list setting repeats its flag once per entry, matching the
        repeatable options; a setting with no CLI option yields nothing.
        '''
        setting = get_setting(name)
        if setting is None or not setting.option_flag:
            return []

        value = self.get(name)
        if not has_value(value):
            return []

        values = value if isinstance(value, list) else [value]
        return ['{}={}'.format(setting.option_flag, self._make_flag_value(setting, entry))
                for entry in values]

    def _make_flag_value(self, setting, value):
        # Written by the code that reads it, so a forwarded flag is one the
        # receiving command can parse back into the same value.
        if setting.serialize:
            return setting.serialize(value, self.context)
        if setting.value_type == SettingType.LIST:
            # One entry of the list, not the whole list format_value would pack.
            return str(value)
        return setting.format_value(value)

    def _find_raw_value(self, setting):
        # CLI option, either the live waf options or a native command Namespace.
        value = self._get_option_value(self.options, setting.option_names)
        if has_value(value):
            return value

        # Persisted `golem configure` options, so a command reached through a
        # build directory honours what the project was configured with, without
        # the user re-passing the option.
        if self.build_dir:
            value = self._get_option_value(
                get_persisted_configure_options(self.build_dir), setting.option_names)
            if has_value(value):
                return value

        # The project itself, for the settings a golemfile can state.
        value = self._get_project_value(setting)
        if has_value(value):
            return value

        # Environment variable.
        for env_name in setting.env_names:
            value = helpers.get_environ(env_name)
            if has_value(value):
                return value

        # Configuration store, project-local scope first, then the user-global one.
        for scope in (config_store.LOCAL_SCOPE, config_store.GLOBAL_SCOPE):
            if scope == config_store.LOCAL_SCOPE and not self.project_dir:
                continue
            for key in setting.keys:
                value = config_store.get_scoped_value(
                    key=key, scope=scope, project_dir=self.project_dir)
                if has_value(value):
                    return value

        return None

    @staticmethod
    def _get_option_value(options, option_names):
        # `options` is a Namespace when it comes from a live CLI/waf parse, and a
        # plain dict when it comes from the persisted `golem configure` options.
        if not options:
            return None

        for option_name in option_names:
            if isinstance(options, dict):
                value = options.get(option_name)
            else:
                value = getattr(options, option_name, None)
            if has_value(value):
                return value

        return None

    def _get_project_value(self, setting):
        if self.project is None or not setting.project_attribute:
            return None
        return getattr(self.project, setting.project_attribute, None)


def get_settings(options=None, build_dir=None, project_dir=None, project=None):
    '''The single factory for a Settings.'''
    return Settings(
        options=options,
        build_dir=build_dir,
        project_dir=project_dir,
        project=project)
