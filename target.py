import helpers
from configuration import Configuration
from condition_expression import ConditionExpression


class Target:
    def __init__(self):
        self.type = ''
        self.name = ''
        self.configs = []
        self.version_template = None

    def __str__(self):
        return helpers.print_obj(self)

    def when(self, **kwargs):
        config = Configuration(**kwargs)
        self.configs.append(config)
        return config

    @staticmethod
    def deserialize(json_object):
        target = Target()
        for entry in json_object:
            key = ConditionExpression.clean(entry)
            value = json_object[entry]
            if key == 'name':
                target.name = value
            elif key == 'type':
                target.type = value
            elif key == 'version_template':
                target.version_template = value

        target.configs = Configuration.deserialize(json_object)
        return target
