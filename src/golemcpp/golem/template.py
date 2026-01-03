from golemcpp.golem import helpers


class Template:
    def __init__(self, source=None, target=None, build=None):
        self.source = source
        self.target = target
        self.build = build

    def __str__(self):
        return helpers.print_obj(self)
