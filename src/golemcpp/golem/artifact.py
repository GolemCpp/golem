import os

from golemcpp.golem.resolved_version import ResolvedVersion


class Artifact:
    def __init__(
        self,
        path=None,
        location=None,
        type=None,
        scope=None,
        repository=None,
        target=None,
        decorated_target=None,
        resolved=None,
    ):
        self.path = path
        self.location = location
        self.type = type
        self.scope = scope
        self.repository = repository
        self.target = target
        self.decorated_target = decorated_target
        # Which version of the project produced this artifact.
        self.resolved = resolved if resolved else ResolvedVersion()

    def __str__(self):
        return self.absolute_path

    @property
    def absolute_path(self):
        return os.path.join(self.location, self.path)

    def __eq__(self, other):
        return self.absolute_path == other.absolute_path

    RESOLVED_MEMBER = "resolved"

    @staticmethod
    def serialized_members():
        return [
            "path",
            "location",
            "type",
            "scope",
            "repository",
            "target",
            "decorated_target",
            "resolved",
        ]

    @staticmethod
    def serialize_to_json(o):
        json_obj = {}

        for key in o.__dict__:
            if key in Artifact.serialized_members():
                if o.__dict__[key]:
                    json_obj[key] = o.__dict__[key]

        if o.resolved:
            json_obj[Artifact.RESOLVED_MEMBER] = o.resolved.to_dict()

        return json_obj

    def parse_entry(self, key, value):
        if key == Artifact.RESOLVED_MEMBER:
            self.resolved = ResolvedVersion.from_dict(value)
            return

        if key in Artifact.serialized_members():
            if not isinstance(value, str):
                raise RuntimeError(
                    "Bad artifact member type: {}".format(str(type(value)))
                )
            self.__dict__[key] = value

    def read_json(self, o):
        for entry in o:
            self.parse_entry(key=entry, value=o[entry])

    @staticmethod
    def unserialize_from_json(o):
        artifact = Artifact()
        artifact.read_json(o)
        return artifact
