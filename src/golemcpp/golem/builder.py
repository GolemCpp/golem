#!/usr/bin/env python3

from waflib.TaskGen import feature, before_method
from golemcpp.golem.context import Context
import sys


def get_context(context):
    global global_context
    if not 'global_context' in globals():
        global_context = Context(context)

    global_context.context = context
    return global_context


def options(context):
    Context.options(context)


def configure(context):
    ctx = get_context(context)
    ctx.configure()


def build(context):
    ctx = get_context(context)
    ctx.build_on = True
    ctx.environment()
    ctx.build()


def export(context):
    ctx = get_context(context)
    ctx.environment()

    # Disable targets as there is no task generator associated with this command for the moment
    ctx.context.targets = None

    ctx.export()


def resolve(context):
    ctx = get_context(context)

    ctx.deps_to_resolve = []
    ctx.deps_resolve = True

    ctx.environment(resolve_dependencies=True)

    # Disable targets as there is no task generator associated with this command for the moment
    ctx.context.targets = None

    ctx.resolve_recursively()


def package(context):
    ctx = get_context(context)
    ctx.environment()

    # Disable targets as there is no task generator associated with this command for the moment
    ctx.context.targets = None

    ctx.package()


def requirements(context):
    ctx = get_context(context)
    ctx.environment()

    # Disable targets as there is no task generator associated with this command for the moment
    ctx.context.targets = None

    ctx.requirements()


def dependencies(context):
    ctx = get_context(context)
    ctx.deps_build = True
    ctx.environment()

    # Disable targets as there is no task generator associated with this command for the moment
    ctx.context.targets = None

    ctx.dependencies()


def cppcheck(context):
    ctx = get_context(context)
    ctx.environment()

    # Disable targets as there is no task generator associated with this command for the moment
    ctx.context.targets = None

    ctx.cppcheck()


def clang_tidy(context):
    ctx = get_context(context)
    ctx.environment()

    # Disable targets as there is no task generator associated with this command for the moment
    ctx.context.targets = None

    ctx.clang_tidy()


@feature('*')
@before_method('process_rule')
def post_the_other(self):
    deps = getattr(self, 'depends_on', [])
    for name in self.to_list(deps):
        other = self.bld.get_tgen_by_name(name)
        other.post()
