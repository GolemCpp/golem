from golemcpp.golem import helpers
from golemcpp.golem.condition_expression import ConditionExpression


class Package:
    def __init__(
        self,
        targets=None,
        name=None,
        stripping=None,
    ):
        self.targets = helpers.parameter_to_list(targets)
        self.name = name
        self.stripping = stripping

        self.hooks = []
        self.deb_package = None
        self.msi_package = None
        self.dmg_package = None

    def __str__(self):
        return helpers.print_obj(self)

    def read_json(self, json_object):
        for entry in json_object:
            key = ConditionExpression.clean(entry)
            value = json_object[entry]
            if key in Package.serialized_members():
                self.__dict__[key] = value
            if key in Package.serialized_members_list():
                self.__dict__[key] += value
                self.__dict__[key] = helpers.filter_unique(self.__dict__[key])

        if 'deb' in json_object:
            self.deb_package = DEBPackage()
            self.deb_package.read_json(json_object['deb'])

        if 'msi' in json_object:
            self.msi_package = MSIPackage()
            self.msi_package.read_json(json_object['msi'])

        if 'dmg' in json_object:
            self.dmg_package = DMGPackage()
            self.dmg_package.read_json(json_object['dmg'])

    def dump_json(self):
        json_obj = {}
        for key in self.__dict__:
            if key in Package.serialized_members(
            ) + Package.serialized_members_list():
                if self.__dict__[key]:
                    json_obj[key] = self.__dict__[key]

        if self.deb_package:
            json_obj['deb'] = self.deb_package.dump_json()

        if self.msi_package:
            json_obj['msi'] = self.msi_package.dump_json()

        if self.dmg_package:
            json_obj['dmg'] = self.dmg_package.dump_json()

        return json_obj

    @staticmethod
    def serialized_members():
        return ['name', 'stripping']

    @staticmethod
    def serialized_members_list():
        return ['targets']

    @staticmethod
    def unserialize_from_json(o):
        package = Package()
        package.read_json(o)
        return package

    @staticmethod
    def serialize_to_json(o):
        return o.dump_json()

    def hook(self, callback):
        self.hooks.append(callback)

    def deb(self, **kwargs):
        self.deb_package = DEBPackage(**kwargs)

    def msi(self, **kwargs):
        self.msi_package = MSIPackage(**kwargs)

    def dmg(self, **kwargs):
        self.dmg_package = DMGPackage(**kwargs)


class DEBPackage:
    def __init__(self,
                 prefix=None,
                 subdirectory=None,
                 skeleton=None,
                 control=None,
                 section=None,
                 priority=None,
                 maintainer=None,
                 description=None,
                 homepage=None,
                 depends=None,
                 rpath=None,
                 templates=None,
                 copy_skeleton=None):

        self.prefix = prefix
        self.subdirectory = subdirectory
        self.skeleton = skeleton
        self.control = control
        self.section = section
        self.priority = priority
        self.maintainer = maintainer
        self.description = description
        self.homepage = homepage
        self.depends = helpers.parameter_to_list(depends)
        self.rpath = rpath
        self.templates = helpers.parameter_to_list(templates)
        self.copy_skeleton = helpers.parameter_to_list(copy_skeleton)

    def __str__(self):
        return helpers.print_obj(self)

    def read_json(self, json_object):
        for entry in json_object:
            key = ConditionExpression.clean(entry)
            value = json_object[entry]
            if key in DEBPackage.serialized_members():
                self.__dict__[key] = value
            if key in DEBPackage.serialized_members_list():
                self.__dict__[key] += value
                self.__dict__[key] = helpers.filter_unique(self.__dict__[key])

    def dump_json(self):
        json_obj = {}
        for key in self.__dict__:
            if key in DEBPackage.serialized_members(
            ) + DEBPackage.serialized_members_list():
                if self.__dict__[key]:
                    json_obj[key] = self.__dict__[key]
        return json_obj

    @staticmethod
    def serialized_members():
        return [
            'prefix', 'subdirectory', 'skeleton', 'control', 'section',
            'priority', 'maintainer', 'description', 'homepage', 'rpath'
        ]

    @staticmethod
    def serialized_members_list():
        return ['templates', 'depends', 'copy_skeleton']

    @staticmethod
    def unserialize_from_json(o):
        package = DEBPackage()
        package.read_json(o)
        return package

    @staticmethod
    def serialize_to_json(o):
        return o.dump_json()


class MSIPackage:
    def __init__(self,
                 skeleton=None,
                 project=None,
                 parameters=None,
                 extensions=None,
                 cultures=None,
                 installdir_id=None,
                 installdir_files_id=None,
                 installdir_files_xslt=None):
        self.skeleton = skeleton
        self.project = project
        self.parameters = helpers.parameter_to_list(parameters)
        self.extensions = helpers.parameter_to_list(extensions)
        self.cultures = helpers.parameter_to_list(cultures)
        self.installdir_id = installdir_id
        self.installdir_files_id = installdir_files_id
        self.installdir_files_xslt = installdir_files_xslt

    def __str__(self):
        return helpers.print_obj(self)

    def read_json(self, json_object):
        for entry in json_object:
            key = ConditionExpression.clean(entry)
            value = json_object[entry]
            if key in MSIPackage.serialized_members():
                self.__dict__[key] = value
            if key in MSIPackage.serialized_members_list():
                self.__dict__[key] += value
                self.__dict__[key] = helpers.filter_unique(self.__dict__[key])

    def dump_json(self):
        json_obj = {}
        for key in self.__dict__:
            if key in MSIPackage.serialized_members(
            ) + MSIPackage.serialized_members_list():
                if self.__dict__[key]:
                    json_obj[key] = self.__dict__[key]
        return json_obj

    @staticmethod
    def serialized_members():
        return [
            'skeleton', 'project', 'parameters', 'extensions', 'cultures',
            'installdir_id', 'installdir_files_id', 'installdir_files_xslt'
        ]

    @staticmethod
    def serialized_members_list():
        return []

    @staticmethod
    def unserialize_from_json(o):
        package = MSIPackage()
        package.read_json(o)
        return package

    @staticmethod
    def serialize_to_json(o):
        return o.dump_json()


class DMGPackage:
    def __init__(self, name=None, skeleton=None, background=None):
        self.name = name
        self.skeleton = skeleton
        self.background = background

    def __str__(self):
        return helpers.print_obj(self)

    def read_json(self, json_object):
        for entry in json_object:
            key = ConditionExpression.clean(entry)
            value = json_object[entry]
            if key in DMGPackage.serialized_members():
                self.__dict__[key] = value
            if key in DMGPackage.serialized_members_list():
                self.__dict__[key] += value
                self.__dict__[key] = helpers.filter_unique(self.__dict__[key])

    def dump_json(self):
        json_obj = {}
        for key in self.__dict__:
            if key in DMGPackage.serialized_members(
            ) + DMGPackage.serialized_members_list():
                if self.__dict__[key]:
                    json_obj[key] = self.__dict__[key]
        return json_obj

    @staticmethod
    def serialized_members():
        return ['name', 'skeleton', 'background']

    @staticmethod
    def serialized_members_list():
        return []

    @staticmethod
    def unserialize_from_json(o):
        package = DMGPackage()
        package.read_json(o)
        return package

    @staticmethod
    def serialize_to_json(o):
        return o.dump_json()