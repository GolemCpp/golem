import os
from dataclasses import dataclass

from golemcpp.golem import cache_configuration
from golemcpp.golem import helpers
from golemcpp.golem import resource_manifest
from golemcpp.golem import tool_registry
from golemcpp.golem.cache_manager import get_cache_manager
from golemcpp.golem.resource_manager import Pinning
from golemcpp.golem.resource_manager import ResourceManager
from golemcpp.golem.resource_manifest import ResourceKind
from golemcpp.golem.tool import Tool


@dataclass(frozen=True)
class InstalledToolInfo:
    name: str
    version: str
    cache_root: str = ''
    is_read_only: bool = False


class ToolManager(ResourceManager):
    '''
    Manages installable tools as ordinary cached resources.

    Tools are pinned in cache on their name, which means they update in place
    when asking for a different version. Said differently, asking for a different
    version replaces any existing one.
    '''

    kind = ResourceKind.TOOL
    pinning = Pinning.NAME

    @staticmethod
    def get_tool(tool_name: str, version: str = '') -> Tool:
        definition = tool_registry.get_tool(tool_name)
        if definition is None:
            raise ValueError('unsupported tool: {}'.format(tool_name))
        return Tool(definition=definition, version=version)

    @staticmethod
    def list_available_tools():
        return tool_registry.list_available_tools()

    @staticmethod
    def pre_install_refresh(root, tool: Tool) -> None:
        # A tool's root stores many things, only the manifest and the source
        # directory should remain before a refresh.
        for name in os.listdir(root):
            if name in (
                cache_configuration.SOURCE_DIRNAME,
                resource_manifest.MANIFEST_FILENAME,
            ):
                continue
            path = os.path.join(root, name)
            if os.path.isdir(path):
                helpers.remove_tree(path)
            else:
                os.remove(path)

    @staticmethod
    def post_install(root, tool: Tool) -> None:
        tool.definition.build_handler(resource_root=root)

    def list_installed_tools(self) -> list[InstalledToolInfo]:
        # Scan every configured cache location, like CacheManager.scan, so a tool
        # installed in an additional (or read-only) cache is listed too.
        installed_tools = []
        for definition in self.list_available_tools():
            resource = self.resource_for(Tool(definition=definition))
            for cache_dir in self.cache_manager.locations:
                source = self.cache_manager.read_manifest_source(
                    self.cache_manager.make_cached_resource(cache_dir, resource)
                )
                if source is None:
                    continue
                installed_tools.append(
                    InstalledToolInfo(
                        name=definition.name,
                        version=source.resolved.reference,
                        cache_root=cache_dir.location,
                        is_read_only=cache_dir.is_read_only,
                    )
                )
        return installed_tools


def get_tool_manager(cache_configuration) -> ToolManager:
    '''The single factory for the tool resource manager.'''
    return ToolManager(get_cache_manager(cache_configuration))
