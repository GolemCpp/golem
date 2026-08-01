import os

from golemcpp.golem import overrides
from golemcpp.golem.cache_manager import get_cache_manager
from golemcpp.golem.resource import Resource
from golemcpp.golem.resource_manager import ResourceManager
from golemcpp.golem.resource_manifest import ResourceKind


class OverlayManager(ResourceManager):
    '''
    An overlay is a source carrying configuration a project layers onto its own.
    It contributes an `overrides.json` today; whatever it carries next is read
    the same way, from the paths install_overlays hands back.
    '''

    @staticmethod
    def resource_for(source) -> Resource:
        return Resource(
            kind=ResourceKind.OVERLAY,
            cache_key=source.get_cache_key(),
            source=source)

    def install_overlays(self, sources, fetch=True):
        '''
        Installs each configured overlay, in the order it was configured,
        and returns where each lives.
        '''
        return [
            self.install(self.resolve_cached_resource(source), source, fetch=fetch)
            for source in sources
        ]

    def load_overrides(self, sources, project_dir, merged_path, fetch=True):
        '''
        Merges the overrides the configured overlays contribute, layered
        in order, and returns `merged_path` containing them.
        
        Returns an empty string when no overrides could be found.
        '''
        contributions = []
        for overlay_path in self.install_overlays(sources, fetch=fetch):
            overrides_path = os.path.join(overlay_path, overrides.OVERRIDES_FILENAME)
            if os.path.exists(overrides_path):
                contributions.append(
                    overrides.read_overrides(overrides_path, project_dir))

        if not contributions:
            return ''

        return overrides.write_overrides(
            overrides.merge_overrides(contributions), merged_path)


def get_overlay_manager(cache_configuration) -> OverlayManager:
    '''The single factory for the overlay resource manager.'''
    return OverlayManager(get_cache_manager(cache_configuration))
