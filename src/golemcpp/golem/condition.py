from golemcpp.golem import helpers
from golemcpp.golem import target_platform
import json
from golemcpp.golem.condition_expression import ConditionExpression

# The two axes that have a canonical spelling of their own. A condition and a
# build meet only as strings, so a recipe saying `x64` matches a context saying
# `x86_64` exactly when they are made the same word here.
VALUE_NORMALIZERS = {
    'osystem': target_platform.normalize_osystem,
    'arch': target_platform.normalize_arch,
}

# A value carrying any of this is an expression rather than a name, and is left
# alone. No recipe writes one, and intersection() composes them out of values
# normalized on the way in, so a composed expression is canonical already.
EXPRESSION_CHARACTERS = '+()'


def normalize_values(member, values):
    '''
    Spell a condition's values the way the context will report them.

    Everything arrives here: a golemfile read, a condition restored from JSON,
    and the shorthand parser in configuration.py. That is the point of doing it
    in one place, since data written before this existed is normalized on the
    way back in rather than needing a migration.
    '''
    normalize = VALUE_NORMALIZERS.get(member)
    if not normalize:
        return values

    normalized = []
    for value in values:
        if not isinstance(value, str) or any(
            character in value for character in EXPRESSION_CHARACTERS
        ):
            normalized.append(value)
            continue
        negation = '!' if value.startswith('!') else ''
        normalized.append(negation + normalize(value[len(negation) :]))
    return normalized


class Condition(object):
    def __init__(
        self,
        variant=None,
        link=None,
        runtime_link=None,
        runtime_variant=None,
        osystem=None,
        arch=None,
        compiler=None,
        distribution=None,
        release=None,
        type=None,
        runtime=None,
    ):

        # Handle legacy 'runtime' parameter by mapping it to 'runtime_link'
        if runtime_link is None and runtime is not None:
            runtime_link = runtime

        # debug, release
        self.variant = helpers.parameter_to_list(variant)

        # shared, static
        self.link = helpers.parameter_to_list(link)

        # shared, static
        self.runtime_link = helpers.parameter_to_list(runtime_link)

        # debug, release
        self.runtime_variant = helpers.parameter_to_list(runtime_variant)

        # Canonical operating system names, e.g. linux, windows, macos.
        self.osystem = normalize_values('osystem', helpers.parameter_to_list(osystem))

        # Canonical architecture names, e.g. x86_64, i686, aarch64.
        self.arch = normalize_values('arch', helpers.parameter_to_list(arch))

        # gcc, clang, msvc
        self.compiler = helpers.parameter_to_list(compiler)

        # debian, ubuntu, etc.
        self.distribution = helpers.parameter_to_list(distribution)

        # jessie, stretch, etc.
        self.release = helpers.parameter_to_list(release)

        # program, library
        self.type = helpers.parameter_to_list(type)

    def __str__(self):
        return helpers.print_obj(self)

    @property
    def type_unique(self):
        if not isinstance(self.type, list):
            return self.type
        elif len(self.type) == 1:
            return self.type[0]
        else:
            raise Exception("Can't have a unique value from {}".format(self.type))

    @property
    def link_unique(self):
        if not isinstance(self.link, list):
            return self.link
        elif len(self.link) == 1:
            return self.link[0]
        else:
            raise Exception("Can't have a unique value from {}".format(self.link))

    @staticmethod
    def intersection_expression(cond1, cond2):
        if not cond1 and not cond2:
            return []
        elif not cond1:
            return cond2
        elif not cond2:
            return cond1
        else:
            return ['(' + '+'.join(cond1) + ')(' + '+'.join(cond2) + ')']

    def intersection(self, condition):
        self.variant = Condition.intersection_expression(
            condition.variant, self.variant
        )
        self.link = Condition.intersection_expression(condition.link, self.link)
        self.runtime_link = Condition.intersection_expression(
            condition.runtime_link, self.runtime_link
        )
        self.runtime_variant = Condition.intersection_expression(
            condition.runtime_variant, self.runtime_variant
        )
        self.osystem = Condition.intersection_expression(
            condition.osystem, self.osystem
        )
        self.arch = Condition.intersection_expression(condition.arch, self.arch)
        self.compiler = Condition.intersection_expression(
            condition.compiler, self.compiler
        )
        self.distribution = Condition.intersection_expression(
            condition.distribution, self.distribution
        )
        self.release = Condition.intersection_expression(
            condition.release, self.release
        )
        self.type = Condition.intersection_expression(condition.type, self.type)

    @staticmethod
    def serialized_members():
        return [
            'variant',
            'link',
            'runtime_link',
            'runtime_variant',
            'osystem',
            'arch',
            'compiler',
            'distribution',
            'release',
            'type',
        ]

    @staticmethod
    def serialize_to_json(o, avoid_lists=False):
        json_obj = {}

        for key in o.__dict__:
            if key in Condition.serialized_members():
                if o.__dict__[key]:
                    if (
                        avoid_lists
                        and len(o.__dict__[key]) == 1
                        and isinstance(o.__dict__[key], list)
                        and (
                            o.__dict__[key][0] is None
                            or not isinstance(o.__dict__[key][0], list)
                        )
                    ):
                        json_obj[key] = o.__dict__[key][0]
                    else:
                        json_obj[key] = o.__dict__[key]

        return json_obj

    def parse_entry(self, key, value):
        entries = ConditionExpression.parse_members(key)
        has_entry = False
        for entry in entries:
            raw_entry = ConditionExpression.remove_modifiers(entry)

            # Handle legacy 'runtime' entry by mapping it to 'runtime_link'
            if raw_entry == 'runtime':
                raw_entry = 'runtime_link'

            if raw_entry in Condition.serialized_members():
                values = value if isinstance(value, list) else [value]
                self.__dict__[raw_entry] += normalize_values(raw_entry, values)
                self.__dict__[raw_entry] = helpers.filter_unique(
                    self.__dict__[raw_entry]
                )
                has_entry = True

        return has_entry

    def read_json(self, o):
        has_entry = False

        for entry in o:
            if Condition.parse_entry(self, entry, o[entry]):
                has_entry = True

        return has_entry

    @staticmethod
    def unserialize_from_json(o):
        condition = Condition()
        condition.read_json(o)
        return condition
