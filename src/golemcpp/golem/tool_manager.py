import os
from dataclasses import dataclass

from golemcpp.golem import helpers
from golemcpp.golem import resource_manifest
from golemcpp.golem import tool_registry
from golemcpp.golem.cache_configuration import SOURCE_DIRNAME
from golemcpp.golem.cache_manager import get_cache_manager
from golemcpp.golem.resource import Resource
from golemcpp.golem.resource_manager import FetchPolicy
from golemcpp.golem.resource_manager import ResourceManager
from golemcpp.golem.resource_manifest import ResourceKind
from golemcpp.golem.tool import Tool


@dataclass(frozen=True)
class InstalledToolInfo:
    name: str
    version: str
    cache_root: str = ''
    is_read_only: bool = False


@dataclass(frozen=True)
class ToolInstallResult:
    name: str
    version: str
    resource_root: str
    cache_root: str


class ToolManager(ResourceManager):
    '''
    Manages installable tools as ordinary cached resources: tools resolve across
    every configured cache exactly like dependencies and repositories (through the
    shared CacheManager).
    '''

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
    def resource_for(tool: Tool) -> Resource:
        # Keyed by the name alone, so a tool asked for at another version lands in
        # the root it already occupies rather than beside it.
        return Resource(
            kind=ResourceKind.TOOL,
            cache_key=tool.name,
            source=ToolManager.source_for(tool))

    @staticmethod
    def source_for(tool: Tool):
        return tool.to_source()

    @staticmethod
    def resolve_version(tool: Tool) -> Tool:
        tool.resolve()
        return tool

    @classmethod
    def policy_for(cls, tool: Tool) -> FetchPolicy:
        # Lands on the exact commit its version resolved to, and cleans because
        # building a tool dirties its own source tree. Not pinned the way a
        # dependency is: a tool is keyed by its name, so the same root is reused
        # for whatever version is asked for next, and reaching a tag pushed after
        # the clone needs the remote.
        return FetchPolicy(
            checkout=tool.resolved_version,
            reference=tool.resolved_hash,
            clean=True,
            fetch_remote=True)

    @staticmethod
    def pre_install_refresh(root, tool: Tool) -> None:
        # A tool's root stores many things, only the manifest and the source
        # directory should remain before a refresh.
        for name in os.listdir(root):
            if name in (SOURCE_DIRNAME, resource_manifest.MANIFEST_FILENAME):
                continue
            path = os.path.join(root, name)
            if os.path.isdir(path):
                helpers.remove_tree(path)
            else:
                os.remove(path)

    @staticmethod
    def post_install(root, tool: Tool) -> None:
        tool.definition.build_handler(resource_root=root)

    def resolve_cached_tool(self, tool_name: str, compute_size=False, read_manifest=False):
        '''
        The tool as a cached resource: where it lives, which cache it belongs to
        and whether it is installed at all, resolved in one go.
        
        A pure lookup -- it goes straight to the cache manager rather than through
        resolve_cached_resource, so finding an installed tool never queries a
        remote. A tool is keyed by its name, so locating one needs no version.
        '''
        return self.cache_manager.resolve_cached_resource(
            self.resource_for(self.get_tool(tool_name)),
            compute_size=compute_size,
            read_manifest=read_manifest)

    def read_tool_source(self, tool_name: str):
        cached_tool = self.resolve_cached_tool(tool_name)
        return self.cache_manager.read_manifest_source(cached_tool.path)

    def list_installed_tools(self) -> list[InstalledToolInfo]:
        # Scan every configured cache location, like CacheManager.scan, so a tool
        # installed in an additional (or read-only) cache is listed too.
        installed_tools = []
        for definition in self.list_available_tools():
            resource = self.resource_for(Tool(definition=definition))
            for cache_dir in self.cache_manager.locations:
                source = self.cache_manager.read_manifest_source(
                    self.cache_manager.get_resource_location(cache_dir, resource))
                if source is None:
                    continue
                installed_tools.append(InstalledToolInfo(
                    name=definition.name,
                    version=source.reference,
                    cache_root=cache_dir.location,
                    is_read_only=cache_dir.is_read_only))
        return installed_tools

    def install_tool(self, tool_name: str, version: str) -> ToolInstallResult:
        tool = self.get_tool(tool_name, version=version)
        # Locating resolves the version, which is what the manifest records.
        cached_tool = self.resolve_cached_resource(tool)
        if cached_tool.is_read_only:
            raise RuntimeError(
                'cannot install {} into read-only cache location {}'.format(
                    tool.name, cached_tool.cache_root))

        return ToolInstallResult(
            name=tool.name,
            version=tool.resolved_version,
            resource_root=self.install(cached_tool, tool),
            cache_root=cached_tool.cache_root)

    def uninstall_tool(self, cached_tool) -> bool:
        '''
        Remove an already resolved tool resource, so what a caller inspected and
        confirmed is exactly what gets deleted. Returns whether it was removed.
        '''
        removed, _ = self.cache_manager.remove_resources([cached_tool])
        return bool(removed)


def get_tool_manager(cache_configuration) -> ToolManager:
    '''The single factory for the tool resource manager.'''
    return ToolManager(get_cache_manager(cache_configuration))
