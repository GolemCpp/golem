import os
import sys
import helpers
import json
from target import Target
from configuration import Configuration
from condition_expression import ConditionExpression
from dependency import Dependency
from package import Package
from helpers import *


class Project:
    def __init__(self):
        self.cache = []
        self.deps = []

        self.targets = []
        self.exports = []

        self.qt = False
        self.qtdir = ''

        self.packages = []
        self.configuration_paths = []

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
                    print(item[0] + " : " + item[1] + " -> " + item[2])
                    self.deps[i].resolved_version = item[2]
                    break
            if not self.deps[i].resolved_version:
                print(dep.name + " : no cached version")

        sys.stdout.flush()

    def deps_load_json(self, cache):
        for i, dep in enumerate(self.deps):
            for item in cache:
                if item['name'] == dep.name and item['version'] == dep.version:
                    print(item['name'] + " : " +
                          item['version'] + " -> " + item['commit'])
                    self.deps[i].resolved_version = item['commit']
                    break
            if not self.deps[i].resolved_version:
                print(dep.name + " : no cached version")

        sys.stdout.flush()

    def target(self, type, name, version_template=None, **kwargs):
        newtarget = Target()
        newtarget.type = type
        newtarget.name = name
        newtarget.version_template = version_template

        config = Configuration(**kwargs)
        config.type = type

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

    def objects(self, **kwargs):
        return self.target(type='objects', **kwargs)

    def export(self, **kwargs):
        return self.target(type='export', **kwargs)

    def configuration(self, path):
        self.configuration_paths.append(path)

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

    def read_configurations(self, context):
        resolved_paths = []
        for path in self.configuration_paths:
            resolved_path = context.make_project_path(path)
            if not os.path.exists(resolved_path):
                raise Exception(
                    "Can't find configuration file at " + resolved_path)
            resolved_paths.append(resolved_path)

        configs = []
        for path in resolved_paths:
            json_conf = None
            with open(path, 'r') as fp:
                json_conf = byteify(json.load(fp))
            if not json_conf:
                raise Exception("Failed at loading " + path)

            configs += Configuration.deserialize(json_conf)
        return configs

    @staticmethod
    def deserialize(json_object):
        project = Project()
        for entry in json_object:
            key = ConditionExpression.clean(entry)
            value = json_object[entry]
            if key == 'configurations':
                project.configuration_paths = value
            elif key == 'dependencies':
                for json_obj in value:
                    project.deps.append(Dependency.deserialize(json_obj))
            elif key == 'targets':
                for json_obj in value:
                    project.targets.append(Target.deserialize(json_obj))
            elif key == 'exports':
                for json_obj in value:
                    target = Target.deserialize(json_obj)
                    target.type = 'export'
                    project.exports.append(target)
            elif key == 'packages':
                for json_obj in value:
                    project.packages.append(Package.deserialize(json_obj))
            elif key == 'qt_enabled':
                project.qt = value
            elif key == 'qt_path':
                project.qtpath = value
        return project
