import json
import os
import re
from argparse import ArgumentParser
from argparse import Namespace
from dataclasses import dataclass
from dataclasses import field
from datetime import datetime
from datetime import timedelta
from datetime import timezone

from golemcpp.golem.cache_configuration import get_cache_configuration
from golemcpp.golem.settings import get_settings
from golemcpp.golem import cache_manager
from golemcpp.golem import helpers
from golemcpp.golem import locator
from golemcpp.golem import resource_manager
from golemcpp.golem import safe_part
from golemcpp.golem import source
from golemcpp.golem.source import Source


# The widest a cache key prints in the listing before its middle is cut out. A
# key naming a dependency ("<name>@<host>+<revision>") fits, where one made from
# a deep local path would push every column after it off screen.
KEY_WIDTH = 44

# What stands in for the part of a value the listing had to leave out, and for a
# column a resource has nothing to say in.
ELLIPSIS = '...'
NOTHING = '-'

# The listing columns holding a size and an age (see resource_cells). Both are
# compared down the column instead of read across the line, therefore they are
# the two that align right.
RIGHT_ALIGNED_COLUMNS = (4, 5)

# How a duration is written, and how long each unit lasts. These are the units
# humanize_age prints, so an age read off the listing ("9d ago") is a duration
# `--older-than` accepts. Therefore `m` is minutes here as it is there.
DURATION = re.compile(r'^(\d+)([smhdw])$')
DURATION_UNITS = {'s': 1, 'm': 60, 'h': 3600, 'd': 86400, 'w': 604800}


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
    parser.add_argument('--older-than', dest='older_than', default='')
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


def parse_duration(text: str) -> timedelta:
    '''
    Read a duration written the way an age is printed ("30d", "6h"). Raises
    ValueError on anything else.
    '''
    match = DURATION.match(text.strip().lower())
    if match is None:
        raise ValueError(
            "'{}' is not a duration: write a number and one of the units "
            "{} (for example 30d)".format(text, ', '.join(DURATION_UNITS)))

    return timedelta(seconds=int(match.group(1)) * DURATION_UNITS[match.group(2)])


def is_older_than(resource, cutoff) -> bool:
    '''
    Was a resource last used before cutoff? A resource nothing identifies carries
    no timestamp, so nothing can say how old it is and it is never older.
    '''
    last_used = _parse_iso(resource.last_used_at)
    return last_used is not None and last_used < cutoff


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
    return Source.from_manifest(resource.manifest).label or str(resource.cache_key)


def shorten(text: str, width: int) -> str:
    '''Cut the middle out of text so that it fits width, keeping both ends.'''
    if len(text) <= width:
        return text
    kept = width - len(ELLIPSIS)
    head = kept - kept // 2
    return text[:head] + ELLIPSIS + text[len(text) - kept // 2:]


def short_revision(revision: str) -> str:
    '''
    Abbreviate a commit to the first characters that identify it, the way a cache
    key names one. A revision naming no commit is left as it is.
    '''
    if resource_manager.GIT_OBJECT_NAME.match(revision):
        return revision[:safe_part.DIGEST_LENGTH]
    return revision


def resource_version(resource) -> str:
    '''
    Make the cell saying which version of its source a resource holds: the
    reference it resolved to, and the commit under that reference when the two
    differ.
    '''
    if not resource.is_identified:
        return 'unidentified'

    resolved = Source.from_manifest(resource.manifest).resolved
    parts = [resolved.reference]
    revision = short_revision(resolved.revision)
    if revision and revision != short_revision(resolved.reference):
        parts.append(revision)

    return ' '.join(part for part in parts if part) or NOTHING


def resource_origin(resource) -> str:
    '''
    Make the cell saying how a resource was obtained: the mode a repository was
    fetched with, or that it was copied from a directory, which has no history to
    obtain part of.
    '''
    if not resource.is_identified:
        return NOTHING
    if Source.from_manifest(resource.manifest).type == source.SOURCE_TYPE_DIRECTORY:
        return source.SOURCE_TYPE_DIRECTORY

    mode = resource.fetched.mode
    return mode.value if mode else NOTHING


def resource_flags(resource) -> str:
    '''Say what is worth knowing about a root beyond what it holds.'''
    if resource.is_identified and not resource.is_installed:
        # A root carrying a manifest and no source directory is an install that
        # never finished.
        return 'incomplete'
    return ''


def resource_cells(resource) -> tuple:
    '''Make the columns of one listing line, in the order they are printed.'''
    return (resource.kind,
            shorten(str(resource.cache_key), KEY_WIDTH),
            resource_version(resource),
            resource_origin(resource),
            helpers.format_size(resource.size_bytes),
            humanize_age(resource.last_used_at),
            resource_flags(resource))


def column_widths(rows) -> list:
    '''Measure how wide every column has to be for the rows sharing a listing.'''
    return [max(len(row[column]) for row in rows) for column in range(len(rows[0]))]


def resource_details(resource) -> list:
    '''
    Make the (label, value) pairs `--long` adds under a resource. Every resource
    shows the same ones, so an entry saying nothing about itself is visibly that.
    '''
    origin = Source.from_manifest(resource.manifest)
    resolved = origin.resolved
    fetched = resource.fetched
    manifest = resource.manifest
    # A copied directory is not fetched at all, therefore it has neither.
    left_behind = (fetched.head, fetched.mode.value if fetched.mode else '')

    return [
        ('source', '{} {}'.format(origin.type, origin.locator) if origin.locator else NOTHING),
        ('version', ' '.join(part for part in (resolved.reference, resolved.revision)
                             if part) or NOTHING),
        ('fetched', ', '.join(part for part in left_behind if part) or NOTHING),
        ('created', humanize_age(resource.created_at)),
        ('manifest', 'version {}, golem {}'.format(
            manifest.version, manifest.golem_version or '?') if manifest else NOTHING),
        ('path', resource.path),
    ]


@dataclass
class CacheCommandHandler:
    project_dir: str
    options: Namespace
    _manager: cache_manager.CacheManager | None = field(default=None, init=False, repr=False)

    @staticmethod
    def print_help() -> None:
        print('Usage: golem cache list [<selection>] [--long] [--json]')
        print('       golem cache caches [--json]')
        print('       golem cache size [<selection>]')
        print('       golem cache remove <path-or-regex> [--regex] [<selection>] [--dry-run] [--yes]')
        print('       golem cache purge [<selection>] [--dry-run] [--yes]')
        print('       golem cache unidentified [--remove] [--dry-run] [--yes]')
        print('Manage resources stored in the caches the project is configured to use.')
        print('')
        print('A <selection> narrows what a subcommand works on:')
        print('  [--kind=<kind>] [--cache=<path>] [--older-than=<age>]')
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
        print('  --older-than=<age>     Keep only the resources last used longer ago than')
        print('                         <age>, written as a number and a unit among')
        print('                         s, m, h, d, w (for example 90d)')
        print('  --regex                Treat the remove pattern as a regular expression')
        print('  --long, -l             Show the source, version, timestamps and path')
        print('                         of every listed resource')
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

    def _older_than_cutoff(self):
        '''
        The moment a resource has to have been used before to be selected, or
        None when nothing narrows the selection by age.
        '''
        if not self.options.older_than:
            return None
        return datetime.now(timezone.utc) - parse_duration(self.options.older_than)

    def _is_narrowed(self) -> bool:
        '''Does anything select less than every resource in every cache?'''
        return any((self.options.kind, self.options.cache, self.options.older_than))

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

        cutoff = self._older_than_cutoff()
        if cutoff is not None:
            resources = [resource for resource in resources
                         if is_older_than(resource, cutoff)]

        # Most recently used first: a cache is read to see what is live in it,
        # and cleaned of what nothing has touched in months. An unidentified
        # resource has no timestamp, therefore it sorts last, under its own name.
        resources = sorted(resources, key=lambda resource: resource.cache_key)
        resources.sort(key=lambda resource: resource.last_used_at, reverse=True)

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

        # Widths are taken over every resource listed, so the caches line up with
        # each other and not only within their own group.
        widths = column_widths([resource_cells(resource) for resource in resources])

        groups = list(self._group_by_cache(resources))
        print('Cached resources:')
        for location, group in groups:
            print('')
            print(self._cache_header(location, group))
            for resource in group:
                self._print_resource(resource, widths)

        if len(groups) > 1:
            print('')
            print('Total: {}'.format(self._totals(resources)))
        return 0

    @staticmethod
    def _totals(resources) -> str:
        return '{} resource(s), {}'.format(
            len(resources),
            helpers.format_size(sum(resource.size_bytes for resource in resources)))

    def _cache_header(self, location, group) -> str:
        read_only = any(resource.is_read_only for resource in group)
        return '{}{}: {}'.format(
            location, ' (read-only)' if read_only else '', self._totals(group))

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
            'fetched': resource.fetched.to_dict(),
            'identified': resource.is_identified,
            'installed': resource.is_installed,
            'manifest_version': resource.manifest_version,
            'cache_root': resource.cache_root,
            'read_only': resource.is_read_only,
            'size_bytes': resource.size_bytes,
            'created_at': resource.created_at,
            'last_used_at': resource.last_used_at,
            'path': resource.path,
        }

    def _print_resource(self, resource, widths) -> None:
        cells = resource_cells(resource)
        aligned = [cell.rjust(width) if column in RIGHT_ALIGNED_COLUMNS else cell.ljust(width)
                   for column, (cell, width) in enumerate(zip(cells, widths))]
        print('  {}'.format('  '.join(aligned).rstrip()))

        if not self.options.long:
            return

        details = resource_details(resource)
        label_width = max(len(label) for label, _ in details)
        for label, value in details:
            print('      {}  {}'.format(label.ljust(label_width), value))
        print('')

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
            if self.options.older_than:
                # Age alone selects nothing here: that is what purging does.
                print('Selecting by age alone is "golem cache purge --older-than={}".'.format(
                    self.options.older_than))
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
        # Purging takes everything unless something narrows it, and the prompt
        # says which of the two is about to happen.
        return self._delete_with_confirmation(
            resources,
            'Purge {} resource(s) from the caches?'.format(
                'these' if self._is_narrowed() else 'ALL'))

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

        # Read before anything scans a cache, so a duration written wrong is said
        # so straight away rather than after walking every location.
        try:
            self._older_than_cutoff()
        except ValueError as error:
            print('ERROR: {}'.format(error))
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
