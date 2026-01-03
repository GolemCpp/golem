from golemcpp.golem import helpers
from golemcpp.golem.condition import Condition
from golemcpp.golem.condition_expression import ConditionExpression
from copy import deepcopy
from golemcpp.golem.artifact import Artifact


class Configuration(Condition):
    def __init__(self,
                 targets=None,
                 static_targets=None,
                 shared_targets=None,
                 defines=None,
                 includes=None,
                 isystem=None,
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
                 rpath_link=None,
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
                 wfeatures=None,
                 scripts=None,
                 artifacts_dev=None,
                 artifacts_run=None,
                 licenses=None,
                 qmldirs=None,
                 artifacts_generators=None,
                 target_decorators=None,
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
        self.isystem = helpers.parameter_to_list(isystem)
        self.source = helpers.parameter_to_list(source)
        self.moc = helpers.parameter_to_list(moc)

        self.lib = helpers.parameter_to_list(lib)
        self.libpath = helpers.parameter_to_list(libpath)
        self.stlib = helpers.parameter_to_list(stlib)
        self.stlibpath = helpers.parameter_to_list(stlibpath)
        self.rpath = helpers.parameter_to_list(rpath)
        self.rpath_link = helpers.parameter_to_list(rpath_link)
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
        self.wfeatures = helpers.parameter_to_list(wfeatures)

        self.artifacts_dev = helpers.parameter_to_list(artifacts_dev)
        self.artifacts_run = helpers.parameter_to_list(artifacts_run)
        self.licenses = helpers.parameter_to_list(licenses)
        self.qmldirs = helpers.parameter_to_list(qmldirs)

        self.artifacts = []

        self.artifacts_generators = helpers.parameter_to_list(
            artifacts_generators)
        self.target_decorators = helpers.parameter_to_list(target_decorators)

        self.scripts = helpers.parameter_to_list(scripts)

        self.program = []
        self.library = []

        self.when_configs = []

    def __str__(self):
        return helpers.print_obj(self)

    def append(self, config):
        if config.targets:
            self.targets = helpers.filter_unique(self.targets + config.targets)

        if hasattr(config, 'dlls') and config.dlls:
            self.dlls = helpers.filter_unique(self.dlls + config.dlls)

        if hasattr(config, 'static_targets'):
            self.static_targets = helpers.filter_unique(self.static_targets +
                                                        config.static_targets)

        if hasattr(config, 'shared_targets'):
            self.shared_targets = helpers.filter_unique(self.shared_targets +
                                                        config.shared_targets)

        if hasattr(config, 'ldflags'):
            self.ldflags = helpers.filter_unique(self.ldflags + config.ldflags)

        self.defines = helpers.filter_unique(self.defines + config.defines)
        self.includes = helpers.filter_unique(self.includes + config.includes)
        if hasattr(config, 'isystem'):
            self.isystem = helpers.filter_unique(self.isystem + config.isystem)
        self.source = helpers.filter_unique(self.source + config.source)

        if hasattr(config, 'moc'):
            self.moc = helpers.filter_unique(self.moc + config.moc)

        if hasattr(config, 'lib'):
            self.lib = helpers.filter_unique(self.lib + config.lib)
        if hasattr(config, 'libpath'):
            self.libpath = helpers.filter_unique(self.libpath + config.libpath)
        if hasattr(config, 'stlib'):
            self.stlib = helpers.filter_unique(self.stlib + config.stlib)
        if hasattr(config, 'stlibpath'):
            self.stlibpath = helpers.filter_unique(self.stlibpath +
                                                   config.stlibpath)
        if hasattr(config, 'rpath'):
            self.rpath = helpers.filter_unique(self.rpath + config.rpath)
        if hasattr(config, 'rpath_link'):
            self.rpath_link = helpers.filter_unique(self.rpath_link +
                                                    config.rpath_link)
        if hasattr(config, 'cflags'):
            self.cflags = helpers.filter_unique(self.cflags + config.cflags)
        if hasattr(config, 'cppflags'):
            self.cppflags = helpers.filter_unique(self.cppflags +
                                                  config.cppflags)
        if hasattr(config, 'cxxdeps'):
            self.cxxdeps = helpers.filter_unique(self.cxxdeps + config.cxxdeps)
        if hasattr(config, 'ccdeps'):
            self.ccdeps = helpers.filter_unique(self.ccdeps + config.ccdeps)
        if hasattr(config, 'linkdeps'):
            self.linkdeps = helpers.filter_unique(self.linkdeps +
                                                  config.linkdeps)
        if hasattr(config, 'framework'):
            self.framework = helpers.filter_unique(self.framework +
                                                   config.framework)
        if hasattr(config, 'frameworkpath'):
            self.frameworkpath = helpers.filter_unique(self.frameworkpath +
                                                       config.frameworkpath)

        if hasattr(config, 'program_cxxflags'):
            self.program_cxxflags = helpers.filter_unique(
                self.program_cxxflags + config.program_cxxflags)
        if hasattr(config, 'program_linkflags'):
            self.program_linkflags = helpers.filter_unique(
                self.program_linkflags + config.program_linkflags)
        if hasattr(config, 'library_cxxflags'):
            self.library_cxxflags = helpers.filter_unique(
                self.library_cxxflags + config.library_cxxflags)
        if hasattr(config, 'library_linkflags'):
            self.library_linkflags = helpers.filter_unique(
                self.library_linkflags + config.library_linkflags)

        self.cxxflags = helpers.filter_unique(self.cxxflags + config.cxxflags)
        self.linkflags = helpers.filter_unique(self.linkflags +
                                               config.linkflags)
        self.system = helpers.filter_unique(self.system + config.system)

        self.packages = helpers.filter_unique(self.packages + config.packages)
        self.packages_dev = helpers.filter_unique(self.packages_dev +
                                                  config.packages_dev)

        self.features = helpers.filter_unique(self.features + config.features)
        self.deps = helpers.filter_unique(self.deps + config.deps)
        self.use = helpers.filter_unique(self.use + config.use)
        if hasattr(config, 'uselib'):
            self.uselib = helpers.filter_unique(self.uselib + config.uselib)
        if hasattr(config, 'wfeatures'):
            self.wfeatures = helpers.filter_unique(self.wfeatures +
                                                   config.wfeatures)

        if hasattr(config, 'artifacts_dev'):
            self.artifacts_dev = helpers.filter_unique(self.artifacts_dev +
                                                       config.artifacts_dev)

        if hasattr(config, 'artifacts_run'):
            self.artifacts_run = helpers.filter_unique(self.artifacts_run +
                                                       config.artifacts_run)

        if hasattr(config, 'licenses'):
            self.licenses = helpers.filter_unique(self.licenses +
                                                  config.licenses)

        if hasattr(config, 'artifacts'):
            self.artifacts = helpers.filter_unique(self.artifacts +
                                                   config.artifacts)

        if hasattr(config, 'qmldirs'):
            self.qmldirs = helpers.filter_unique(self.qmldirs + config.qmldirs)

        if hasattr(config, 'artifacts_generators'):
            self.artifacts_generators = self.artifacts_generators + config.artifacts_generators
        if hasattr(config, 'target_decorators'):
            self.target_decorators = self.target_decorators + config.target_decorators

        if hasattr(config, 'scripts'):
            self.scripts = self.scripts + config.scripts

        if hasattr(config, 'program'):
            self.program = self.program + config.program

        if hasattr(config, 'library'):
            self.library = self.library + config.library

    def merge(self, context, configs, exporting=False, condition=None):
        def compare_with_expected_value(expected, other):
            if isinstance(expected, list):
                return other in expected
            else:
                return other == expected

        def evaluate_condition(expected,
                               conditions,
                               predicate=compare_with_expected_value):
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
                                return [parse_paren_helper(level + 1)
                                        ] + parse_paren_helper(level)
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
                                    if (not predicate(expected, raw_value)
                                            if has_negation else predicate(
                                                expected, raw_value)):
                                        i_result = True
                                result = result and i_result
                        return result

                    if evaluate_array(expression_array):
                        return True

            return False

        for c_tmp in configs:
            c = c_tmp.merge_configs(context=context,
                                    exporting=exporting,
                                    condition=condition)

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
                if not expected_compiler:
                    expected_compiler = condition.compiler
                if not expected_distribution:
                    expected_distribution = condition.distribution
                if not expected_release: expected_release = condition.release
                if not expected_type: expected_type = condition.type

            if not expected_variant: expected_variant = context.variant()
            if not expected_link: expected_link = context.link()
            if not expected_runtime: expected_runtime = context.runtime()
            if not expected_osystem: expected_osystem = context.osname()
            if not expected_arch: expected_arch = context.arch()
            if not expected_compiler:
                expected_compiler = context.compiler_name()
            if not expected_distribution:
                expected_distribution = context.distribution()
            if not expected_release: expected_release = context.release()

            other_type = c.type

            if (other_type and expected_type
                    and not evaluate_condition(expected_type, other_type)):
                continue

            if ((c.variant
                 and not evaluate_condition(expected_variant, c.variant)) or
                (c.link and not evaluate_condition(expected_link, c.link)) or
                (c.runtime
                 and not evaluate_condition(expected_runtime, c.runtime)) or
                (c.osystem
                 and not evaluate_condition(expected_osystem, c.osystem)) or
                (c.arch and not evaluate_condition(expected_arch, c.arch)) or
                (c.compiler
                 and not evaluate_condition(expected_compiler, c.compiler)) or
                (c.distribution and
                 not evaluate_condition(expected_distribution, c.distribution))
                    or
                (c.release
                 and not evaluate_condition(expected_release, c.release))):
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
        config.merge(context=context,
                     configs=self.when_configs,
                     exporting=exporting,
                     condition=condition)
        config.when_configs = []
        return config

    def merge_copy(self, context, configs, exporting=False, condition=None):
        config = Configuration.copy(self)
        config.merge(context=context,
                     configs=configs,
                     exporting=exporting,
                     condition=condition)
        return config

    def parse_entry(self, key, value):
        entries = ConditionExpression.parse_members(key)
        has_entry = False
        for entry in entries:
            raw_entry = ConditionExpression.remove_modifiers(entry)

            if raw_entry in Configuration.serialized_members_list():
                self.__dict__[raw_entry] += helpers.parameter_to_list(value)
                self.__dict__[raw_entry] = helpers.filter_unique(
                    self.__dict__[raw_entry])
                has_entry = True
            elif raw_entry in Configuration.serialized_members():
                self.__dict__[raw_entry] = value
                has_entry = True

        return has_entry

    def parse_artifacts_entry(self, key, value):
        raw_entry = ConditionExpression.clean(key)
        artifacts = []
        if raw_entry == "artifacts":
            for artifact_entry in value:
                artifact = Artifact.unserialize_from_json(artifact_entry)
                artifacts.append(artifact)
        return artifacts

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
            elif raw_entry in [
                    'debian', 'opensuse', 'ubuntu', 'centos', 'redhat'
            ]:
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
        return ['packages_tool', 'header_only']

    @staticmethod
    def serialized_members_list():
        return [
            'targets', 'static_targets', 'shared_targets', 'dlls', 'defines',
            'includes', 'isystem', 'source', 'moc', 'lib', 'libpath', 'stlib',
            'stlibpath', 'rpath', 'rpath_link', 'cflags', 'cppflags',
            'cxxdeps', 'ccdeps', 'linkdeps', 'framework', 'frameworkpath',
            'program_cxxflags', 'program_linkflags', 'library_cxxflags',
            'library_linkflags', 'cxxflags', 'linkflags', 'ldflags', 'system',
            'packages', 'packages_dev', 'features', 'deps', 'use', 'uselib',
            'wfeatures', 'artifacts_dev', 'artifacts_run', 'licenses',
            'qmldirs'
        ]

    @staticmethod
    def serialize_to_json(o, avoid_lists=False):
        json_obj = Condition.serialize_to_json(o, avoid_lists=avoid_lists)

        for key in o.__dict__:
            if key in Configuration.serialized_members():
                if o.__dict__[key]:
                    json_obj[key] = o.__dict__[key]

        for key in o.__dict__:
            if key in Configuration.serialized_members_list():
                if o.__dict__[key]:
                    if avoid_lists and len(
                            o.__dict__[key]) == 1 and isinstance(
                                o.__dict__[key], list) and (
                                    o.__dict__[key][0] is None or
                                    not isinstance(o.__dict__[key][0], list)):
                        json_obj[key] = o.__dict__[key][0]
                    else:
                        json_obj[key] = o.__dict__[key]

        if o.artifacts:
            json_obj['artifacts'] = [
                Artifact.serialize_to_json(obj) for obj in o.artifacts
            ]

        if o.when_configs:
            json_obj['when'] = [
                Configuration.serialize_to_json(obj) for obj in o.when_configs
            ]

        return json_obj

    def read_json(self, o):
        Condition.read_json(self, o)

        for entry in o:
            self.parse_entry(entry, o[entry])

        artifacts = []
        for entry in o:
            artifacts += self.parse_artifacts_entry(entry, o[entry])
        self.artifacts = artifacts

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