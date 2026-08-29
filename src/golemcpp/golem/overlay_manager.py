import os

from golemcpp.golem import overrides
from golemcpp.golem.cache_manager import get_cache_manager
from golemcpp.golem.overlay import Overlay
from golemcpp.golem.resource_manager import ResourceManager
from golemcpp.golem.resource_manifest import ResourceKind


class OverlayManager(ResourceManager):
    '''
    Manages overlays, which are repositories carrying project configuration
    layers to override a project configuration. Today, it only contributes
    `overrides.json` to control dependencies and manage conflicts.

    Overlays are pinned in cache on the version asked. It means that when asking
    a branch on a overlay, it will update in place to follow this branch at resolve
    time. Same if asking for a Node-like version, it will update in place on
    the same asked version. E.g. "^1.0.0" will follow 1.1.0, then 1.2.0, etc.
    '''

    kind = ResourceKind.OVERLAY

    @staticmethod
    def get_overlay(source) -> Overlay:
        return Overlay(source=source)

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
                cached_overlay.source_path, overrides.OVERRIDES_FILENAME
            )
            if os.path.exists(overrides_path):
                contributions.append(
                    overrides.read_overrides(overrides_path, project_dir)
                )

        if not contributions:
            return ''

        return overrides.write_overrides(
            overrides.merge_overrides(contributions), merged_path
        )


def get_overlay_manager(cache_configuration) -> OverlayManager:
    '''The single factory for the overlay resource manager.'''
    return OverlayManager(get_cache_manager(cache_configuration))
