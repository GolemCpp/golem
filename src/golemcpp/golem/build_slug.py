"""
The name a build's own configuration goes by.

A slug names every input that decides whether one artifact can substitute for
another: the target it is for, the toolchain that made it, and the high-level
choices Golem offers for configuring a project. Nothing specific to the project
being built belongs here, which is what keeps `-std=`, sanitizers and custom
flags out of it.

It is written to be read. Someone looking at a cache directory should recognise
their own configuration in its name, and get back to it from what they typed.
So the name is *parseable*, and that is enforced rather than hoped for: a value
that would render an unreadable name is refused at construction.
"""

from dataclasses import dataclass, fields

# Legal in a filename on every platform Golem targets.
SEPARATOR = "~"

LINKAGES = {"shared": "sh", "static": "st"}
VARIANTS = {"debug": "d", "release": "r"}

# The fields with a closed vocabulary, which render short.
FIELD_VOCABULARIES = {
    "runtime_link": LINKAGES,
    "runtime_variant": VARIANTS,
    "link": LINKAGES,
    "variant": VARIANTS,
}

FIELD_SPELLINGS = {
    name: {short: word for word, short in vocabulary.items()}
    for name, vocabulary in FIELD_VOCABULARIES.items()
}


# TODO: near-identities are not reused, and one day should be. Built for a
# lower baseline runs on a higher one, and a patch release of a compiler is
# usually compatible with the one before it. E.g. `i386 ⊑ i486 ⊑ i586 ⊑ i686`,
# x86-64-v1..v4, and gcc 13.4.0 against 13.4.1 are all the same question.
#
# That question is a ranking over identities driven by a policy, and it does
# not belong here: a slug says what a build *is*, and coarsening it to win
# cache hits is how i386 and i686 came to share a name in the first place. So
# the compiler version stays as precise as the toolchain reports it. E.g. C++
# module reuse depends on the exact version. And nothing is reused until the
# ranking exists. Should a C++ standard library field ever be added, that field
# answers its own ABI question rather than the compiler field answering by
# proxy.
@dataclass(frozen=True)
class BuildSlug:
    """
    What a build was configured for, as one value.

    The constructor is the contract. Every field is something that decides
    whether an artifact can stand in for another, so adding an axis means
    changing this signature, and what a build's identity depends on can be read
    in one place.
    """

    osystem: str
    arch: str
    compiler: str
    runtime_link: str
    runtime_variant: str
    link: str
    variant: str

    def __post_init__(self):
        for field in fields(self):
            value = getattr(self, field.name)
            vocabulary = FIELD_VOCABULARIES.get(field.name)

            if vocabulary is not None:
                if value not in vocabulary:
                    raise ValueError(
                        "'{}' is not a {}: it is one of {}.".format(
                            value,
                            field.name.replace("_", " "),
                            ", ".join(sorted(vocabulary)),
                        )
                    )
                continue

            if not value:
                raise ValueError(
                    "A build slug needs {} to name what it was built for; "
                    "leaving it out would name two different builds the "
                    "same.".format(field.name)
                )
            if SEPARATOR in value:
                raise ValueError(
                    "'{}' cannot be a {}: '{}' separates a slug's fields, so "
                    "the name could not be read back.".format(
                        value, field.name, SEPARATOR
                    )
                )

    def __str__(self):
        return SEPARATOR.join(
            FIELD_VOCABULARIES.get(field.name, {}).get(
                getattr(self, field.name), getattr(self, field.name)
            )
            for field in fields(self)
        )

    @staticmethod
    def parse(name):
        """
        Read a slug back into the configuration it names.

        Refuses a name this format did not write, which is how a directory left
        behind by an earlier one is recognised.
        """
        names = [field.name for field in fields(BuildSlug)]
        values = str(name).split(SEPARATOR)
        if len(values) != len(names):
            raise ValueError(
                "'{}' is not a build slug: {} fields where there are "
                "{}.".format(name, len(values), len(names))
            )

        settled = {}
        for field_name, value in zip(names, values):
            spellings = FIELD_SPELLINGS.get(field_name)
            if spellings is None:
                settled[field_name] = value
                continue
            if value not in spellings:
                raise ValueError(
                    "'{}' is not a build slug: '{}' spells no {}.".format(
                        name, value, field_name.replace("_", " ")
                    )
                )
            settled[field_name] = spellings[value]

        return BuildSlug(**settled)
