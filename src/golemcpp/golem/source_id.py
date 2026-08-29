"""
What Golem names a source after, whatever version is asked of it.

    @<name>[=<d>][@<owner>[=<d>][@<host>[=<d>][@<rooting>[=<d>]]]]

Four fields, spelled from what a locator holds:

- `<name>` is the last path segment. The one field that may hold a literal `.`,
  because a repository is called socket.io and nothing is joined onto it here.
- `<owner>` is the segments above the name, joined by `.`.
- `<host>` is the hostname, in natural order.
- `<rooting>` is what the path is relative to, empty for the ordinary case.

Spelling is lossy, therefore a field carries `=<digest>` when spelling it lost
what told it from another. Each digest is taken over what its own field was read
from, so a difference outside that field never reaches it.

An identity leads with `@`. That is what tells a recipe from the furniture a
cookbook repository also holds (e.g. an `AGENTS.md`, a `README`, a `.github/`),
therefore a listing selects on it.
"""

from dataclasses import dataclass
from dataclasses import replace

from golemcpp.golem import locator as locator_module
from golemcpp.golem import safe_part

# What the fields are spelled as when a locator names no host Golem can read,
# and when it names this filesystem. A digest is added when a host is really
# spelled like one of these to avoid any conflict.
LOCAL_HOST = "_local_"
NO_HOST = "_nohost_"

# The rooting field's vocabulary. All chosen by Golem so none can be mistaken
# for data.
SCP_ROOTING = "scp"
DRIVE_ROOTING = "drive"

# What separates the fields, and what marks the start of an identity.
FIELD_SEPARATOR = "@"

# What joins the parts inside the owner and the host.
PART_SEPARATOR = "."

# The `.git` a path may end in, which means two different things by position.
GIT_SUFFIX = ".git"


def spell_field(value, charset=safe_part.UNSAFE_IN_DOT_JOINED, of=None):
    """Spell one field, and add a digest when spelling it lost something."""
    if not value:
        return ""

    spelled, lossy = safe_part.spell(value, charset)

    if not lossy:
        return spelled

    return safe_part.with_digest(spelled, of=value if of is None else of)


def spell_joined_field(parts, of=None):
    """
    Spell several parts as one dotted field, digested if any of them lost
    something.

    The digest is taken over the parts as they were written, joined by `/`,
    therefore two segment lists reaching one spelling still reach two digests.
    """
    if not parts:
        return ""

    spelled = []
    lossy = False

    for part in parts:
        text, part_lossy = safe_part.spell(part, safe_part.UNSAFE_IN_DOT_JOINED)
        spelled.append(text)
        lossy = lossy or part_lossy

    text = PART_SEPARATOR.join(spelled)

    if not lossy:
        return text

    return safe_part.with_digest(text, of="/".join(parts) if of is None else of)


def port_of(parsed):
    """
    Read the port a locator names: the number urlparse gave, the raw text when
    it refused, or None when none was written.

    A port Golem could not read is data it did not understand, therefore it is
    carried rather than dropped. Otherwise `:99999` merges onto no port at all.
    """
    try:
        return parsed.port
    except ValueError:
        authority = parsed.netloc.rpartition("@")[2]
        _, colon, text = authority.rpartition(":")
        return text if colon else None


def strip_git(segments, local):
    """
    Drop the `.git` a path ends in, by position and by who reads the path.

    A whole segment is the git directory of the worktree above it, therefore it
    names that repository and the level drops.

    A suffix is a convention for a bare repository. A server serves `/o/repo`
    and `/o/repo.git` as one, but a filesystem has two entries, therefore the
    suffix is kept for a local path.
    """
    if not segments:
        return segments

    last = segments[-1]

    if last.lower() == GIT_SUFFIX:
        return segments[:-1]

    if not local and last.lower().endswith(GIT_SUFFIX):
        return segments[:-1] + [last[: -len(GIT_SUFFIX)]]

    return segments


def rooting_of(parsed, segments, local):
    """
    Make the field saying what the path is relative to.

    A scheme is a road to a server rather than a different server, therefore
    every ordinary transport leaves this empty. Two forms name another root: an
    scp path hangs off a user's home, and a Windows drive is a root of its own.
    """
    if parsed.scheme == locator_module.SCP_IDENTITY_SCHEME:
        # An scp path is relative to the named user's home, so the user is part
        # of the root: alice@host:repo and bob@host:repo are two repositories.
        if not parsed.username:
            return SCP_ROOTING
        return SCP_ROOTING + PART_SEPARATOR + spell_field(parsed.username)

    if local and segments:
        # A drive is a root beside the others rather than a directory under
        # one, so `C:/proj/mylib` is not the POSIX path `/c/proj/mylib`.
        drive = locator_module.DRIVE_SEGMENT.match(segments[0])
        if drive:
            return DRIVE_ROOTING + PART_SEPARATOR + spell_field(drive.group("letter"))

    return ""


def host_of(parsed, hostname, local):
    """Make the host field: a hostname in natural order, or a sentinel."""
    if local:
        return LOCAL_HOST

    if not hostname:
        return NO_HOST

    host = spell_joined_field(hostname.split(PART_SEPARATOR))
    port = port_of(parsed)

    if port is not None and port != locator_module.DEFAULT_PORTS.get(parsed.scheme):
        # Two ports on one host are two servers, and the readable half cannot
        # say so. Digested over the host and the port that were read, so the
        # userinfo an absolute URL discards cannot come back in through here.
        return "{}{}{}".format(
            host.split(safe_part.DIGEST_SEPARATOR)[0],
            safe_part.DIGEST_SEPARATOR,
            safe_part.digest("{}:{}".format(hostname.lower(), port)),
        )

    if host in (LOCAL_HOST, NO_HOST):
        # A host really spelled like a sentinel has to say it is not one. Only
        # an exact single-label host can collide: natural order leaves
        # `_local_.example.com` spelling itself.
        return safe_part.with_digest(host, of=hostname.lower())

    return host


@dataclass(frozen=True)
class SourceId:
    """
    The identity of the source a locator names.

    Every field holds its own safe spelling with its own digest already bound
    to it, so the identity is exactly what the fields spell and reading one
    back is a split rather than a parse.
    """

    name: str = ""
    owner: str = ""
    host: str = ""
    rooting: str = ""

    def fields(self) -> list:
        """List the four fields, outermost first, the order the grammar spells them."""
        return [self.name, self.owner, self.host, self.rooting]

    def __bool__(self) -> bool:
        return bool(self.name)

    def __str__(self) -> str:
        """
        Spell the identity, leaving off trailing empty fields.

        A field is written as soon as something after it has to be. Therefore
        `@repo@@host.xz` spells an empty owner, and `@repo` does not end in a
        bare separator.
        """
        if not self.name:
            return ""

        name, owner, host, rooting = self.fields()
        text = FIELD_SEPARATOR + name

        if owner or host or rooting:
            text += FIELD_SEPARATOR + owner
        if host or rooting:
            text += FIELD_SEPARATOR + host
        if rooting:
            text += FIELD_SEPARATOR + rooting

        return text

    @staticmethod
    def parse(text):
        """
        Read an identity back out of its spelling, folding case.

        A field can never hold a `@`, since it is outside every safe set,
        therefore this splits rather than parses. Trailing empty fields are
        accepted and dropped, so `@repo@@` reads as `@repo`.

        Raise when the text does not lead with `@`, names more than four
        fields, or leaves the name out.
        """
        if not text:
            return SourceId()

        if not text.startswith(FIELD_SEPARATOR):
            raise ValueError(
                "identity '{}' does not start with '{}': every identity does, "
                "so that a recipe is told from the furniture a cookbook also "
                "holds".format(text, FIELD_SEPARATOR)
            )

        fields = text[len(FIELD_SEPARATOR) :].lower().split(FIELD_SEPARATOR)

        if len(fields) > 4:
            raise ValueError(
                "identity '{}' names more than the four fields an identity "
                "has".format(text)
            )

        if not fields[0]:
            raise ValueError(
                "identity '{}' names no name, which is the one field an "
                "identity cannot leave out".format(text)
            )

        return SourceId(*(fields + [""] * (4 - len(fields))))

    @staticmethod
    def from_locator(value):
        """
        Compose the identity of the source a locator names.

        The argument is a raw string rather than a Locator, because callers
        reach this with a git remote URL read straight out of a repository.

        Raise when the locator names no path, since there is no segment to be a
        name.
        """
        if not value:
            return SourceId()

        if locator_module.is_opaque(value):
            # No hierarchy to read at all, so the rooting field is a bare
            # digest: the escape hatch every field has, with nothing readable
            # in front of it. Answered before as_url, so nothing tries to read
            # a URL out of a value that is not one.
            transport = locator_module.TRANSPORT_HELPER.match(value).group("transport")
            return SourceId(
                name=spell_field(transport, safe_part.UNSAFE_IN_STANDALONE),
                host=NO_HOST,
                rooting=safe_part.DIGEST_SEPARATOR + safe_part.digest(value),
            )

        url = locator_module.as_url(value)
        parsed = locator_module.parse_url(url)
        hostname, segments = locator_module.url_components(parsed)

        local = url.startswith(
            locator_module.FILE_SCHEME + locator_module.URL_SCHEME_SEPARATOR
        )
        segments = strip_git(segments, local)
        rooting = rooting_of(parsed, segments, local)

        if local and segments and locator_module.DRIVE_SEGMENT.match(segments[0]):
            # The drive went into the rooting field, so it is not also a path
            # part: `C:/proj/mylib` is `mylib` under `proj`, rooted at C.
            segments = segments[1:]

        if not segments:
            raise ValueError(
                "locator '{}' names no repository: nothing in it is a "
                "name".format(value)
            )

        return SourceId(
            name=spell_field(segments[-1], safe_part.UNSAFE_IN_STANDALONE),
            owner=spell_joined_field(segments[:-1]),
            host=host_of(parsed, hostname, local),
            rooting=rooting,
        )

    def rungs(self):
        """
        Yield this identity and the less qualified ones above it, most specific
        first.

        Probing drops the last field, which is how a recipe named at
        `@json@nlohmann@github.com` answers a project cloned over ssh. A
        trailing empty field is never spelled, therefore an identity with one
        has fewer than four rungs: `@repo@@host.xz` drops straight to `@repo`.
        """
        fields = self.fields()
        seen = set()

        for kept in range(len(fields), 0, -1):
            rung = SourceId(*(fields[:kept] + [""] * (len(fields) - kept)))
            if not rung:
                break
            if str(rung) not in seen:
                seen.add(str(rung))
                yield rung

    def filled_from(self, other):
        """
        Fill this identity's empty fields from another, and keep the ones it
        states.

        Therefore `@boost` keys to `@boost@boostorg@github.com`, while
        `@boost@somefork@github.com` stays as it was written.
        """
        return replace(
            self,
            **{
                field: getattr(self, field) or getattr(other, field)
                for field in ("name", "owner", "host", "rooting")
            },
        )
