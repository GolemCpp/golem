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
from waflib import Logs
import copy


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

        self.master_dependencies_configuration = None
        self.master_dependencies_repository = None

    def __str__(self):
        return helpers.print_obj(self)

    def resolve(self, global_config_file, dependencies_to_keep):
        cached_dependencies = []

        if global_config_file and os.path.exists(global_config_file):
            cache = None
            with open(global_config_file, 'r') as fp:
                cache = json.load(fp)
            cached_dependencies = Dependency.load_cache(cache=cache)

        for dependency in self.deps:
            is_dependency_to_keep = False
            for dependency_to_keep in dependencies_to_keep:
                if dependency.repository == dependency_to_keep.repository and dependency.version == dependency_to_keep.version:
                    dependency.resolved_version = dependency_to_keep.resolved_version
                    dependency.resolved_hash = dependency_to_keep.resolved_hash
                    is_dependency_to_keep = True
                    break

            cached_deps = [
                dep for dep in cached_dependencies
                if dep.repository == dependency.repository
                and dep.version == dependency.version
            ]
            if not cached_deps:
                if not is_dependency_to_keep:
                    Logs.debug("Querying Git for {} at {}".format(
                        dependency.version, dependency.repository))
                    dependency.resolve()

                cached_dep = copy.deepcopy(dependency)
                cached_dependencies.append(cached_dep)
            else:
                dependency.resolved_version = cached_deps[0].resolved_version
                dependency.resolved_hash = cached_deps[0].resolved_hash

            Logs.debug("Found {}: {} -> {} ({})".format(
                dependency.name, dependency.version,
                dependency.resolved_version, dependency.resolved_hash))

        for dependency in cached_dependencies:
            dependency.name = None

        if global_config_file:
            cache = Dependency.save_cache(cached_dependencies)
            with open(global_config_file, 'w') as fp:
                json.dump(cache, fp, indent=4)

    def deps_resolve_json(self):
        return Dependency.save_cache(dependencies=self.deps)

    def deps_load_json(self, cache):
        cached_dependencies = Dependency.load_cache(cache=cache)

        for i, dependency in enumerate(self.deps):
            for cached_dependency in cached_dependencies:
                if cached_dependency.name == dependency.name and cached_dependency.version == dependency.version:
                    print("{}: {} -> {} ({})".format(
                        cached_dependency.name, cached_dependency.version,
                        cached_dependency.resolved_version,
                        cached_dependency.resolved_hash))
                    self.deps[
                        i].resolved_version = cached_dependency.resolved_version
                    self.deps[
                        i].resolved_hash = cached_dependency.resolved_hash
                    break
            if not self.deps[i].resolved_hash:
                print("{} : no cached version".format(dependency.name))

        sys.stdout.flush()

    def target(self, type, name, link=None, version_template=None, **kwargs):
        new_target = Target(name=name,
                            version_template=version_template,
                            type=type,
                            link=link,
                            **kwargs)

        self.targets.append(new_target)
        return new_target

    def library(self, type=None, **kwargs):
        return self.target(type='library', **kwargs)

    def shared_library(self, type=None, link=None, **kwargs):
        return self.target(type='library', link='shared', **kwargs)

    def static_library(self, type=None, link=None, **kwargs):
        return self.target(type='library', link='static', **kwargs)

    def program(self, type=None, **kwargs):
        return self.target(type='program', **kwargs)

    def objects(self, type=None, **kwargs):
        return self.target(type='objects', **kwargs)

    def export(self, type=None, **kwargs):
        new_target = Target(type=None, export=True, **kwargs)
        self.exports.append(new_target)
        return new_target

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

    def package(self,
                targets,
                name,
                section,
                priority,
                maintainer,
                description,
                homepage,
                prefix=None,
                stripping=None,
                rpath=None):
        package = Package(targets=targets,
                          prefix=prefix,
                          name=name,
                          section=section,
                          priority=priority,
                          maintainer=maintainer,
                          description=description,
                          homepage=homepage,
                          stripping=stripping,
                          rpath=rpath)
        self.packages.append(package)
        return package

    def read_configurations(self, context):
        resolved_paths = []
        for path in self.configuration_paths:
            resolved_path = context.make_project_path(path)
            if not os.path.exists(resolved_path):
                raise Exception("Can't find configuration file at " +
                                resolved_path)
            resolved_paths.append(resolved_path)

        configs = []
        for path in resolved_paths:
            json_conf = None
            with open(path, 'r') as fp:
                json_conf = json.load(fp)
            if not json_conf:
                raise Exception("Failed at loading " + path)

            configs.append(Configuration.unserialize_from_json(json_conf))
        return configs

    @staticmethod
    def unserialize_from_json(json_object):
        project = Project()
        for entry in json_object:
            key = ConditionExpression.clean(entry)
            value = json_object[entry]
            if key == 'configurations':
                project.configuration_paths = value
            elif key == 'dependencies':
                for json_obj in value:
                    project.deps.append(
                        Dependency.unserialize_from_json(json_obj))
            elif key == 'targets':
                for json_obj in value:
                    project.targets.append(
                        Target.unserialize_from_json(json_obj))
            elif key == 'exports':
                for json_obj in value:
                    target = Target.unserialize_from_json(json_obj)
                    target.export = True
                    project.exports.append(target)
            elif key == 'packages':
                for json_obj in value:
                    project.packages.append(
                        Package.unserialize_from_json(json_obj))
            elif key == 'qt_enabled':
                project.qt = value
            elif key == 'qt_path':
                project.qtpath = value
        return project
