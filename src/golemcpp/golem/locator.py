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
    The identity of the source a locator names, spelled.

    A thin reading of `SourceId`, kept here because every caller reaches it with
    a locator rather than with an identity. `source_id.SourceId.from_locator`
    is what to use when the fields themselves are wanted.
    '''
    # Imported here rather than at the top: source_id reads a locator, so the
    # two modules would otherwise import each other.
    from golemcpp.golem.source_id import SourceId

    return str(SourceId.from_locator(value))


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
