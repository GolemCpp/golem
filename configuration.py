import helpers
from condition import Condition
from condition_expression import ConditionExpression


class Configuration:
    def __init__(self,
                 target=None,
                 targets=None,
                 static_targets=None,
                 shared_targets=None,
                 type=None,
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
        self.condition = Condition(**kwargs)

        self.targets = [] if target is None else [target]
        self.targets = self.targets if targets is None else targets

        self.static_targets = [] if static_targets is None else static_targets
        self.shared_targets = [] if shared_targets is None else shared_targets

        self.dlls = [] if dlls is None else dlls

        self.type = 'library' if type is None else type

        self.defines = [] if defines is None else defines
        self.includes = [] if includes is None else includes
        self.source = [] if source is None else source
        self.moc = [] if moc is None else moc

        self.lib = [] if lib is None else lib
        self.libpath = [] if libpath is None else libpath
        self.stlib = [] if stlib is None else stlib
        self.stlibpath = [] if stlibpath is None else stlibpath
        self.rpath = [] if rpath is None else rpath
        self.cflags = [] if cflags is None else cflags
        self.cppflags = [] if cppflags is None else cppflags
        self.cxxdeps = [] if cxxdeps is None else cxxdeps
        self.ccdeps = [] if ccdeps is None else ccdeps
        self.linkdeps = [] if linkdeps is None else linkdeps
        self.framework = [] if framework is None else framework
        self.frameworkpath = [] if frameworkpath is None else frameworkpath

        self.program_cxxflags = [] if program_cxxflags is None else program_cxxflags
        self.program_linkflags = [] if program_linkflags is None else program_linkflags
        self.library_cxxflags = [] if library_cxxflags is None else library_cxxflags
        self.library_linkflags = [] if library_linkflags is None else library_linkflags

        self.cxxflags = [] if cxxflags is None else cxxflags
        self.linkflags = [] if linkflags is None else linkflags
        self.ldflags = [] if ldflags is None else ldflags
        self.system = [] if system is None else system

        self.packages = [] if packages is None else packages
        self.packages_dev = [] if packages_dev is None else packages_dev
        self.packages_tool = '' if packages_tool is None else packages_tool

        self.features = [] if features is None else features
        self.deps = [] if deps is None else deps
        self.use = [] if use is None else use

        self.header_only = False if header_only is None else header_only

    def __str__(self):
        return helpers.print_obj(self)

    @property
    def target(self):
        return '' if not self.targets else self.targets[0]

    @target.setter
    def target(self, value):
        self.targets = [value] if value else []

    def append(self, config):

        if config.targets:
            self.targets = config.targets

        if hasattr(config, 'dlls') and config.dlls:
            self.dlls = config.dlls

        if hasattr(config, 'static_targets'):
            self.static_targets += config.static_targets

        if hasattr(config, 'shared_targets'):
            self.shared_targets += config.shared_targets

        if hasattr(config, 'ldflags'):
            self.ldflags += config.ldflags

        self.defines += config.defines
        self.includes += config.includes
        self.source += config.source

        if hasattr(config, 'moc'):
            self.moc += config.moc

        if hasattr(config, 'lib'):
            self.lib += config.lib
        if hasattr(config, 'libpath'):
            self.libpath += config.libpath
        if hasattr(config, 'stlib'):
            self.stlib += config.stlib
        if hasattr(config, 'stlibpath'):
            self.stlibpath += config.stlibpath
        if hasattr(config, 'rpath'):
            self.rpath += config.rpath
        if hasattr(config, 'cflags'):
            self.cflags += config.cflags
        if hasattr(config, 'cppflags'):
            self.cppflags += config.cppflags
        if hasattr(config, 'cxxdeps'):
            self.cxxdeps += config.cxxdeps
        if hasattr(config, 'ccdeps'):
            self.ccdeps += config.ccdeps
        if hasattr(config, 'linkdeps'):
            self.linkdeps += config.linkdeps
        if hasattr(config, 'framework'):
            self.framework += config.framework
        if hasattr(config, 'frameworkpath'):
            self.frameworkpath += config.frameworkpath

        if hasattr(config, 'program_cxxflags'):
            self.program_cxxflags += config.program_cxxflags
        if hasattr(config, 'program_linkflags'):
            self.program_linkflags += config.program_linkflags
        if hasattr(config, 'library_cxxflags'):
            self.library_cxxflags += config.library_cxxflags
        if hasattr(config, 'library_linkflags'):
            self.library_linkflags += config.library_linkflags

        self.cxxflags += config.cxxflags
        self.linkflags += config.linkflags
        self.system += config.system

        self.packages += config.packages
        self.packages_dev += config.packages_dev
        if config.packages_tool:
            self.packages_tool = config.packages_tool

        self.features += config.features
        self.deps += config.deps
        self.use += config.use

    def merge(self, context, configs, exporting=False, target_type=None):
        def evaluate_condition(expected, conditions):
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
                                    if type(b[0]) is str:
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
                            if type(item) is list:
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
                                    if expected != raw_value if has_negation else expected == raw_value:
                                        i_result = True
                                result = result and i_result
                        return result

                    if evaluate_array(expression_array):
                        return True

            return False

        for c in configs:
            if not hasattr(c.condition, 'target_type'):
                c.condition.target_type = []

            if (	(not c.condition.variant or evaluate_condition(context.variant(), c.condition.variant))
                    and (not c.condition.linking or evaluate_condition(context.link(), c.condition.linking))
                    and (not c.condition.runtime or evaluate_condition(context.runtime(), c.condition.runtime))
                    and (not c.condition.osystem or evaluate_condition(context.osname(), c.condition.osystem))
                    and (not c.condition.arch or evaluate_condition(context.arch(), c.condition.arch))
                    and (not c.condition.compiler or evaluate_condition(context.compiler_name(), c.condition.compiler))
                    and (not c.condition.distribution or evaluate_condition(context.distribution(), c.condition.distribution))
                    and (not c.condition.target_type or target_type is None or evaluate_condition(target_type, c.condition.target_type))
                    and (not c.condition.release or evaluate_condition(context.release(), c.condition.release))):
                self.append(c)

                if exporting and not self.header_only and c.header_only is not None:
                    self.header_only = c.header_only

    def parse_entry(self, key, value):
        entries = ConditionExpression.parse_members(key)
        has_entry = False
        for entry in entries:
            raw_entry = ConditionExpression.remove_modifiers(entry)

            if raw_entry == "defines":
                self.defines += value
                has_entry = True
            elif raw_entry == "cxxflags":
                self.cxxflags += value
                has_entry = True
            elif raw_entry == "linkflags":
                self.linkflags += value
                has_entry = True
            elif raw_entry == "ldflags":
                self.ldflags += value
                has_entry = True
            elif raw_entry == "cppflags":
                self.cppflags += value
                has_entry = True
            elif raw_entry == "cflags":
                self.cflags += value
                has_entry = True
            elif raw_entry == "lib":
                self.lib += value
                has_entry = True
            elif raw_entry == "libpath":
                self.libpath += value
                has_entry = True
            elif raw_entry == "stlib":
                self.stlib += value
                has_entry = True
            elif raw_entry == "stlibpath":
                self.stlibpath += value
                has_entry = True
            elif raw_entry == "rpath":
                self.rpath += value
                has_entry = True
            elif raw_entry == "includes":
                self.includes += value
                has_entry = True
            elif raw_entry == "source":
                self.source += value
                has_entry = True
            elif raw_entry == "cxxdeps":
                self.cxxdeps += value
                has_entry = True
            elif raw_entry == "ccdeps":
                self.ccdeps += value
                has_entry = True
            elif raw_entry == "linkdeps":
                self.linkdeps += value
                has_entry = True
            elif raw_entry == "framework":
                self.framework += value
                has_entry = True
            elif raw_entry == "frameworkpath":
                self.frameworkpath += value
                has_entry = True
            elif raw_entry == "dlls":
                self.dlls += value
                has_entry = True
            elif raw_entry == "moc":
                self.moc += value
                has_entry = True
            elif raw_entry == "system":
                self.system += value
                has_entry = True
            elif raw_entry == "packages":
                self.packages += value
                has_entry = True
            elif raw_entry == "packages_dev":
                self.packages_dev += value
                has_entry = True
            elif raw_entry == "deps":
                self.deps += value
                has_entry = True
            elif raw_entry == "features":
                self.features += value
                has_entry = True
            elif raw_entry == "use":
                self.use += value
                has_entry = True
            elif raw_entry == "targets":
                self.targets += value
                has_entry = True
            elif raw_entry == "static_targets":
                self.static_targets += value
                has_entry = True
            elif raw_entry == "shared_targets":
                self.shared_targets += value
                has_entry = True
            elif raw_entry == "type":
                self.type = value
                has_entry = True
            elif raw_entry == "packages_tool":
                self.packages_tool = value
                has_entry = True
            elif raw_entry == "header_only":
                self.header_only = value
                has_entry = True
            elif raw_entry == "program_cxxflags":
                self.program_cxxflags = value
                has_entry = True
            elif raw_entry == "program_linkflags":
                self.program_linkflags = value
                has_entry = True
            elif raw_entry == "library_cxxflags":
                self.library_cxxflags = value
                has_entry = True
            elif raw_entry == "library_linkflags":
                self.library_linkflags = value
                has_entry = True

            elif raw_entry == "arch":
                self.condition.arch += value
            elif raw_entry == "variant":
                self.condition.variant += value
            elif raw_entry == "compiler":
                self.condition.compiler += value
            elif raw_entry == "osystem":
                self.condition.osystem += value
            elif raw_entry == "linking":
                self.condition.linking += value
            elif raw_entry == "runtime":
                self.condition.runtime += value
            elif raw_entry == "distribution":
                self.condition.distribution += value
            elif raw_entry == "release":
                self.condition.release += value

        return has_entry

    def parse_condition_entry(self, key, value):
        config = Configuration()
        raw_entry = ConditionExpression.clean(key)
        raw_entry = ConditionExpression.remove_modifiers(key)

        if raw_entry == "when":
            configs = Configuration.deserialize(value)
            for config in configs:
                config.condition.intersection(self.condition)
            return configs
        return []

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
                condition.linking.append(entry)
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
                condition.target_type.append(entry)
                is_empty = False

        if not is_empty:
            configs = Configuration.deserialize(value)
            for config in configs:
                config.condition.intersection(self.condition)
                config.condition.intersection(condition)
            return configs
        return []

    @staticmethod
    def deserialize(json_obj):
        configs = []
        config = Configuration()
        is_empty = True
        for entry in json_obj:
            if config.parse_entry(entry, json_obj[entry]):
                is_empty = False
        for entry in json_obj:
            configs += config.parse_condition_entry(entry, json_obj[entry])
        for entry in json_obj:
            configs += config.parse_special_entry(entry, json_obj[entry])
        if not is_empty:
            configs = [config] + configs
        return configs
