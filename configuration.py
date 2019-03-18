import helpers
from condition import Condition


class Configuration:
    def __init__(self, target=None, targets=None, static_targets=None, shared_targets=None, type=None, defines=None, includes=None, source=None, cxxflags=None, linkflags=None, system=None, packages=None, packages_dev=None, packages_tool=None, features=None, deps=None, use=None, header_only=None, dlls=None, **kwargs):
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

        self.cxxflags = [] if cxxflags is None else cxxflags
        self.linkflags = [] if linkflags is None else linkflags
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

        self.defines += config.defines
        self.includes += config.includes
        self.source += config.source

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

    def merge(self, context, configs, exporting=False):
        for c in configs:
            if (	(not c.condition.variant or context.variant() in c.condition.variant)
                    and (not c.condition.linking or context.link() in c.condition.linking)
                    and (not c.condition.runtime or context.runtime() in c.condition.runtime)
                    and (not c.condition.osystem or context.osname() in c.condition.osystem)
                    and (not c.condition.arch or context.arch() in c.condition.arch)
                    and (not c.condition.compiler or context.compiler() in c.condition.compiler)
                    and (not c.condition.distribution or context.distribution() in c.condition.distribution)
                    and (not c.condition.release or context.release() in c.condition.release)):
                self.append(c)

                if exporting:
                    if c.header_only is not None:
                        self.header_only = c.header_only
