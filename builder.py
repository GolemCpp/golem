#!/usr/bin/env python

from waflib.TaskGen import feature, before_method
from context import Context
import sys
sys.dont_write_bytecode = True


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
    ctx.environment()
    ctx.build()


def export(context):
    ctx = get_context(context)
    ctx.environment()
    ctx.export()


def resolve(context):
    ctx = get_context(context)
    ctx.environment(resolve_dependencies=True)
    ctx.resolve_recursively()


def package(context):
    ctx = get_context(context)
    ctx.environment()
    ctx.package()


def requirements(context):
    ctx = get_context(context)
    ctx.environment()
    ctx.requirements()


def dependencies(context):
    ctx = get_context(context)
    ctx.environment()
    ctx.dependencies()


@feature('*')
@before_method('process_rule')
def post_the_other(self):
    deps = getattr(self, 'depends_on', [])
    for name in self.to_list(deps):
        other = self.bld.get_tgen_by_name(name)
        other.post()
