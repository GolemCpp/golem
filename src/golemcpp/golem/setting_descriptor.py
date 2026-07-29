from enum import Enum


# Separator packing a list setting into a single environment variable or
# configuration store entry (e.g. PATH1|PATH2=url-regex).
LIST_SEPARATOR = '|'

# Spellings that turn a boolean setting off; anything else present means on.
FALSE_VALUES = ('off', 'false', '0', 'no')


class SettingType(Enum):
    STRING = 'string'
    BOOL = 'bool'
    INT = 'int'
    LIST = 'list'


def has_value(value):
    '''
    Whether a source actually provides a setting. An unset option or variable is
    falsy (empty string, empty list, zero) and falls through to the next source,
    while a boolean False is an explicit answer that stops the search.
    '''
    if isinstance(value, bool):
        return True
    return bool(value)


def require_positive(value, context):
    '''A count that only makes sense above zero. Raises on anything else.'''
    if value <= 0:
        raise ValueError('a positive value is required, got {}'.format(value))
    return value


class SettingProcessingContext:
    '''
    What turning a raw setting into a value needs beyond the value itself. Holds
    the project directory today; grows with what a serializer asks for.
    '''

    def __init__(self, project_dir=None):
        self.project_dir = project_dir


class SettingDescriptor:
    '''
    Definition of one setting: the name it answers to in each source (config
    key, environment variable, CLI option dest), its type and its default.
    Renaming one means moving the old spelling into the matching `legacy_*`
    tuple, which keeps resolving after the current one.

    A setting whose text denotes an object carries the functor pair that reads
    and writes it, `deserialize(text, context)` and `serialize(value, context)`,
    declared together and applied per entry for a list. A plain path only needs
    `is_path`, which resolves it against the project directory.
    '''

    def __init__(self, key, env_name, description,
                 value_type=SettingType.STRING, default=None, option_name=None,
                 is_path=False, deserialize=None, serialize=None,
                 legacy_keys=(), legacy_env_names=(), legacy_option_names=()):
        self.key = key
        self.env_name = env_name
        self.option_name = option_name
        self.description = description
        self.value_type = value_type
        self.default = default
        self.is_path = is_path
        self.deserialize = deserialize
        self.serialize = serialize
        self.legacy_keys = tuple(legacy_keys)
        self.legacy_env_names = tuple(legacy_env_names)
        self.legacy_option_names = tuple(legacy_option_names)

    def __str__(self):
        return self.key

    @property
    def keys(self):
        return (self.key,) + self.legacy_keys

    @property
    def env_names(self):
        return (self.env_name,) + self.legacy_env_names

    @property
    def option_names(self):
        if not self.option_name:
            return self.legacy_option_names
        return (self.option_name,) + self.legacy_option_names

    @property
    def option_flag(self):
        # The command-line spelling of the option dest, for help output.
        if not self.option_name:
            return ''
        return '--{}'.format(self.option_name.replace('_', '-'))

    def get_default(self):
        # Callable defaults let a setting depend on the environment (e.g. the
        # cache directory derived from HOME) without freezing it at import time.
        if callable(self.default):
            return self.default()
        if isinstance(self.default, (list, tuple)):
            return list(self.default)
        return self.default

    def parse(self, value):
        '''
        Convert a raw value to the setting type: a string from the environment,
        an already typed value from a CLI option, the project or the JSON store.
        None when it cannot be converted, so the caller tries the next source.
        '''
        if value is None:
            return None

        if self.value_type == SettingType.BOOL:
            if isinstance(value, bool):
                return value
            return str(value).strip().lower() not in FALSE_VALUES

        if self.value_type == SettingType.INT:
            try:
                return int(value)
            except (TypeError, ValueError):
                return None

        if self.value_type == SettingType.LIST:
            if isinstance(value, (list, tuple)):
                return [str(entry) for entry in value if entry]
            return [entry for entry in str(value).split(LIST_SEPARATOR) if entry]

        return str(value)

    def format_value(self, value):
        '''
        The way a value is spelled in an environment variable or in the
        configuration store, the reverse of parse.
        '''
        if value is None:
            return ''

        if self.value_type == SettingType.BOOL:
            return 'on' if value else 'off'

        if self.value_type == SettingType.LIST:
            return LIST_SEPARATOR.join(str(entry) for entry in value)

        return str(value)
