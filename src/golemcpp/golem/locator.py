'''
Where a source is, once it has been read.

A locator is the middle of a location: `[<kind>+]<locator>[#<version>]`.

It is absolute, context-free, naming no version, and a string git takes as it
stands. Holding one means the reading already happened, so nothing downstream has
to ask what it means.

Two shapes reach that. A `file://` URL names something on this filesystem, and is
what a path configured relative to a project becomes.

Everything else is a remote locator kept exactly as it was written, because that
set is open: `<transport>::` dispatches to any `git-remote-<transport>` on PATH,
and `url.<base>.insteadOf` lets a git configuration invent prefixes golem cannot
know about. So golem recognises the one case it has to act on, a bare path, and
passes the rest along.
'''

import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote, unquote, urlparse

from golemcpp.golem import helpers
from golemcpp.golem import safe_part


# What separates a scheme from the rest of a URL. A locator holding one names
# nothing on this filesystem unless that scheme is `file`.
URL_SCHEME_SEPARATOR = '://'

# A single letter before the colon is a Windows drive, not a host: `C:/proj` is a
# path where `host:proj` is an scp-style remote.
DOS_DRIVE = re.compile(r'^[a-zA-Z]:[\\/]')

# Drive segment of a Windows path. E.g. C:
DRIVE_SEGMENT = re.compile(r'^(?P<letter>[a-zA-Z]):$')

FILE_SCHEME = 'file'

# `<transport>::<address>`, dispatched to a `git-remote-<transport>` helper. The
# address is defined by that helper rather than by git, so golem has no grammar
# for it.
# 
# E.g. `ext::sh -c foo` is a command and `bzr::lp:project` is a bzr alias,
# neither of which names a hierarchy.
# 
# Only an address that is itself a URL is read, see is_opaque for the rest.
TRANSPORT_HELPER = re.compile(
    r'^(?P<transport>[a-zA-Z][a-zA-Z0-9+.-]*)::(?P<address>.+)$')

# `[user@]host:path`, the ssh shorthand git accepts.
SCP_STYLE = re.compile(r'^(?:(?P<user>[^/@]+)@)?(?P<host>[^/:]+):(?P<path>.+)$')

# What scp-style is read under, so it cannot flatten onto `ssh://`.
#
# Note that `git@host:repo.git` and `ssh://host/repo.git` name two different
# repositories. The former is relative to the user's home, the latter is 
# an asbolute path.
SCP_IDENTITY_SCHEME = 'scp+ssh'

# The only two characters that cannot sit raw in a netloc: urlparse reads a
# bracket as the start of an IPv6 literal and then refuses the whole locator.
NETLOC_BREAKING = str.maketrans({'[': '%5B', ']': '%5D'})

# The port each transport uses when none is written.
DEFAULT_PORTS = {
    SCP_IDENTITY_SCHEME: 22,
    'ssh': 22,
    'git': 9418,
    'http': 80,
    'https': 443,
    'ftp': 21,
    'ftps': 990,
}

# What a character outside the safe sets becomes.
# Read a `~` as "something outside the safe set was here, possibly a `~`".
SUBSTITUTE_MARKER = '~'

# What survives into an id. Anything else is substituted rather than dropped.
UNSAFE_IN_ID = re.compile(r'[^0-9a-zA-Z_-]')

# The same, for the repository name, which may also hold a `.`.
UNSAFE_IN_ID_NAME = re.compile(r'[^0-9a-zA-Z._-]')

# Exact complements of the two filters above, so that "verbatim" means precisely
# "nothing was substituted" and the predicate cannot claim otherwise.
VERBATIM_IN_ID = re.compile(r'^[A-Za-z0-9_-]+$')
VERBATIM_IN_ID_NAME = re.compile(r'^[A-Za-z0-9._-]+$')

# How many path segments a forge locator names: an owner and a repository. Fixing
# it is what makes the boundary between the host and the path recoverable.
# Otherwise, left free `https://a.b/c/d` and `https://c.a.b/d` are both `d@b.a.c`.
FORGE_PATH_SEGMENTS = 2

# The host half of an id for a locator that names no host git can see.
NO_HOST = '_no_host_'

# The host half of an id for a local locator, whose path stands in for a host.
FILESYSTEM_HOST = 'fsys'


def parse_url(value):
    '''
    Parses the URL and raises a meaningful error message in case it fails.
    '''
    try:
        return urlparse(value)
    except ValueError as error:
        raise ValueError(
            "locator '{}' cannot be read as a URL: {}".format(value, error)) from error


def is_bare_path(value):
    '''
    Whether a locator is a path on this filesystem, written as one.

    Git's rule, taken as it stands so golem can never disagree with git about
    what a locator is: a `:` before the first `/` makes it a remote, which is why
    a path holding one has to be written `./weird:name`.
    '''
    if URL_SCHEME_SEPARATOR in value:
        return False
    if DOS_DRIVE.match(value):
        return True
    return ':' not in value.split('/', 1)[0]


def url_components(parsed):
    '''
    The host and the path segments a parsed locator holds, both possibly empty.

    Segments come back decoded and the hostname is left exactly as it stands.
    '''
    return (parsed.hostname or '',
            [unquote(segment) for segment in parsed.path.split('/') if segment])


def without_drive_colon(segments):
    '''
    The segments with a leading Windows drive spelled by its letter alone.

    Readable half only. What tells `C:/proj/mylib` from the ordinary POSIX path
    `/c/proj/mylib` is the digest. See `names_one_repository` for the details.
    '''
    if not segments:
        return segments

    match = DRIVE_SEGMENT.match(segments[0])
    if not match:
        return segments

    return [match.group('letter')] + segments[1:]


def names_verbatim(components):
    '''
    Whether every component survives the filter with only its case changed.

    The last one is the repository name, which may hold a `.`; the rest may not.
    '''
    if not components:
        return False
    return (all(VERBATIM_IN_ID.match(part) for part in components[:-1])
            and bool(VERBATIM_IN_ID_NAME.match(components[-1])))


def without_git_suffix(segments):
    '''The segments with `.git` off the last one: `repo` and `repo.git` are one.'''
    if segments and segments[-1].endswith('.git'):
        return segments[:-1] + [segments[-1][:-4]]
    return segments


def names_one_repository(url):
    '''
    Whether a locator's identity stands on its own, without a digest.

    Two things have to hold:

    1. Every component has to survive UNSAFE_IN_ID intact but for its case, or
    `socket.io` and `socketio` come out as one name.

    2. The boundary between the host and the path has to be recoverable, which
    is what a fixed segment count fixes.

    The shape that satisfies both is the one a forge uses `<host>/<owner>/<repository>`.
    Anything else is named the same way and told apart by a digest.
    '''
    parsed = parse_url(url)
    hostname, segments = url_components(parsed)
    segments = without_git_suffix(segments)

    try:
        port = parsed.port
    except ValueError:
        # A port urlparse cannot read is git's to complain about, not golem's to
        # refuse over. Unconfirmed is not the forge shape, so it digests.
        return False

    if port and port != DEFAULT_PORTS.get(parsed.scheme):
        # Two ports on one host are two servers, and an id cannot say so.
        return False

    if url.startswith(FILE_SCHEME + URL_SCHEME_SEPARATOR):
        # The marker is the whole head here, so the boundary needs no fixing and
        # a local path may be any depth.
        return not hostname and names_verbatim(segments)

    labels = hostname.split('.') if hostname else []
    if len(labels) < 2 or labels[-1] == FILESYSTEM_HOST:
        # A single-label host leaves too little to tell a host from a path, and
        # one ending in the marker would read as a local locator.
        return False
    if len(segments) != FORGE_PATH_SEGMENTS:
        return False

    return names_verbatim(labels + segments)


def is_opaque(value):
    '''
    Whether a locator holds no hierarchy golem is able to read.

    A transport helper hands its address to `git-remote-<transport>`, which is the
    only thing that knows how to read it.
    
    E.g. `ext::sh -c foo` is a command line and `bzr::lp:project` is a bzr alias.

    An address that is itself a URL is the exception, and the documented common
    case: `hg::https://host/repo` names the repository the URL names.
    '''
    match = TRANSPORT_HELPER.match(value)
    return bool(match) and URL_SCHEME_SEPARATOR not in match.group('address')


def opaque_id(value):
    '''
    Make the identity of a locator nothing can read a hierarchy out of.
    '''
    transport = TRANSPORT_HELPER.match(value).group('transport')

    return safe_part.with_digest(
        '{}@{}'.format(
            UNSAFE_IN_ID_NAME.sub(SUBSTITUTE_MARKER, transport).lower(),
            NO_HOST),
        of=value)


def as_url(value):
    '''
    A locator in a shape urlparse can read.

    For identity only. What git is handed is always what was written.

    Reads nothing off the filesystem.

    Every *path* this builds a URL out of is encoded on the way in, so what comes
    back out can be decoded without guessing. An scp path and a Windows path are
    filesystem paths rather than URLs, and a `#` in one is a character in a
    directory name, not a fragment. An authority is the exception and goes in as
    it stands, bar the two characters that would break the netloc: a host is not
    percent-encoded, so encoding one would leave no correct way to read it back.
    '''
    match = TRANSPORT_HELPER.match(value)
    if match and URL_SCHEME_SEPARATOR in match.group('address'):
        # Only process URL addresses.
        #
        # Any other address is opaque and must never reach here. See
        # generate_id for the details.
        #
        #   hg::https://hg.example.com/repo -> https://hg.example.com/repo
        return as_url(match.group('address'))

    if URL_SCHEME_SEPARATOR in value:
        # Already a URL, already properly encoded.
        #
        #   https://github.com/nlohmann/json.git -> unchanged
        #   file:///srv/git/mylib.git            -> unchanged
        return value

    if DOS_DRIVE.match(value):
        # Make an absolute path on Windows a URL.
        #
        #   C:/proj/mylib      -> file:///C:/proj/mylib
        #   C:\proj\weird#name -> file:///C:/proj/weird%23name
        return 'file:///' + quote(
            value.replace('\\', '/').lstrip('/'), safe='/:')

    if is_bare_path(value):
        # Make a path a URL and ensure it is absolute.
        #
        # A relative path means relative to the current directory. But a locator
        # arriving through a Locator was made absolute against its project long
        # before this.
        #
        #   /srv/git/mylib.git -> file:///srv/git/mylib.git
        #   ../mylib           -> file:///<parent of cwd>/mylib
        #   ./weird:name       -> file:///<cwd>/weird%3Aname
        return Path(os.path.abspath(value)).as_uri()

    match = SCP_STYLE.match(value)
    if match:
        # Make a SCP style locator a URL.
        #
        # The path is percent-encoded because a URL path is; the authority is not,
        # because a netloc is not.
        #
        #   git@github.com:nlohmann/json.git
        #       -> scp+ssh://git@github.com/nlohmann/json.git
        #   host.xz:repo.git   -> scp+ssh://host.xz/repo.git
        #   git@wéird:repo.git -> scp+ssh://git@wéird/repo.git
        authority = match.group('host').translate(NETLOC_BREAKING)
        if match.group('user'):
            authority = '{}@{}'.format(
                match.group('user').translate(NETLOC_BREAKING), authority)
        return '{}://{}/{}'.format(
            SCP_IDENTITY_SCHEME, authority, quote(match.group('path')))

    # What is left names neither a host nor a path.
    # 
    # Encoded like a path so what comes back out decodes the same way, and
    # identified by the digest, since there is no hierarchy in it to read.
    #
    #   :repo -> %3Arepo
    #   a:    -> a%3A
    return quote(value)


def generate_id(value):
    '''
    Make the identity of the source a locator names, whatever version is asked
    of it.

    The output is a published contract for the shape a forge uses. It is the
    recipe directory name in the cookbook, e.g. `json@com.github.nlohmann`,
    looked up by `Context.load_recipe`.

    Spelling a locator safely is lossy, so any other shape is followed by a
    digest of the whole thing, the way `make_revision_component` does for a
    revision.

    Takes a raw string rather than a Locator, since callers reach it with a git
    remote URL read straight out of a repository.
    '''
    if not value:
        return ''

    if is_opaque(value):
        # Answered before as_url, so nothing tries to read a URL out of a value
        # that is not one.
        return opaque_id(value)

    url = as_url(value)
    hostname, segments = url_components(parse_url(url))

    if not hostname and not segments:
        raise ValueError(
            "locator '{}' names no repository: a scheme on its own identifies "
            "nothing".format(value))

    segments = without_git_suffix(segments)

    if url.startswith(FILE_SCHEME + URL_SCHEME_SEPARATOR):
        # A local locator has no host to reverse, so its path stands in for one
        # behind a marker: `file:///tmp/mylib` is `mylib@fsys.tmp`.
        head = [FILESYSTEM_HOST] + (hostname.split('.') if hostname else [])
        # Every spelling of a Windows path converges on a `file://` URL, so the
        # drive is trimmed here rather than in as_url, which a path already
        # normalized on Windows never reaches.
        segments = without_drive_colon(segments)
    else:
        head = list(reversed(hostname.split('.'))) if hostname else []

    parts = [component for component in head + segments if component]

    if not parts:
        raise ValueError(
            "locator '{}' names no repository: nothing in it survives as a "
            "name".format(value))

    # The last part is the repository name, which is allowed the extra character.
    components = [UNSAFE_IN_ID.sub(SUBSTITUTE_MARKER, part).lower()
                  for part in parts[:-1]]
    components.append(
        UNSAFE_IN_ID_NAME.sub(SUBSTITUTE_MARKER, parts[-1]).lower())

    readable = '{}@{}'.format(components[-1], '.'.join(components[:-1]) or NO_HOST)

    if names_one_repository(url):
        return readable

    # Digested over the normalized form, so every spelling of one repository
    # still lands on one id.
    return safe_part.with_digest(readable, of=url)


@dataclass(frozen=True)
class Locator:
    '''
    A settled locator. Empty means a source names none, the way an empty
    ResolvedVersion means nothing was resolved.
    '''

    value: str = ''

    def __post_init__(self):

        if not self.value:
            return
        
        # A bare path is not a resolved locator.
        if is_bare_path(self.value):
            raise ValueError(
                "locator '{}' is a path, not a settled locator: it has to be "
                "resolved against a project first".format(self.value))
        
        # Must be a valid URL
        hostname, segments = url_components(parse_url(self.value))
        if not hostname and not segments:
            raise ValueError(
                "locator '{}' names nothing: a scheme on its own identifies no "
                "source".format(self.value))

    def __bool__(self) -> bool:
        return bool(self.value)

    def __str__(self) -> str:
        return self.value

    def is_local(self) -> bool:
        '''Whether this names something on the filesystem golem is running on.'''
        return parse_url(self.value).scheme == FILE_SCHEME

    def get_local_path(self):
        '''The local path this names, or None when it names no local path.'''
        parsed = parse_url(self.value)

        if parsed.scheme != FILE_SCHEME:
            return None

        path = unquote(parsed.path)

        if sys.platform.startswith("win"):
            if path.startswith("/") and len(path) > 2 and path[2] == ":":
                path = path[1:]
            path = path.replace("/", "\\")

        return path

    def is_existing_directory(self) -> bool:
        '''Whether this names a directory that is there to read.'''
        path = self.get_local_path()
        return path is not None and os.path.isdir(path)

    def is_git_repository(self) -> bool:
        '''Whether this names a local repository git can clone from.'''
        path = self.get_local_path()
        return path is not None and helpers.is_git_repository(path=path)

    def get_id(self) -> str:
        return generate_id(self.value)
