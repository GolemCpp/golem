import helpers


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
