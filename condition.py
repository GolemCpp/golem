import helpers


class Condition:
    def __init__(self, variant=None, linking=None, runtime=None, osystem=None, arch=None, compiler=None, distribution=None, release=None, target_type=None):
        self.variant = [] if variant is None else variant 	# debug, release
        self.linking = [] if linking is None else linking 	# shared, static
        self.runtime = [] if runtime is None else runtime 	# shared, static
        self.osystem = [] if osystem is None else osystem 	# linux, windows, osx
        self.arch = [] if arch is None else arch			# x86, x64
        self.compiler = [] if compiler is None else compiler 	# gcc, clang, msvc

        # debian, ubuntu, etc.
        self.distribution = [] if distribution is None else distribution
        # jessie, stretch, etc.
        self.release = [] if release is None else release
        self.target_type = [] if target_type is None else target_type

    def __str__(self):
        return helpers.print_obj(self)

    def __nonzero__(self):
        if self.variant or self.linking or self.runtime or self.osystem or self.arch or self.compiler or self.distribution or self.release:
            return True
        return False

    def append(self, condition):
        self.variant += condition.variant
        self.linking += condition.linking
        self.runtime += condition.runtime
        self.osystem += condition.osystem
        self.arch += condition.arch
        self.compiler += condition.compiler
        self.distribution += condition.distribution
        self.release += condition.release
        self.target_type += condition.target_type

    def prepend(self, condition):
        self.variant = condition.variant + self.variant
        self.linking = condition.linking + self.linking
        self.runtime = condition.runtime + self.runtime
        self.osystem = condition.osystem + self.osystem
        self.arch = condition.arch + self.arch
        self.compiler = condition.compiler + self.compiler
        self.distribution = condition.distribution + self.distribution
        self.release = condition.release + self.release
        self.target_type = condition.target_type + self.target_type
