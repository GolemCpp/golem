import json
import os
from argparse import ArgumentParser
from argparse import Namespace
from dataclasses import dataclass
from dataclasses import field
from datetime import datetime
from datetime import timezone

from golemcpp.golem.cache_configuration import get_cache_configuration
from golemcpp.golem.settings import get_settings
from golemcpp.golem import cache_manager
from golemcpp.golem import helpers
from golemcpp.golem.source import Source


def build_cache_parser() -> ArgumentParser:
    parser = ArgumentParser(
        prog='golem cache',
        add_help=False,
        description='Manage cached resources across the configured caches.',
    )
    parser.add_argument('action', nargs='?')
    parser.add_argument('pattern', nargs='?')
    parser.add_argument('--project-dir', dest='project_dir', default='')
    parser.add_argument('--build-dir', dest='build_dir', default='')
    parser.add_argument('--cache-directory', dest='cache_directory', default='')
    parser.add_argument('--cache', dest='cache', default='')
    parser.add_argument('--kind', dest='kind', default='')
    parser.add_argument('--regex', action='store_true', dest='regex')
    parser.add_argument('--long', '-l', action='store_true', dest='long')
    parser.add_argument('--json', action='store_true', dest='as_json')
    parser.add_argument('--remove', action='store_true', dest='remove')
    parser.add_argument('--dry-run', action='store_true', dest='dry_run')
    parser.add_argument('--yes', '-y', action='store_true', dest='yes')
    parser.add_argument('-h', '--help', action='store_true', dest='help')
    return parser


def parse_cache_args(args: list[str]) -> Namespace:
    parser = build_cache_parser()
    return parser.parse_args(args)


def _parse_iso(value: str):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def humanize_age(value: str) -> str:
    parsed = _parse_iso(value)
    if parsed is None:
        return 'unknown'

    seconds = int((datetime.now(timezone.utc) - parsed).total_seconds())
    if seconds < 0:
        seconds = 0

    if seconds < 60:
        return '{}s ago'.format(seconds)
    minutes = seconds // 60
    if minutes < 60:
        return '{}m ago'.format(minutes)
    hours = minutes // 60
    if hours < 24:
        return '{}h ago'.format(hours)
    days = hours // 24
    return '{}d ago'.format(days)


def resource_label(resource: cache_manager.CachedResource) -> str:
    if resource.manifest is None:
        return str(resource.cache_key)
    source = Source.from_manifest(resource.manifest)
    return source.label or str(resource.cache_key)


@dataclass
class CacheCommandHandler:
    project_dir: str
    options: Namespace
    _manager: cache_manager.CacheManager | None = field(default=None, init=False, repr=False)

    @staticmethod
    def print_help() -> None:
        print('Usage: golem cache list [--kind=<kind>] [--cache=<path>] [--long] [--json]')
        print('       golem cache caches [--json]')
        print('       golem cache size [--kind=<kind>] [--cache=<path>]')
        print('       golem cache remove <path-or-regex> [--regex] [--dry-run] [--yes]')
        print('       golem cache purge [--kind=<kind>] [--cache=<path>] [--dry-run] [--yes]')
        print('       golem cache unidentified [--remove] [--dry-run] [--yes]')
        print('Manage resources stored in the caches the project is configured to use.')
        print('')
        print('Subcommands:')
        print('  list           List cached resources across every configured cache')
        print('  caches         List the configured cache locations themselves')
        print('  size           Show storage totals per cache and per resource kind')
        print('  remove         Delete resources matching a path substring or regex')
        print('  purge          Delete every resource from the caches')
        print('  unidentified   List (or --remove) resources without a valid manifest')
        print('')
        print('Options:')
        print('  --kind=<kind>          Filter by resource kind (dependency, tool,')
        print('                         cookbook, overlay)')
        print('  --cache=<path>         Restrict to a single cache location')
        print('  --regex                Treat the remove pattern as a regular expression')
        print('  --long, -l             Show created/last-used/manifest-version details')
        print('  --json                 Emit machine-readable JSON')
        print('  --dry-run              Show the selection without deleting anything')
        print('  --yes, -y              Do not prompt for confirmation before deleting')
        print('  --cache-directory=<path>   Override the primary cache directory')

    def make_manager(self) -> cache_manager.CacheManager:
        if self._manager is None:
            settings = get_settings(
                options=self.options,
                build_dir=self.options.build_dir or None,
                project_dir=self.project_dir or None,
            )
            cache_configuration = get_cache_configuration(settings)
            self._manager = cache_manager.get_cache_manager(cache_configuration)
        return self._manager

    def _cache_filter(self):
        if not self.options.cache:
            return None
        return os.path.abspath(
            helpers.make_absolute_path(self.options.cache, os.getcwd()))

    def _scanned_resources(self, compute_size=True):
        manager = self.make_manager()
        resources = manager.scan(compute_size=compute_size)

        cache_filter = self._cache_filter()
        if cache_filter is not None:
            resources = [
                resource for resource in resources
                if os.path.abspath(resource.cache_root) == cache_filter
            ]

        if self.options.kind:
            resources = cache_manager.CacheManager.filter_kind(
                resources, self.options.kind)

        return resources

    # -- list -------------------------------------------------------------

    def handle_list(self) -> int:
        resources = self._scanned_resources()

        if self.options.as_json:
            print(json.dumps([self._resource_to_dict(r) for r in resources], indent=2))
            return 0

        if not resources:
            print('No cached resources found.')
            return 0

        print('Cached resources:')
        for location, group in self._group_by_cache(resources):
            read_only = any(resource.is_read_only for resource in group)
            print('')
            print('{}{}:'.format(location, ' (read-only)' if read_only else ''))
            for resource in group:
                self._print_resource(resource)
        return 0

    def _group_by_cache(self, resources):
        '''
        Group resources by their cache location, yielding (location, resources)
        in the order the caches are configured (primary first) so the listing is
        stable and separated per cache.
        '''
        groups = {}
        for resource in resources:
            groups.setdefault(resource.cache_root, []).append(resource)

        emitted = set()
        for cache_dir in self.make_manager().locations:
            group = groups.get(cache_dir.location)
            if group is not None and cache_dir.location not in emitted:
                emitted.add(cache_dir.location)
                yield cache_dir.location, group

        for location, group in groups.items():
            if location not in emitted:
                emitted.add(location)
                yield location, group

    def _resource_to_dict(self, resource) -> dict:
        return {
            'kind': resource.kind,
            'cache_key': resource.cache_key,
            'source': resource.source,
            'identified': resource.is_identified,
            'manifest_version': resource.manifest_version,
            'cache_root': resource.cache_root,
            'read_only': resource.is_read_only,
            'size_bytes': resource.size_bytes,
            'created_at': resource.created_at,
            'last_used_at': resource.last_used_at,
            'path': resource.path,
        }

    def _print_resource(self, resource) -> None:
        label = resource_label(resource)
        marker = ' (unidentified)' if not resource.is_identified else ''
        print('  [{}] {}{}'.format(resource.kind, label, marker))
        # The path is always shown (the cache location is the group header above).
        print('    size: {}  path: {}'.format(
            helpers.format_size(resource.size_bytes),
            resource.path))
        if self.options.long:
            print('    created: {}  last used: {}'.format(
                humanize_age(resource.created_at),
                humanize_age(resource.last_used_at)))
            print('    manifest version: {}'.format(
                resource.manifest_version if resource.manifest_version is not None else '-'))

    # -- caches -----------------------------------------------------------

    def handle_caches(self) -> int:
        summaries = self.make_manager().list_cache_locations()

        if self.options.as_json:
            print(json.dumps([{
                'location': summary.location,
                'read_only': summary.is_read_only,
                'regex': summary.regex,
                'exists': summary.exists,
            } for summary in summaries], indent=2))
            return 0

        print('Configured caches:')
        for summary in summaries:
            attributes = ['read-only' if summary.is_read_only else 'writable']
            if summary.regex:
                attributes.append('regex={}'.format(summary.regex))
            if not summary.exists:
                attributes.append('missing')
            print('  {} ({})'.format(summary.location, ', '.join(attributes)))
        return 0

    # -- size -------------------------------------------------------------

    def handle_size(self) -> int:
        resources = self._scanned_resources()

        per_cache = {}
        per_kind = {}
        total = 0
        for resource in resources:
            per_cache[resource.cache_root] = per_cache.get(resource.cache_root, 0) + resource.size_bytes
            per_kind[resource.kind] = per_kind.get(resource.kind, 0) + resource.size_bytes
            total += resource.size_bytes

        if self.options.as_json:
            print(json.dumps({
                'total_bytes': total,
                'per_cache': per_cache,
                'per_kind': per_kind,
            }, indent=2))
            return 0

        print('Cache storage usage:')
        print('  Total: {}'.format(helpers.format_size(total)))
        if per_cache:
            print('  By cache:')
            for location in sorted(per_cache):
                print('    {}: {}'.format(location, helpers.format_size(per_cache[location])))
        if per_kind:
            print('  By kind:')
            for kind in sorted(per_kind):
                print('    {}: {}'.format(kind, helpers.format_size(per_kind[kind])))
        return 0

    # -- deletion helpers -------------------------------------------------

    def _delete_with_confirmation(self, resources, prompt) -> int:
        if not resources:
            print('No matching resources.')
            return 0

        total = sum(resource.size_bytes for resource in resources)
        print('Selected {} resource(s), {}:'.format(len(resources), helpers.format_size(total)))
        for resource in resources:
            print('  [{}] {}  ({})  {}'.format(
                resource.kind,
                resource_label(resource),
                helpers.format_size(resource.size_bytes),
                resource.path))

        deletable = [resource for resource in resources if not resource.is_read_only]
        read_only = [resource for resource in resources if resource.is_read_only]
        if read_only:
            print('Skipping {} resource(s) in read-only caches.'.format(len(read_only)))

        if self.options.dry_run:
            print('Dry run: nothing was deleted.')
            return 0

        if not deletable:
            print('Nothing to delete.')
            return 0

        if not helpers.confirm(prompt, assume_yes=self.options.yes):
            print('Aborted. Nothing was deleted.')
            return 0

        removed, _ = cache_manager.CacheManager.remove_resources(deletable)
        freed = sum(resource.size_bytes for resource in removed)
        print('Removed {} resource(s), freed {}.'.format(len(removed), helpers.format_size(freed)))
        return 0

    # -- remove -----------------------------------------------------------

    def handle_remove(self) -> int:
        if not self.options.pattern:
            print('ERROR: remove requires a path or regex pattern')
            self.print_help()
            return 1

        resources = self._scanned_resources()
        selected = cache_manager.CacheManager.select(
            resources, self.options.pattern, use_regex=self.options.regex)
        return self._delete_with_confirmation(
            selected,
            "Delete these resource(s)?")

    # -- purge ------------------------------------------------------------

    def handle_purge(self) -> int:
        resources = self._scanned_resources()
        return self._delete_with_confirmation(
            resources,
            "Purge ALL selected resource(s) from the caches?")

    # -- unidentified -----------------------------------------------------

    def handle_unidentified(self) -> int:
        resources = self._scanned_resources()
        unidentified = cache_manager.CacheManager.unidentified(resources)

        if not self.options.remove:
            if self.options.as_json:
                print(json.dumps([self._resource_to_dict(r) for r in unidentified], indent=2))
                return 0
            if not unidentified:
                print('No unidentified resources found.')
                return 0
            print('Unidentified resources (no valid manifest):')
            for resource in unidentified:
                print('  {}  ({})  cache: {}'.format(
                    resource.path,
                    helpers.format_size(resource.size_bytes),
                    resource.cache_root))
            return 0

        return self._delete_with_confirmation(
            unidentified,
            "Delete these unidentified resource(s)?")

    # -- dispatch ---------------------------------------------------------

    def handle(self, args: list[str]) -> int:
        dispatch = {
            'list': self.handle_list,
            'caches': self.handle_caches,
            'size': self.handle_size,
            'remove': self.handle_remove,
            'purge': self.handle_purge,
            'unidentified': self.handle_unidentified,
        }

        handler = dispatch.get(self.options.action)
        if handler is None:
            print('ERROR: unsupported cache command: {}'.format(' '.join(args)))
            self.print_help()
            return 1

        return handler()


def handle_cache_command(project_dir: str, args: list[str]) -> int:
    try:
        options = parse_cache_args(args)
    except SystemExit:
        CacheCommandHandler.print_help()
        return 1

    if options.help or options.action is None:
        CacheCommandHandler.print_help()
        return 0

    return CacheCommandHandler(project_dir=project_dir, options=options).handle(args)
