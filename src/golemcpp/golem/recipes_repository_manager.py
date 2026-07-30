from golemcpp.golem.cache_manager import get_cache_manager
from golemcpp.golem.resource import Resource
from golemcpp.golem.resource_manager import ResourceManager
from golemcpp.golem.resource_manifest import ResourceKind


class RecipesRepositoryManager(ResourceManager):
    @staticmethod
    def resource_for(source) -> Resource:
        return Resource(
            kind=ResourceKind.RECIPES_REPOSITORY,
            cache_key=source.get_cache_key(),
            source=source)

    def resolve_cache_directory(self, source):
        return self.cache_manager.resolve_cache_directory(self.resource_for(source))

    def get_resource_location(self, cache_dir, source) -> str:
        return self.cache_manager.get_resource_location(cache_dir, self.resource_for(source))

    def staged_install(self, cache_dir, source, populate) -> str:
        '''Clone the repository source into a staging dir, then atomically swap it
        into place with its manifest (see CacheManager.staged_install).'''
        return self.cache_manager.staged_install(
            cache_dir, self.resource_for(source), populate)


def get_recipes_repository_manager(cache_configuration) -> RecipesRepositoryManager:
    '''The single factory for the recipes repository resource manager.'''
    return RecipesRepositoryManager(get_cache_manager(cache_configuration))
