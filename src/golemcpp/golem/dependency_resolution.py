"""
What Golem worked out about a dependency, beside what the golemfile declared.

A declaration says as much as its author knew. E.g. a locator, or an identity.

Everything past that needs something the golemfile does not contain. E.g. the project
directory, a cookbook, a remote. All of it lands here, so a build reads one place and
never consults a declaration.

Filled in two passes. Reading the location settles the locator and the kind. Resolving
settles the rest.
"""

from dataclasses import dataclass
from dataclasses import field
from dataclasses import replace

from golemcpp.golem.resolved_version import ResolvedVersion
from golemcpp.golem.source_id import SourceId


@dataclass(frozen=True)
class RecipeLink:
    """
    One recipe a dependency was served by, and the cookbook holding it.

    It is a record of a DeclaredRecipe, but for what DependencyResolution needs.
    """

    name: str = ""
    cookbook: str = ""

    def to_dict(self) -> dict:
        return {"name": self.name, "cookbook": self.cookbook}

    @classmethod
    def from_dict(cls, data) -> "RecipeLink":
        return cls(name=data.get("name", ""), cookbook=data.get("cookbook", ""))


@dataclass(frozen=True)
class DependencyResolution:
    """Where a dependency comes from, and what it turned out to be."""

    # Where Golem fetches it from, and what it does with what it finds.
    locator: str = ""
    kind: str = ""
    # What names it in a cache, composed from the locator.
    identity: SourceId = None
    # Which version the request landed on. A copied directory has none.
    version: ResolvedVersion = field(default_factory=ResolvedVersion)
    # Which recipes served it, most derived first. Empty where a recipe served
    # none of it, and where nothing fetched it to find out.
    recipe: tuple = ()

    def __bool__(self) -> bool:
        """
        Has Golem worked anything out yet?

        True as soon as the location has been read, which is before anything is
        resolved. A caller asking whether a version was found asks `version`.
        """
        return bool(
            self.locator or self.kind or self.identity or self.version or self.recipe
        )

    def settle_locator(self, locator: str, kind: str) -> "DependencyResolution":
        """
        This resolution with where the source is, and what it is.

        The identity is composed here rather than taken, therefore no caller can
        settle a locator and leave a resolution disagreeing with itself.
        """
        return replace(
            self,
            locator=locator,
            kind=kind,
            identity=SourceId.from_locator(locator),
        )

    def settle_version(self, version: ResolvedVersion) -> "DependencyResolution":
        """
        This resolution with the version the request landed on.

        Two passes fill one of these, therefore this keeps what reading the
        location already settled.
        """
        return replace(self, version=version)

    def settle_recipe(self, recipe) -> "DependencyResolution":
        """
        This resolution with the recipes that served the dependency.
        """
        return replace(
            self,
            recipe=tuple(
                RecipeLink(
                    name=str(declaration.rung),
                    cookbook=declaration.cookbook.cache_key,
                )
                for declaration in recipe.chain
            ),
        )

    def to_dict(self) -> dict:
        recorded = {}

        for name in ("locator", "kind"):
            if getattr(self, name):
                recorded[name] = getattr(self, name)

        if self.identity:
            recorded["identity"] = str(self.identity)

        if self.version:
            recorded["version"] = self.version.to_dict()

        if self.recipe:
            recorded["recipe"] = [link.to_dict() for link in self.recipe]

        return recorded

    @classmethod
    def from_dict(cls, data) -> "DependencyResolution":
        """What a recorded resolution means. Nothing recorded is nothing known."""
        if not data:
            return cls()

        identity = data.get("identity")

        return cls(
            locator=data.get("locator", ""),
            kind=data.get("kind", ""),
            identity=SourceId.parse(identity) if identity else None,
            version=ResolvedVersion.from_dict(data.get("version")),
            recipe=tuple(RecipeLink.from_dict(link) for link in data.get("recipe", ())),
        )
