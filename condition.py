import helpers


class Condition:
    def __init__(self, variant=None, link=None, linking=None, runtime=None, osystem=None, arch=None, compiler=None, distribution=None, release=None, target_type=None):

        self.variant = helpers.parameter_to_list(variant) 	# debug, release
        self.link = helpers.parameter_to_list(link) 	# shared, static
        self.linking = helpers.parameter_to_list(linking) 	# shared, static
        self.runtime = helpers.parameter_to_list(runtime) 	# shared, static
        self.osystem = helpers.parameter_to_list(
            osystem) 	# linux, windows, osx
        self.arch = helpers.parameter_to_list(arch)			# x86, x64
        self.compiler = helpers.parameter_to_list(compiler) 	# gcc, clang, msvc

        # debian, ubuntu, etc.
        self.distribution = helpers.parameter_to_list(distribution)
        # jessie, stretch, etc.
        self.release = helpers.parameter_to_list(release)
        self.target_type = helpers.parameter_to_list(target_type)

        if not self.link and self.linking:
            self.link = self.linking

    def __str__(self):
        return helpers.print_obj(self)

    def __nonzero__(self):
        if self.variant or self.link or self.linking or self.runtime or self.osystem or self.arch or self.compiler or self.distribution or self.release or self.target_type:
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
        self.link = Condition.intersection_expression(
            condition.link, self.link)
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
        if not self.link and self.linking:
            self.link = self.linking

    @staticmethod
    def unserialize_json(json_obj):
        cond = Condition()
        z = cond.__dict__.copy()
        z.update(json_obj)
        cond.__dict__ = z
        return cond
