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


def digest(value, length=DIGEST_LENGTH):
    '''What tells two values apart once spelling them safely has lost the difference.'''
    return hashlib.sha256(value.encode('utf-8')).hexdigest()[:length]


def with_digest(text, of):
    '''
    Bind a readable spelling to the value it was spelled from.

    `of` is what gets hashed, which is never `text`: the point is to restore what
    spelling `text` threw away, so the digest has to be taken over the original.
    '''
    return text + DIGEST_SEPARATOR + digest(of)
