'''
The parts an identity is composed of.

Golem names a directory or a file after the value it holds, and that name has to
identify the value: two of them must never land on one name. Such a name is
composed of parts, and a part is spelled from something that came from outside
Golem's realm (e.g. a path segment, a host label, a git ref) into something legal
on the strictest platform Golem runs on.

Spelling is lossy, therefore a part carries a digest of what it was spelled from
whenever the safe spelling lost what told it from another. That is the whole
reason a digest exists here, and it is why the mechanism lives in one place while
the policy does not: a locator digests only what it had to substitute, a revision
digests always, and an advertisement digests only what it had to cut.
'''

import hashlib
import re


# What a character outside a safe set becomes.
# Read a `~` as "something outside the safe set was here, possibly a `~`".
SUBSTITUTE_MARKER = '~'

# Binds a lossy spelling to the digest that tells it apart. Outside every safe
# set, so it can never appear in the half it delimits.
DIGEST_SEPARATOR = '='

# How much of a digest is kept. Thirty-two bits reads thin on its own, but a
# digest only ever separates values whose readable halves already match, so the
# space it works in is one readable half rather than the whole cache.
DIGEST_LENGTH = 8

# How much of a value is kept for reading, before the digest takes over. Not how
# long a part is: a digested one runs to this plus the separator plus the digest.
READABLE_LENGTH = 40

# What a part joined to its neighbours with a `.` may not hold: a `.`, or
# `group.subgroup` and `group/subgroup` spell the same.
UNSAFE_IN_DOT_JOINED = re.compile(r'[^0-9a-zA-Z_-]')

# What a part nothing is joined onto may hold, which is the same plus a `.`: a
# repository is called socket.io, and a reference v1.0.0.
#
# Deliberately defined as an independant regex from the one above, but they have to
# agree with each other. Appending the dot to the set above would have not been
# accepted as a valid regex. E.g. _-. is invalid.
UNSAFE_IN_STANDALONE = re.compile(r'[^0-9a-zA-Z._-]')

# The marker and the separator have to be unspellable, or a substituted `~` reads
# as one that was really there and a `=` appears in the half it delimits.
for _charset in (UNSAFE_IN_DOT_JOINED, UNSAFE_IN_STANDALONE):
    assert _charset.match(SUBSTITUTE_MARKER), 'the marker has to be unsafe'
    assert _charset.match(DIGEST_SEPARATOR), 'the separator has to be unsafe'


def spell(value, charset):
    '''
    Spell a value safely, and say whether saying it that way lost anything.

    Substitutes before folding case so that, for example, a U+212A KELVIN SIGN
    doesn't turn into a plain `k` and reports no loss.

    Case folding itself is not a loss. NTFS and APFS are case-insensitive, so
    case cannot carry meaning in a directory name anyway.
    '''
    spelled = charset.sub(SUBSTITUTE_MARKER, value).lower()
    return spelled, spelled != value.lower()


def digest(value, length=DIGEST_LENGTH):
    '''
    What tells two values apart when their readable halves cannot.

    Either because spelling them safely lost the difference, which is what
    `with_digest` binds back, or because the value has no readable form worth
    keeping and the digest stands in for the whole of it.
    '''
    return hashlib.sha256(value.encode('utf-8')).hexdigest()[:length]


def with_digest(text, of):
    '''
    Bind a readable spelling to the value it was spelled from.

    `of` is what gets hashed, which is never `text`: the point is to restore what
    spelling `text` threw away, so the digest has to be taken over the original.
    '''
    return text + DIGEST_SEPARATOR + digest(of)
