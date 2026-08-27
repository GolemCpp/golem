import os
import sys
from golemcpp.golem import helpers
import json
from golemcpp.golem.target import Target
from golemcpp.golem.configuration import Configuration
from golemcpp.golem.condition_expression import ConditionExpression
from golemcpp.golem.template import Template
from golemcpp.golem.dependency import Dependency
from golemcpp.golem.package import Package
from golemcpp.golem.helpers import *
from waflib import Logs
import copy


class Project:
    def __init__(self, project_dir):
        self.cache = []
        self.deps = []

        self.targets = []
        self.exports = []

        self.qt = False
        self.qtdir = ''

        self.packages = []
        self.configuration_paths = []

        # TODO: Serialize these new members to/from JSON
        self.clang_tidy_checks = None
        self.cppcheck_enable = None
        self.enable_build_number = False

        self.project_dir = project_dir

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
                if (dependency.repository == dependency_to_keep.repository
                        and dependency.version == dependency_to_keep.version):
                    dependency.resolved = dependency_to_keep.resolved
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
                dependency.resolved = cached_deps[0].resolved

            Logs.debug("Found {}: {} -> {} ({})".format(
                dependency.name, dependency.version,
                dependency.resolved.reference, dependency.resolved.revision))

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
                if (cached_dependency.name == dependency.name
                        and cached_dependency.version == dependency.version):
                    print("{}: {} -> {} ({})".format(
                        cached_dependency.name, cached_dependency.version,
                        cached_dependency.resolved.reference,
                        cached_dependency.resolved.revision))
                    self.deps[i].resolved = cached_dependency.resolved
                    break
            # A copied directory has no version to have cached, so saying so about
            # one would report a failure that cannot happen.
            if not self.deps[i].resolved and not dependency.is_non_git_directory():
                print("{} : no cached version".format(dependency.name))

        sys.stdout.flush()

    def target(self,
               type,
               name,
               link=None,
               version_template=None,
               templates=None,
               args=None,
               **kwargs):
        new_target = Target(name=name,
                            version_template=version_template,
                            templates=templates,
                            args=args,
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

    def task(self, name, **kwargs):
        return self.target(type='task', name=name, args=kwargs)

    def template(self, **kwargs):
        return Template(**kwargs)

    def export(self, type=None, **kwargs):
        new_target = Target(type=None, export=True, **kwargs)
        self.exports.append(new_target)
        return new_target

    def configuration(self, path):
        self.configuration_paths.append(path)

    def dependency(self, **kwargs):
        dep = Dependency(**kwargs)
        dep.update_source(self.project_dir, identity_allowed=True)
        self.deps.append(dep)
        return dep

    def enable_qt(self, path=None):
        self.qt = True
        if path:
            self.qtdir = path

    def package(self, targets, name, stripping=None):
        package = Package(targets=targets, name=name, stripping=stripping)
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
    def unserialize_from_json(json_object, project_dir):
        project = Project(project_dir=project_dir)
        for entry in json_object:
            key = ConditionExpression.clean(entry)
            value = json_object[entry]
            if key == 'configurations':
                project.configuration_paths = value
            elif key == 'dependencies':
                for json_obj in value:
                    # Through update_source like a dependency declared in a
                    # golemfile: a `location` reaches this path too, and left
                    # unresolved it would name a source no reader looks at.
                    dependency = Dependency.unserialize_from_json(json_obj)
                    dependency.update_source(project_dir, identity_allowed=True)
                    project.deps.append(dependency)
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
