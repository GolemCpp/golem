import helpers
from condition_expression import ConditionExpression


class Package:
    def __init__(self, targets=None, prefix=None, name=None, section=None, priority=None, maintainer=None, description=None, homepage=None):
        self.targets = targets
        self.prefix = prefix
        self.name = name
        self.section = section
        self.priority = priority
        self.maintainer = maintainer
        self.description = description
        self.homepage = homepage

    def __str__(self):
        return helpers.print_obj(self)

    @staticmethod
    def unserialize_from_json(json_object):
        package = Package()
        for entry in json_object:
            key = ConditionExpression.clean(entry)
            value = json_object[entry]
            if key == 'targets':
                package.targets = value
            elif key == 'prefix':
                package.prefix = value
            elif key == 'name':
                package.name = value
            elif key == 'section':
                package.section = value
            elif key == 'priority':
                package.priority = value
            elif key == 'maintainer':
                package.maintainer = value
            elif key == 'description':
                package.description = value
            elif key == 'homepage':
                package.homepage = value
        return package
