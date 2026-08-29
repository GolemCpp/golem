from dataclasses import dataclass

from golemcpp.golem import cppfront_tool


@dataclass(frozen=True)
class ToolDefinition:
    '''What Golem knows how to install, as opposed to a Tool someone asked for.'''

    name: str
    description: str
    repository: str
    default_version: str | None
    build_handler: callable


TOOLS = {
    cppfront_tool.CPPFRONT_NAME: ToolDefinition(
        name=cppfront_tool.CPPFRONT_NAME,
        description=cppfront_tool.CPPFRONT_DESCRIPTION,
        repository=cppfront_tool.CPPFRONT_REPOSITORY,
        default_version=cppfront_tool.DEFAULT_CPPFRONT_VERSION,
        build_handler=cppfront_tool.build_cppfront,
    ),
}


def get_tool(name: str) -> ToolDefinition | None:
    return TOOLS.get(name)


def list_available_tools() -> list[ToolDefinition]:
    return [TOOLS[name] for name in sorted(TOOLS)]
