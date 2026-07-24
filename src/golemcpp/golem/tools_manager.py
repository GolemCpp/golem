import os
from dataclasses import dataclass

from golemcpp.golem import cache_manifest
from golemcpp.golem import helpers
from golemcpp.golem import tools_registry


@dataclass(frozen=True)
class ToolManifest:
    # Lightweight view over the unified cache manifest, kept for callers that
    # only care about a tool's name and installed version.
    tool: str
    version: str


@dataclass(frozen=True)
class InstalledToolInfo:
    name: str
    version: str


@dataclass(frozen=True)
class ToolInstallResult:
    name: str
    version: str
    cache_root: str


@dataclass(frozen=True)
class ToolUninstallResult:
    name: str
    removed: bool


class ToolsManager:
    def __init__(self, cache_directory: str):
        self.cache_directory = cache_directory

    @staticmethod
    def get_tool(tool_name: str):
        tool = tools_registry.get_tool(tool_name)
        if tool is None:
            raise ValueError('unsupported tool: {}'.format(tool_name))
        return tool

    @staticmethod
    def list_available_tools():
        return tools_registry.list_available_tools()

    def tool_cache_root(self, tool_name: str) -> str:
        return os.path.join(self.cache_directory, tool_name)

    def tool_staging_root(self, tool_name: str) -> str:
        return self.tool_cache_root(tool_name) + '.tmp'

    def tool_manifest_path(self, tool_name: str) -> str:
        return os.path.join(self.tool_cache_root(tool_name),
                            cache_manifest.MANIFEST_FILENAME)

    def read_tool_manifest(self, tool_name: str) -> ToolManifest | None:
        manifest = cache_manifest.ResourceManifest.read(
            self.tool_manifest_path(tool_name))
        if manifest is None:
            return None

        identity = manifest.identity or {}
        return ToolManifest(
            tool=identity.get('name', tool_name),
            version=identity.get('version', ''),
        )

    def list_installed_tools(self) -> list[InstalledToolInfo]:
        installed_tools = []
        for tool in self.list_available_tools():
            manifest = self.read_tool_manifest(tool.name)
            if manifest is None:
                continue

            installed_tools.append(InstalledToolInfo(
                name=tool.name,
                version=manifest.version,
            ))

        return installed_tools

    def install_tool(self, tool_name: str, version: str) -> ToolInstallResult:
        tool = self.get_tool(tool_name)
        resolved_version = version or tool.default_version
        cache_root = self.tool_cache_root(tool.name)
        staging_root = self.tool_staging_root(tool.name)

        helpers.remove_tree(staging_root)
        os.makedirs(staging_root, exist_ok=True)

        try:
            tool.install_handler(
                version=resolved_version,
                install_root=staging_root,
            )

            manifest = cache_manifest.ResourceManifest.create(
                kind=cache_manifest.ResourceKind.TOOL,
                cache_key=tool.name,
                identity={
                    'name': tool.name,
                    'version': resolved_version,
                    'repository_url': tool.repository_url,
                })
            manifest.write(os.path.join(staging_root, cache_manifest.MANIFEST_FILENAME))

            helpers.remove_tree(cache_root)
            os.makedirs(os.path.dirname(cache_root), exist_ok=True)
            os.replace(staging_root, cache_root)
        finally:
            helpers.remove_tree(staging_root)

        return ToolInstallResult(
            name=tool.name,
            version=resolved_version,
            cache_root=cache_root,
        )

    def uninstall_tool(self, tool_name: str) -> ToolUninstallResult:
        tool = self.get_tool(tool_name)
        cache_root = self.tool_cache_root(tool.name)

        if not os.path.isdir(cache_root):
            return ToolUninstallResult(name=tool.name, removed=False)

        helpers.remove_tree(cache_root)
        return ToolUninstallResult(name=tool.name, removed=True)