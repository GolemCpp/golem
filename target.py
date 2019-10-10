import copy
import helpers
from configuration import Configuration
from condition_expression import ConditionExpression
from dependency import Dependency


class Target(Configuration):
    def __init__(self, name=None, version_template=None, export=False, ** kwargs):
        super(Target, self).__init__(**kwargs)
        self.name = name
        self.version_template = version_template
        self.export = export

    def __str__(self):
        return helpers.print_obj(self)

    @staticmethod
    def serialized_members():
        return [
            'name',
            'version_template'
        ]

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

        for key, value in o.iteritems():
            if key in Target.serialized_members():
                self.__dict__[key] = value

    @staticmethod
    def unserialize_from_json(o):
        target = Target()
        target.read_json(o)
        return target


class TargetConfigurationFile(object):
    def __init__(self, project=None, configuration=None):
        self.configuration = configuration
        self.dependencies = []
        if self.configuration and project:
            self.dependencies = [
                obj for n in configuration.deps for obj in project.deps if obj.name == n]

    @staticmethod
    def serialize_to_json(o):
        json_obj = {
            "dependencies": [Dependency.serialize_to_json(dep) for dep in o.dependencies],
            "configuration": Configuration.serialize_to_json(o.configuration)
        }
        return json_obj

    @staticmethod
    def unserialize_from_json(o):
        target_configuration_file = TargetConfigurationFile()
        for key, value in o.iteritems():
            if key == 'dependencies':
                for dep in value:
                    target_configuration_file.dependencies.append(
                        Dependency.unserialize_from_json(dep))
            elif key == 'configuration':
                target_configuration_file.configuration = Configuration.unserialize_from_json(
                    value)
        return target_configuration_file
