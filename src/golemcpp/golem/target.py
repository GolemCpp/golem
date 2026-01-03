import copy
from golemcpp.golem import helpers
from golemcpp.golem.configuration import Configuration
from golemcpp.golem.condition_expression import ConditionExpression
from golemcpp.golem.dependency import Dependency
import json


class Target(Configuration):
    def __init__(self,
                 name=None,
                 version_template=None,
                 templates=None,
                 export=False,
                 args=None,
                 **kwargs):
        super(Target, self).__init__(**kwargs)
        self.name = name
        self.version_template = version_template
        self.templates = templates
        self.export = export
        self.args = args

    def __str__(self):
        return helpers.print_obj(self)

    @staticmethod
    def serialized_members():
        return ['name', 'version_template']

    @staticmethod
    def serialize_to_json(o):
        json_obj = Configuration.serialize_to_json(o)

        for key in o.__dict__:
            if key in Target.serialized_members():
                if o.__dict__[key]:
                    json_obj[key] = o.__dict__[key]

        return json_obj

    def read_json(self, o):
        Configuration.read_json(self, o)

        for key, value in o.items():
            if key in Target.serialized_members():
                self.__dict__[key] = value

    @staticmethod
    def unserialize_from_json(o):
        target = Target()
        target.read_json(o)
        return target


class TargetConfigurationFile(object):
    def __init__(self, project=None, configuration=None):
        self.dependencies = []
        self.configuration = configuration
        if self.configuration and project:
            self.dependencies = [
                obj for n in configuration.deps for obj in project.deps
                if obj.name == n
            ]

    @staticmethod
    def serialize_to_json(o):
        json_obj = {
            "dependencies": [
                Dependency.serialize_to_json(dep) for dep in o.dependencies
            ],
            "configuration": Configuration.serialize_to_json(o.configuration)
        }
        return json_obj

    @staticmethod
    def unserialize_from_json(o):
        target_configuration_file = TargetConfigurationFile()
        for key, value in o.items():
            if key == 'dependencies':
                for dep in value:
                    target_configuration_file.dependencies.append(
                        Dependency.unserialize_from_json(dep))
            elif key == 'configuration':
                target_configuration_file.configuration = Configuration.unserialize_from_json(
                    value)
        return target_configuration_file

    @staticmethod
    def load_file(path, context):

        json_content = None
        with open(path, 'r') as file_json:
            json_content = json.load(file_json)

        conf_file = TargetConfigurationFile.unserialize_from_json(json_content)

        for dependency in conf_file.dependencies:
            dependency.update_cache_dir(context=context)

        conf_file.configuration.artifacts_dev = context.translate_cache_dir_paths(
            conf_file.configuration.artifacts_dev)
        conf_file.configuration.artifacts_run = context.translate_cache_dir_paths(
            conf_file.configuration.artifacts_run)
        conf_file.configuration.licenses = context.translate_cache_dir_paths(
            conf_file.configuration.licenses)
        conf_file.configuration.rpath_link = context.translate_cache_dir_paths(
            conf_file.configuration.rpath_link)
        conf_file.configuration.lib = context.translate_cache_dir_paths(
            conf_file.configuration.lib)
        conf_file.configuration.stlib = context.translate_cache_dir_paths(
            conf_file.configuration.stlib)
        conf_file.configuration.libpath = context.translate_cache_dir_paths(
            conf_file.configuration.libpath)
        conf_file.configuration.stlibpath = context.translate_cache_dir_paths(
            conf_file.configuration.stlibpath)
        conf_file.configuration.isystem = context.translate_cache_dir_paths(
            conf_file.configuration.isystem)

        artifacts = conf_file.configuration.artifacts.copy()
        for artifact in artifacts:
            artifact.location = context.translate_cache_dir_paths(
                paths=[artifact.location])[0]
        conf_file.configuration.artifacts = artifacts

        return conf_file

    @staticmethod
    def save_file(path, project, configuration, context):

        conf_file = TargetConfigurationFile(project=project,
                                            configuration=configuration)

        conf_file.configuration.artifacts_dev = context.make_cache_dir_paths(
            conf_file.configuration.artifacts_dev)
        conf_file.configuration.artifacts_run = context.make_cache_dir_paths(
            conf_file.configuration.artifacts_run)
        conf_file.configuration.licenses = context.make_cache_dir_paths(
            conf_file.configuration.licenses)
        conf_file.configuration.rpath_link = context.make_cache_dir_paths(
            conf_file.configuration.rpath_link)
        conf_file.configuration.lib = context.make_cache_dir_paths(
            conf_file.configuration.lib)
        conf_file.configuration.stlib = context.make_cache_dir_paths(
            conf_file.configuration.stlib)
        conf_file.configuration.libpath = context.make_cache_dir_paths(
            conf_file.configuration.libpath)
        conf_file.configuration.stlibpath = context.make_cache_dir_paths(
            conf_file.configuration.stlibpath)
        conf_file.configuration.isystem = context.make_cache_dir_paths(
            conf_file.configuration.isystem)

        artifacts = conf_file.configuration.artifacts.copy()
        for artifact in artifacts:
            artifact.location = context.make_cache_dir_paths(
                paths=[artifact.location])[0]
        conf_file.configuration.artifacts = artifacts

        json_content = json.dumps(
            conf_file,
            default=TargetConfigurationFile.serialize_to_json,
            sort_keys=True,
            indent=4)
        with open(path, 'w') as output:
            output.write(json_content)