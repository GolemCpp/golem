from dataclasses import dataclass

from golemcpp.golem import cppfront_tool


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    repository: str
    default_version: str | None
    install_handler: callable


TOOLS = {
    cppfront_tool.CPPFRONT_NAME: Tool(
        name=cppfront_tool.CPPFRONT_NAME,
        description=cppfront_tool.CPPFRONT_DESCRIPTION,
        repository=cppfront_tool.CPPFRONT_REPOSITORY,
        default_version=cppfront_tool.DEFAULT_CPPFRONT_VERSION,
        install_handler=cppfront_tool.install_cppfront,
    ),
}


def get_tool(name: str) -> Tool | None:
    return TOOLS.get(name)


def list_available_tools() -> list[Tool]:
    return [TOOLS[name] for name in sorted(TOOLS)]