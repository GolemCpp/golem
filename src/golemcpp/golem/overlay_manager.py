import os

from golemcpp.golem import overrides
from golemcpp.golem.cache_manager import get_cache_manager
from golemcpp.golem.overlay import Overlay
from golemcpp.golem.resource import Resource
from golemcpp.golem.resource_manager import ResourceManager
from golemcpp.golem.resource_manifest import ResourceKind


class OverlayManager(ResourceManager):
    '''
    An overlay is a source carrying configuration a project layers onto its own.
    It contributes an `overrides.json` today; whatever it carries next is read
    the same way, from the content of the overlays a caller installed.
    '''

    @staticmethod
    def get_overlay(source, version: str = '') -> Overlay:
        return Overlay(source=source, version=version)

    @classmethod
    def resource_for(cls, overlay: Overlay) -> Resource:
        return Resource(
            kind=ResourceKind.OVERLAY,
            cache_key=cls.cache_key_for(overlay),
            source=cls.source_for(overlay))

    @staticmethod
    def source_for(overlay: Overlay):
        return overlay.to_source()

    @staticmethod
    def resolve_version(overlay: Overlay) -> Overlay:
        overlay.resolve()
        return overlay

    def load_overrides(self, cached_overlays, project_dir, merged_path):
        '''
        Merges the overrides the given overlays contribute, layered in the order
        they come in, and returns `merged_path` containing them. Reads them where
        they already are: installing the overlays is the caller's step.

        Returns an empty string when no overrides could be found.
        '''
        contributions = []
        for cached_overlay in cached_overlays:
            overrides_path = os.path.join(
                cached_overlay.source_path, overrides.OVERRIDES_FILENAME)
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
