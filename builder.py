#!/usr/bin/env python

import sys
sys.dont_write_bytecode = True

from context import Context


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
    ctx.resolve()
    ctx.build()


def export(context):
    ctx = get_context(context)
    ctx.resolve()
    ctx.export()


def resolve(context):
    ctx = get_context(context)
    ctx.resolve()
    ctx.resolve_recursively()


def package(context):
    ctx = get_context(context)
    ctx.resolve()
    ctx.package()


def requirements(context):
    ctx = get_context(context)
    ctx.resolve()
    ctx.requirements()


def dependencies(context):
    ctx = get_context(context)
    ctx.resolve()
    ctx.dependencies()


from waflib.TaskGen import feature, before_method


@feature('*')
@before_method('process_rule')
def post_the_other(self):
    deps = getattr(self, 'depends_on', [])
    for name in self.to_list(deps):
        other = self.bld.get_tgen_by_name(name)
        other.post()
