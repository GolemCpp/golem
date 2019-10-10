import helpers
from condition import Condition
from condition_expression import ConditionExpression
from copy import deepcopy


class Configuration(Condition):
    def __init__(self,
                 targets=None,
                 static_targets=None,
                 shared_targets=None,
                 defines=None,
                 includes=None,
                 source=None,
                 cxxflags=None,
                 linkflags=None,
                 system=None,
                 packages=None,
                 packages_dev=None,
                 packages_tool=None,
                 features=None,
                 deps=None,
                 use=None,
                 uselib=None,
                 header_only=None,
                 dlls=None,
                 ldflags=None,
                 moc=None,
                 lib=None,
                 libpath=None,
                 stlib=None,
                 stlibpath=None,
                 rpath=None,
                 cflags=None,
                 cppflags=None,
                 cxxdeps=None,
                 ccdeps=None,
                 linkdeps=None,
                 framework=None,
                 frameworkpath=None,
                 program_cxxflags=None,
                 program_linkflags=None,
                 library_cxxflags=None,
                 library_linkflags=None,
                 **kwargs):
        super(Configuration, self).__init__(**kwargs)

        self.packages_tool = '' if packages_tool is None else packages_tool
        self.header_only = False if header_only is None else header_only

        self.targets = helpers.parameter_to_list(targets)

        self.static_targets = helpers.parameter_to_list(static_targets)
        self.shared_targets = helpers.parameter_to_list(shared_targets)

        self.dlls = helpers.parameter_to_list(dlls)

        self.defines = helpers.parameter_to_list(defines)
        self.includes = helpers.parameter_to_list(includes)
        self.source = helpers.parameter_to_list(source)
        self.moc = helpers.parameter_to_list(moc)

        self.lib = helpers.parameter_to_list(lib)
        self.libpath = helpers.parameter_to_list(libpath)
        self.stlib = helpers.parameter_to_list(stlib)
        self.stlibpath = helpers.parameter_to_list(stlibpath)
        self.rpath = helpers.parameter_to_list(rpath)
        self.cflags = helpers.parameter_to_list(cflags)
        self.cppflags = helpers.parameter_to_list(cppflags)
        self.cxxdeps = helpers.parameter_to_list(cxxdeps)
        self.ccdeps = helpers.parameter_to_list(ccdeps)
        self.linkdeps = helpers.parameter_to_list(linkdeps)
        self.framework = helpers.parameter_to_list(framework)
        self.frameworkpath = helpers.parameter_to_list(frameworkpath)

        self.program_cxxflags = helpers.parameter_to_list(program_cxxflags)
        self.program_linkflags = helpers.parameter_to_list(program_linkflags)
        self.library_cxxflags = helpers.parameter_to_list(library_cxxflags)
        self.library_linkflags = helpers.parameter_to_list(library_linkflags)

        self.cxxflags = helpers.parameter_to_list(cxxflags)
        self.linkflags = helpers.parameter_to_list(linkflags)
        self.ldflags = helpers.parameter_to_list(ldflags)
        self.system = helpers.parameter_to_list(system)

        self.packages = helpers.parameter_to_list(packages)
        self.packages_dev = helpers.parameter_to_list(packages_dev)

        self.features = helpers.parameter_to_list(features)
        self.deps = helpers.parameter_to_list(deps)
        self.use = helpers.parameter_to_list(use)
        self.uselib = helpers.parameter_to_list(uselib)

        self.program = []
        self.library = []

        self.when_configs = []

    def __str__(self):
        return helpers.print_obj(self)

    def append(self, config):
        if config.targets:
            self.targets += config.targets
            self.targets = helpers.filter_unique(self.targets)

        if hasattr(config, 'dlls') and config.dlls:
            self.dlls += config.dlls
            self.dlls = helpers.filter_unique(self.dlls)

        if hasattr(config, 'static_targets'):
            self.static_targets += config.static_targets
            self.static_targets = helpers.filter_unique(self.static_targets)

        if hasattr(config, 'shared_targets'):
            self.shared_targets += config.shared_targets
            self.shared_targets = helpers.filter_unique(self.shared_targets)

        if hasattr(config, 'ldflags'):
            self.ldflags += config.ldflags
            self.ldflags = helpers.filter_unique(self.ldflags)

        self.defines += config.defines
        self.defines = helpers.filter_unique(self.defines)
        self.includes += config.includes
        self.includes = helpers.filter_unique(self.includes)
        self.source += config.source
        self.source = helpers.filter_unique(self.source)

        if hasattr(config, 'moc'):
            self.moc += config.moc
            self.moc = helpers.filter_unique(self.moc)

        if hasattr(config, 'lib'):
            self.lib += config.lib
            self.lib = helpers.filter_unique(self.lib)
        if hasattr(config, 'libpath'):
            self.libpath += config.libpath
            self.libpath = helpers.filter_unique(self.libpath)
        if hasattr(config, 'stlib'):
            self.stlib += config.stlib
            self.stlib = helpers.filter_unique(self.stlib)
        if hasattr(config, 'stlibpath'):
            self.stlibpath += config.stlibpath
            self.stlibpath = helpers.filter_unique(self.stlibpath)
        if hasattr(config, 'rpath'):
            self.rpath += config.rpath
            self.rpath = helpers.filter_unique(self.rpath)
        if hasattr(config, 'cflags'):
            self.cflags += config.cflags
            self.cflags = helpers.filter_unique(self.cflags)
        if hasattr(config, 'cppflags'):
            self.cppflags += config.cppflags
            self.cppflags = helpers.filter_unique(self.cppflags)
        if hasattr(config, 'cxxdeps'):
            self.cxxdeps += config.cxxdeps
            self.cxxdeps = helpers.filter_unique(self.cxxdeps)
        if hasattr(config, 'ccdeps'):
            self.ccdeps += config.ccdeps
            self.ccdeps = helpers.filter_unique(self.ccdeps)
        if hasattr(config, 'linkdeps'):
            self.linkdeps += config.linkdeps
            self.linkdeps = helpers.filter_unique(self.linkdeps)
        if hasattr(config, 'framework'):
            self.framework += config.framework
            self.framework = helpers.filter_unique(self.framework)
        if hasattr(config, 'frameworkpath'):
            self.frameworkpath += config.frameworkpath
            self.frameworkpath = helpers.filter_unique(self.frameworkpath)

        if hasattr(config, 'program_cxxflags'):
            self.program_cxxflags += config.program_cxxflags
            self.program_cxxflags = helpers.filter_unique(
                self.program_cxxflags)
        if hasattr(config, 'program_linkflags'):
            self.program_linkflags += config.program_linkflags
            self.program_linkflags = helpers.filter_unique(
                self.program_linkflags)
        if hasattr(config, 'library_cxxflags'):
            self.library_cxxflags += config.library_cxxflags
            self.library_cxxflags = helpers.filter_unique(
                self.library_cxxflags)
        if hasattr(config, 'library_linkflags'):
            self.library_linkflags += config.library_linkflags
            self.library_linkflags = helpers.filter_unique(
                self.library_linkflags)

        self.cxxflags += config.cxxflags
        self.cxxflags = helpers.filter_unique(self.cxxflags)
        self.linkflags += config.linkflags
        self.linkflags = helpers.filter_unique(self.linkflags)
        self.system += config.system
        self.system = helpers.filter_unique(self.system)

        self.packages += config.packages
        self.packages = helpers.filter_unique(self.packages)
        self.packages_dev += config.packages_dev
        self.packages_dev = helpers.filter_unique(self.packages_dev)

        self.features += config.features
        self.features = helpers.filter_unique(self.features)
        self.deps += config.deps
        self.deps = helpers.filter_unique(self.deps)
        self.use += config.use
        self.use = helpers.filter_unique(self.use)
        if hasattr(config, 'uselib'):
            self.uselib += config.uselib
            self.uselib = helpers.filter_unique(self.uselib)

        if hasattr(config, 'program'):
            self.program += config.program

        if hasattr(config, 'library'):
            self.library += config.library

    def merge(self, context, configs, exporting=False, condition=None):
        def evaluate_condition(expected, conditions, predicate=lambda a, b: a == b):
            conditions = helpers.parameter_to_list(conditions)
            for expression in conditions:
                expression = ConditionExpression.clean(expression)
                if expression:
                    def parse_paren(s):
                        def parse_paren_helper(level=0):
                            try:
                                token = next(tokens)
                            except StopIteration:
                                if level != 0:
                                    raise Exception('missing closing paren')
                                else:
                                    return []
                            if token == ')':
                                if level == 0:
                                    raise Exception('missing opening paren')
                                else:
                                    return []
                            elif token == '(':
                                return [parse_paren_helper(level+1)] + parse_paren_helper(level)
                            else:
                                b = parse_paren_helper(level)
                                if b:
                                    if isinstance(b[0], str):
                                        b[0] = token + b[0]
                                        return b
                                    else:
                                        return [token] + b
                                else:
                                    return [token]
                        tokens = iter(s)
                        return parse_paren_helper()

                    expression_array = parse_paren(expression)

                    def evaluate_array(a):
                        result = True
                        for item in a:
                            if isinstance(item, list):
                                i_result = evaluate_array(item)
                                result = result and i_result
                            else:
                                parsed = ConditionExpression.parse_members(
                                    item)
                                i_result = False
                                for i in parsed:
                                    raw_value = ConditionExpression.remove_modifiers(
                                        i)
                                    has_negation = ConditionExpression.has_negation(
                                        i)
                                    if (not predicate(expected, raw_value) if has_negation else predicate(expected, raw_value)):
                                        i_result = True
                                result = result and i_result
                        return result

                    if evaluate_array(expression_array):
                        return True

            return False

        for c_tmp in configs:
            c = c_tmp.merge_configs(context=context, exporting=exporting, condition=condition)

            expected_variant = self.variant
            expected_link = self.link
            expected_runtime = self.runtime
            expected_osystem = self.osystem
            expected_arch = self.arch
            expected_compiler = self.compiler
            expected_distribution = self.distribution
            expected_release = self.release
            expected_type = self.type

            if condition is not None:
                if not expected_variant: expected_variant = condition.variant
                if not expected_link: expected_link = condition.link
                if not expected_runtime: expected_runtime = condition.runtime
                if not expected_osystem: expected_osystem = condition.osystem
                if not expected_arch: expected_arch = condition.arch
                if not expected_compiler: expected_compiler = condition.compiler
                if not expected_distribution: expected_distribution = condition.distribution
                if not expected_release: expected_release = condition.release
                if not expected_type: expected_type = condition.type

            if not expected_variant: expected_variant = context.variant()
            if not expected_link: expected_link = context.link()
            if not expected_runtime: expected_runtime = context.runtime()
            if not expected_osystem: expected_osystem = context.osname()
            if not expected_arch: expected_arch = context.arch()
            if not expected_compiler: expected_compiler = context.compiler_name()
            if not expected_distribution: expected_distribution = context.distribution()
            if not expected_release: expected_release = context.release()

            other_type = c.type

            if (other_type and expected_type and not evaluate_condition(expected_type, other_type)):
                continue

            if (	(c.variant and not evaluate_condition(expected_variant, c.variant))
                    or (c.link and not evaluate_condition(expected_link, c.link))
                    or (c.runtime and not evaluate_condition(expected_runtime, c.runtime))
                    or (c.osystem and not evaluate_condition(expected_osystem, c.osystem))
                    or (c.arch and not evaluate_condition(expected_arch, c.arch))
                    or (c.compiler and not evaluate_condition(expected_compiler, c.compiler))
                    or (c.distribution and not evaluate_condition(expected_distribution, c.distribution))
                    or (c.release and not evaluate_condition(expected_release, c.release))):
                continue

            self.append(c)

            if exporting:
                if not self.header_only and c.header_only is not None:
                    self.header_only = c.header_only

    def when(self, **kwargs):
        config = Configuration(**kwargs)
        self.when_configs.append(config)
        return config

    def merge_configs(self, context, exporting=False, condition=None):
        config = Configuration.copy(self)
        config.merge(context=context, configs=self.when_configs,
                     exporting=exporting, condition=condition)
        config.when_configs = []
        return config

    def merge_copy(self, context, configs, exporting=False, condition=None):
        config = Configuration.copy(self)
        config.merge(context=context, configs=configs,
                     exporting=exporting, condition=condition)
        return config

    def parse_entry(self, key, value):
        entries = ConditionExpression.parse_members(key)
        has_entry = False
        for entry in entries:
            raw_entry = ConditionExpression.remove_modifiers(entry)

            if raw_entry in Configuration.serialized_members_list():
                self.__dict__[raw_entry] += value
                self.__dict__[raw_entry] = helpers.filter_unique(
                    self.__dict__[raw_entry])
                has_entry = True
            elif raw_entry in Configuration.serialized_members():
                self.__dict__[raw_entry] = value
                has_entry = True

        return has_entry

    def parse_condition_entry(self, key, value):
        raw_entry = ConditionExpression.clean(key)
        configs = []
        if raw_entry == "when":
            for config_tmp in value:
                config = Configuration.unserialize_from_json(config_tmp)
                configs.append(config)
        return configs

    def parse_special_entry(self, key, value):
        entries = ConditionExpression.parse_conditions(key)
        is_empty = True
        condition = Condition()
        for entry in entries:
            raw_entry = ConditionExpression.remove_modifiers(entry)

            if not raw_entry:
                continue
            elif raw_entry in ['x86', 'x64']:
                condition.arch.append(raw_entry)
                is_empty = False
            elif raw_entry in ['debug', 'release']:
                condition.variant.append(entry)
                is_empty = False
            elif raw_entry in ['msvc', 'gcc', 'clang']:
                condition.compiler.append(entry)
                is_empty = False
            elif raw_entry in ['windows', 'linux', 'osx', 'android']:
                condition.osystem.append(entry)
                is_empty = False
            elif raw_entry in ['shared', 'static']:
                condition.link.append(entry)
                is_empty = False
            elif raw_entry in ['rshared', 'rstatic']:
                condition.runtime.append(entry)
                is_empty = False
            elif raw_entry in ['debian', 'opensuse', 'ubuntu', 'centos', 'redhat']:
                condition.distribution.append(entry)
                is_empty = False
            elif raw_entry in ['jessie', 'stretch', 'buster']:
                condition.release.append(entry)
                is_empty = False
            elif raw_entry in ['program', 'library']:
                condition.type.append(entry)
                is_empty = False

        configs = []
        if not is_empty:
            config = Configuration.unserialize_from_json(value)
            config.intersection(condition)
            configs.append(config)
        return configs
        
    @staticmethod
    def serialized_members():
        return [
                'packages_tool',
                'header_only'
            ]

    @staticmethod
    def serialized_members_list():
        return [
                'targets',

                'static_targets',
                'shared_targets',

                'dlls',

                'defines',
                'includes',
                'source',
                'moc',

                'lib',
                'libpath',
                'stlib',
                'stlibpath',
                'rpath',
                'cflags',
                'cppflags',
                'cxxdeps',
                'ccdeps',
                'linkdeps',
                'framework',
                'frameworkpath',

                'program_cxxflags',
                'program_linkflags',
                'library_cxxflags',
                'library_linkflags',

                'cxxflags',
                'linkflags',
                'ldflags',
                'system',

                'packages',
                'packages_dev',

                'features',
                'deps',
                'use',
                'uselib'
            ]

    @staticmethod
    def serialize_to_json(o):
        json_obj = Condition.serialize_to_json(o)

        for key in o.__dict__:
            if key in Configuration.serialized_members():
                if o.__dict__[key]:
                    json_obj[key] = o.__dict__[key]

        for key in o.__dict__:
            if key in Configuration.serialized_members_list():
                if o.__dict__[key]:
                    json_obj[key] = o.__dict__[key]

        if o.when_configs:
            json_obj['when'] = [Configuration.serialize_to_json(obj) for obj in o.when_configs]

        return json_obj

    def read_json(self, o):
        Condition.read_json(self, o)

        for entry in o:
            self.parse_entry(entry, o[entry])
        
        configs = []

        for entry in o:
            configs += self.parse_condition_entry(entry, o[entry])

        for entry in o:
            configs += self.parse_special_entry(entry, o[entry])

        self.when_configs = configs

    @staticmethod
    def unserialize_from_json(o):
        configuration = Configuration()
        configuration.read_json(o)
        return configuration

    def copy(self):
        config_tmp = Configuration()
        for key in config_tmp.__dict__:
            config_tmp.__dict__[key] = self.__dict__[key]
        return deepcopy(config_tmp)