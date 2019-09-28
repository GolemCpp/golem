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
        if self.variant or self.linking or self.runtime or self.osystem or self.arch or self.compiler or self.distribution or self.release or self.target_type:
            return True
        return False

    @staticmethod
    def intersection_expression(cond1, cond2):
        if not cond1 and not cond2:
            return []
        elif not cond1:
            return cond2
        elif not cond2:
            return cond1
        else:
            return ['(' + '+'.join(cond1) + ')(' + '+'.join(cond2) + ')']

    def intersection(self, condition):
        self.variant = Condition.intersection_expression(
            condition.variant, self.variant)
        self.linking = Condition.intersection_expression(
            condition.linking, self.linking)
        self.runtime = Condition.intersection_expression(
            condition.runtime, self.runtime)
        self.osystem = Condition.intersection_expression(
            condition.osystem, self.osystem)
        self.arch = Condition.intersection_expression(
            condition.arch, self.arch)
        self.compiler = Condition.intersection_expression(
            condition.compiler, self.compiler)
        self.distribution = Condition.intersection_expression(
            condition.distribution, self.distribution)
        self.release = Condition.intersection_expression(
            condition.release, self.release)
        self.target_type = Condition.intersection_expression(
            condition.target_type, self.target_type)
