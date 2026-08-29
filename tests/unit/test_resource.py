from golemcpp.golem.resource import Resource
from golemcpp.golem.resource_manifest import ResourceKind
from golemcpp.golem.resolved_version import ResolvedVersion
from golemcpp.golem.source import Source
from golemcpp.golem import cache_configuration
from golemcpp.golem.locator import Locator


def test_subdir_and_location_come_from_the_kind_and_the_source():
    source = Source.for_repository(
        'https://example.com/tool.git', ResolvedVersion(reference='v1', revision='v1')
    )
    resource = Resource(kind=ResourceKind.TOOL, cache_key='demo', source=source)

    assert resource.subdir == cache_configuration.TOOLS_SUBDIR
    assert resource.locator == Locator('https://example.com/tool.git')
