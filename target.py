import helpers
from configuration import Configuration


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
