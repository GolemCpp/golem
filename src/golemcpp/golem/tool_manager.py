from dataclasses import dataclass

from golemcpp.golem import tool_registry
from golemcpp.golem.cache_manager import get_cache_manager
from golemcpp.golem.resource import Resource
from golemcpp.golem.resource_manager import ResourceManager
from golemcpp.golem.resource_manifest import ResourceKind
from golemcpp.golem.source import Source
from golemcpp.golem.version_resolver import VersionResolver


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
    shared CacheManager), and their versions resolve through the shared
    VersionResolver.
    '''

    @staticmethod
    def get_tool(tool_name: str):
        tool = tool_registry.get_tool(tool_name)
        if tool is None:
            raise ValueError('unsupported tool: {}'.format(tool_name))
        return tool

    @staticmethod
    def list_available_tools():
        return tool_registry.list_available_tools()

    @staticmethod
    def resource_for(tool, resolved_version='') -> Resource:
        return Resource(
            kind=ResourceKind.TOOL,
            cache_key=tool.name,
            source=Source.for_repository(
                tool.repository, reference=resolved_version))

    def resolve_cached_tool(self, tool_name: str, compute_size=False, read_manifest=False):
        '''
        The tool as a cached resource: where it lives, which cache it belongs to
        and whether it is installed at all, resolved in one go.
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
        for tool in self.list_available_tools():
            resource = self.resource_for(tool)
            for cache_dir in self.cache_manager.locations:
                source = self.cache_manager.read_manifest_source(
                    self.cache_manager.get_resource_location(cache_dir, resource))
                if source is None:
                    continue
                installed_tools.append(InstalledToolInfo(
                    name=tool.name,
                    version=source.reference,
                    cache_root=cache_dir.location,
                    is_read_only=cache_dir.is_read_only))
        return installed_tools

    def install_tool(self, tool_name: str, version: str) -> ToolInstallResult:
        tool = self.get_tool(tool_name)
        requested = version or tool.default_version or ''
        resolved_version, resolved_hash = VersionResolver.resolve(tool.repository, requested)

        resource = self.resource_for(tool, resolved_version=resolved_version)
        cache_dir = self.cache_manager.resolve_cache_directory(resource)
        if cache_dir.is_read_only:
            raise RuntimeError(
                'cannot install {} into read-only cache location {}'.format(
                    tool.name, cache_dir.location))

        def populate(staging_root):
            tool.install_handler(version=resolved_version, install_root=staging_root)

        resource_root = self.cache_manager.staged_install(cache_dir, resource, populate)
        return ToolInstallResult(
            name=tool.name,
            version=resolved_version,
            resource_root=resource_root,
            cache_root=cache_dir.location)

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
