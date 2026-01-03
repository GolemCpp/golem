from golemcpp.golem import helpers
import json
from golemcpp.golem.condition_expression import ConditionExpression


class Condition(object):
    def __init__(self,
                 variant=None,
                 link=None,
                 runtime=None,
                 osystem=None,
                 arch=None,
                 compiler=None,
                 distribution=None,
                 release=None,
                 type=None):

        # debug, release
        self.variant = helpers.parameter_to_list(variant)

        # shared, static
        self.link = helpers.parameter_to_list(link)

        # shared, static
        self.runtime = helpers.parameter_to_list(runtime)

        # linux, windows, osx
        self.osystem = helpers.parameter_to_list(osystem)

        # x86, x64
        self.arch = helpers.parameter_to_list(arch)

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
            raise Exception("Can't have a unique value from {}".format(
                self.type))

    @property
    def link_unique(self):
        if not isinstance(self.link, list):
            return self.link
        elif len(self.link) == 1:
            return self.link[0]
        else:
            raise Exception("Can't have a unique value from {}".format(
                self.link))

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
            condition.variant, self.variant)
        self.link = Condition.intersection_expression(condition.link,
                                                      self.link)
        self.runtime = Condition.intersection_expression(
            condition.runtime, self.runtime)
        self.osystem = Condition.intersection_expression(
            condition.osystem, self.osystem)
        self.arch = Condition.intersection_expression(condition.arch,
                                                      self.arch)
        self.compiler = Condition.intersection_expression(
            condition.compiler, self.compiler)
        self.distribution = Condition.intersection_expression(
            condition.distribution, self.distribution)
        self.release = Condition.intersection_expression(
            condition.release, self.release)
        self.type = Condition.intersection_expression(condition.type,
                                                      self.type)

    @staticmethod
    def serialized_members():
        return [
            'variant', 'link', 'runtime', 'osystem', 'arch', 'compiler',
            'distribution', 'release', 'type'
        ]

    @staticmethod
    def serialize_to_json(o, avoid_lists=False):
        json_obj = {}

        for key in o.__dict__:
            if key in Condition.serialized_members():
                if o.__dict__[key]:
                    if avoid_lists and len(
                            o.__dict__[key]) == 1 and isinstance(
                                o.__dict__[key], list) and (
                                    o.__dict__[key][0] is None or
                                    not isinstance(o.__dict__[key][0], list)):
                        json_obj[key] = o.__dict__[key][0]
                    else:
                        json_obj[key] = o.__dict__[key]

        return json_obj

    def parse_entry(self, key, value):
        entries = ConditionExpression.parse_members(key)
        has_entry = False
        for entry in entries:
            raw_entry = ConditionExpression.remove_modifiers(entry)

            if raw_entry in Condition.serialized_members():
                if not isinstance(value, list):
                    self.__dict__[raw_entry] += [value]
                else:
                    self.__dict__[raw_entry] += value
                self.__dict__[raw_entry] = helpers.filter_unique(
                    self.__dict__[raw_entry])
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
