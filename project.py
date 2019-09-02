import sys
import helpers
from target import Target
from configuration import Configuration
from dependency import Dependency
from package import Package


class Project:
    def __init__(self):
        self.cache = []
        self.deps = []

        self.targets = []
        self.exports = []

        self.qt = False
        self.qtdir = ''

        self.packages = []

    def __str__(self):
        return helpers.print_obj(self)

    def deps_resolve(self):
        cache = []
        for dep in self.deps:
            dep.resolve()
            cache.append([dep.name, dep.version, dep.resolve()])
        return cache

    def deps_resolve_json(self):
        cache = []
        for dep in self.deps:
            dep.resolve()
            cache.append({
                'name': dep.name,
                'repository': dep.repository,
                'version': dep.version,
                'commit': dep.resolve()
            })
        return cache

    def deps_load(self, cache):
        for i, dep in enumerate(self.deps):
            for item in cache:
                if item[0] == dep.name and item[1] == dep.version:
                    print item[0] + " : " + item[1] + " -> " + item[2]
                    self.deps[i].resolved_version = item[2]
                    break
            if not self.deps[i].resolved_version:
                print dep.name + " : no cached version"

        sys.stdout.flush()

    def deps_load_json(self, cache):
        for i, dep in enumerate(self.deps):
            for item in cache:
                if item['name'] == dep.name and item['version'] == dep.version:
                    print item['name'] + " : " + item['version'] + " -> " + item['commit']
                    self.deps[i].resolved_version = item['commit']
                    break
            if not self.deps[i].resolved_version:
                print dep.name + " : no cached version"

        sys.stdout.flush()

    def target(self, type, name, target=None, targets=None, defines=None, includes=None, source=None, features=None, deps=None, use=None, header_only=None, version_template=None, system=None, moc=None):
        newtarget = Target()
        newtarget.type = type
        newtarget.name = name
        newtarget.version_template = version_template

        config = Configuration()

        config.targets = [] if target is None else [target]
        config.targets = config.targets if targets is None else targets
        config.type = type

        config.defines = [] if defines is None else defines
        config.includes = [] if includes is None else includes
        config.source = [] if source is None else source
        config.moc = [] if moc is None else moc

        config.system = [] if system is None else system

        config.features = [] if features is None else features
        config.deps = [] if deps is None else deps
        config.use = [] if use is None else use

        config.header_only = False if header_only is None else header_only

        newtarget.configs.append(config)

        if type == 'export':
            self.exports.append(newtarget)
            return newtarget

        if any([feature.startswith("QT5") for feature in config.features]):
            self.enable_qt()

        self.targets.append(newtarget)
        return newtarget

    def library(self, **kwargs):
        return self.target(type='library', **kwargs)

    def program(self, **kwargs):
        return self.target(type='program', **kwargs)

    def export(self, **kwargs):
        return self.target(type='export', **kwargs)

    def dependency(self, **kwargs):
        dep = Dependency(**kwargs)
        self.deps.append(dep)
        return dep

    def enable_qt(self, path=None):
        self.qt = True
        if path:
            self.qtdir = path

    def package(self, targets, name, section, priority, maintainer, description, homepage, prefix=None):
        package = Package(
            targets=targets,
            prefix=prefix,
            name=name,
            section=section,
            priority=priority,
            maintainer=maintainer,
            description=description,
            homepage=homepage
        )
        self.packages.append(package)
        return package
