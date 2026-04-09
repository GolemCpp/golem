from golemcpp.golem import helpers


class Template:
    def __init__(self, source=None, target=None, build=None):
        self.source = source
        self.target = target
        self.build = build

    def __str__(self):
        return helpers.print_obj(self)

    @staticmethod
    def serialized_members():
        return ['source', 'target', 'build']

    @staticmethod
    def serialize_to_json(o):
        json_obj = {}
        for key in o.__dict__:
            if key in Template.serialized_members():
                if o.__dict__[key]:
                    json_obj[key] = o.__dict__[key]

        return json_obj

    def read_json(self, o):
        for key, value in o.items():
            if key in Template.serialized_members():
                self.__dict__[key] = value

    @staticmethod
    def unserialize_from_json(o):
        template = Template()
        template.read_json(o)
        return template
