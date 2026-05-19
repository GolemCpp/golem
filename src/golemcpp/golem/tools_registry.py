from dataclasses import dataclass

from golemcpp.golem import cppfront_tool


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    repository_url: str
    default_version: str | None
    install_handler: callable


TOOLS = {
    cppfront_tool.CPPFRONT_NAME: ToolDefinition(
        name=cppfront_tool.CPPFRONT_NAME,
        description=cppfront_tool.CPPFRONT_DESCRIPTION,
        repository_url=cppfront_tool.CPPFRONT_REPOSITORY_URL,
        default_version=cppfront_tool.DEFAULT_CPPFRONT_VERSION,
        install_handler=cppfront_tool.install_cppfront,
    ),
}


def get_tool(name: str) -> ToolDefinition | None:
    return TOOLS.get(name)


def list_available_tools() -> list[ToolDefinition]:
    return [TOOLS[name] for name in sorted(TOOLS)]