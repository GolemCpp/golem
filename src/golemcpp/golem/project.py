import os
import sys
from golemcpp.golem import helpers
import json
from golemcpp.golem.definition import Definition
from golemcpp.golem.configuration import Configuration
from golemcpp.golem.condition_expression import ConditionExpression
from golemcpp.golem.template import Template
from golemcpp.golem.dependency import Dependency
from golemcpp.golem.dependency import SOURCE_MEMBERS
from golemcpp.golem.package import Package
from golemcpp.golem.helpers import *
from waflib import Logs
import copy

# The members used when working out a resolution (the source, and the asked version).
# A cached entry differing in any of them was resolved from a different request.
#
# Compare the requests, not the resolved counterparts.
STALENESS_MEMBERS = SOURCE_MEMBERS + ("version", "version_regex")


def is_stale_for(cached, dependency) -> bool:
    """Was a cached entry resolved from a different request?"""
    return any(
        getattr(cached, member) != getattr(dependency, member)
        for member in STALENESS_MEMBERS
    )


def resolution_key(dependency):
    """
    What a resolution is looked up by; source and version.

    `version_regex` belongs in it because it filters the candidate tags before
    the range is matched, therefore two requests differing only in it can land
    on different revisions.
    """
    return (dependency.resolved.locator, dependency.version, dependency.version_regex)


class Project:
    def __init__(self, project_dir):
        self.cache = []
        self.deps = []

        self.definitions = []
        self.exports = []

        self.qt = False
        self.qtdir = ""

        self.packages = []
        self.configuration_paths = []

        # Which exports a consumer naming nothing is given.
        # Empty means every one of them.
        self.default_exports = []
        self.has_declared_defaults = False

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
            with open(global_config_file, "r") as fp:
                cache = json.load(fp)
            cached_dependencies = Dependency.load_cache(cache=cache)

        for dependency in self.deps:
            is_dependency_to_keep = False
            for dependency_to_keep in dependencies_to_keep:
                if resolution_key(dependency) == resolution_key(dependency_to_keep):
                    dependency.resolved = dependency_to_keep.resolved
                    is_dependency_to_keep = True
                    break

            cached_deps = [
                dep
                for dep in cached_dependencies
                if resolution_key(dep) == resolution_key(dependency)
            ]
            if not cached_deps:
                if not is_dependency_to_keep:
                    Logs.debug(
                        "Querying Git for {} at {}".format(
                            dependency.version, dependency.resolved.locator
                        )
                    )
                    dependency.resolve()

                cached_dep = copy.deepcopy(dependency)
                cached_dependencies.append(cached_dep)
            else:
                dependency.resolved = cached_deps[0].resolved

            Logs.debug(
                "Found {}: {} -> {} ({})".format(
                    dependency.name,
                    dependency.version,
                    dependency.resolved.version.reference,
                    dependency.resolved.version.revision,
                )
            )

        for dependency in cached_dependencies:
            dependency.name = None

        if global_config_file:
            cache = Dependency.save_cache(cached_dependencies)
            with open(global_config_file, "w") as fp:
                json.dump(cache, fp, indent=4)

    def record_recipes(self, global_config_file):
        """
        Write into the shared cache which recipes served this project's dependencies.

        The entries were written before anything was fetched, so they carry no recipe.

        Reloaded rather than saved from what this project holds. Because every
        sub-invocation appends to the same file, and writing a stale list back would
        drop what they added.
        """
        if not global_config_file or not os.path.exists(global_config_file):
            return

        with open(global_config_file, "r") as fp:
            cache = json.load(fp)

        cached_dependencies = Dependency.load_cache(cache=cache)
        # An entry there is identified by the request it answers, the way
        # resolve matches one. Never by name: save_cache nulls those.
        resolved = {
            resolution_key(dependency): dependency.resolved
            for dependency in self.deps
            if dependency.resolved.recipe
        }

        for cached in cached_dependencies:
            key = resolution_key(cached)
            if key in resolved:
                cached.resolved = resolved[key]

        with open(global_config_file, "w") as fp:
            json.dump(Dependency.save_cache(cached_dependencies), fp, indent=4)

    def deps_resolve_json(self):
        return Dependency.save_cache(dependencies=self.deps)

    def deps_load_json(self, cache):
        cached_dependencies = Dependency.load_cache(cache=cache)

        for i, dependency in enumerate(self.deps):
            for cached_dependency in cached_dependencies:
                if cached_dependency.name != dependency.name or is_stale_for(
                    cached_dependency, dependency
                ):
                    continue

                print(
                    "{}: {} -> {} ({})".format(
                        cached_dependency.name,
                        cached_dependency.version,
                        cached_dependency.resolved.version.reference,
                        cached_dependency.resolved.version.revision,
                    )
                )
                self.deps[i].resolved = cached_dependency.resolved
                break
            # A copied directory has no version to have cached, so saying so about
            # one would report a failure that cannot happen.
            if (
                not self.deps[i].resolved.version
                and not dependency.is_non_git_directory()
            ):
                print("{} : no cached version".format(dependency.name))

        sys.stdout.flush()

    def definition(
        self,
        type,
        name,
        link=None,
        version_template=None,
        templates=None,
        args=None,
        **kwargs,
    ):
        new_definition = Definition(
            name=name,
            version_template=version_template,
            templates=templates,
            args=args,
            type=type,
            link=link,
            **kwargs,
        )

        self.definitions.append(new_definition)
        return new_definition

    def library(self, type=None, **kwargs):
        return self.definition(type="library", **kwargs)

    def shared_library(self, type=None, link=None, **kwargs):
        return self.definition(type="library", link="shared", **kwargs)

    def static_library(self, type=None, link=None, **kwargs):
        return self.definition(type="library", link="static", **kwargs)

    def program(self, type=None, **kwargs):
        return self.definition(type="program", **kwargs)

    def objects(self, type=None, **kwargs):
        return self.definition(type="objects", **kwargs)

    def custom(self, name, **kwargs):
        return self.definition(type="task", name=name, args=kwargs)

    def default(self, exports=None):
        """
        Declare useful defaults about what this projects can do.

        A consumer naming no import and no target (silence) is given these exports
        rather than all of them. It is never a gate. Anything the project exports can
        still be asked for.
        """
        if self.has_declared_defaults:
            raise ValueError("the project declares its defaults twice")

        self.has_declared_defaults = True
        self.default_exports = helpers.parameter_to_list(exports)

    def validate(self):
        """
        Refuse what can only be checked once the project is fully declared.
        """
        exported = [export.name for export in self.exports]
        unknown = [name for name in self.default_exports if name not in exported]

        if unknown:
            raise ValueError(
                "the project defaults to exports it does not declare ({}); it "
                "exports {}".format(
                    ", ".join(unknown), ", ".join(exported) or "nothing"
                )
            )

    def template(self, **kwargs):
        return Template(**kwargs)

    def export(self, type=None, **kwargs):
        new_definition = Definition(type=None, export=True, **kwargs)
        self.exports.append(new_definition)
        return new_definition

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
                raise Exception("Can't find configuration file at " + resolved_path)
            resolved_paths.append(resolved_path)

        configs = []
        for path in resolved_paths:
            json_conf = None
            with open(path, "r") as fp:
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
            if key == "configurations":
                project.configuration_paths = value
            elif key == "dependencies":
                for json_obj in value:
                    # Through update_source like a dependency declared in a
                    # golemfile: a `location` reaches this path too, and left
                    # unresolved it would name a source no reader looks at.
                    dependency = Dependency.unserialize_from_json(json_obj)
                    dependency.update_source(project_dir, identity_allowed=True)
                    project.deps.append(dependency)
            elif key == "targets":
                for json_obj in value:
                    project.definitions.append(
                        Definition.unserialize_from_json(json_obj)
                    )
            elif key == "exports":
                for json_obj in value:
                    target = Definition.unserialize_from_json(json_obj)
                    target.export = True
                    project.exports.append(target)
            elif key == "default":
                project.default(exports=value.get("exports"))
            elif key == "packages":
                for json_obj in value:
                    project.packages.append(Package.unserialize_from_json(json_obj))
            elif key == "qt_enabled":
                project.qt = value
            elif key == "qt_path":
                project.qtpath = value

        # The first point at which the project is fully declared.
        project.validate()

        return project
