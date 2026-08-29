"""
A source obtained from a git remote.

This is the one fetcher that clones, fetches shallow, updates submodules, cleans
a working tree and resets onto a revision. A kind asks for what it wants through
the FetchPolicy it hands over.

A resource is obtained whole and left on the revision the policy names: the
submodules come with it, and local changes are discarded before a refresh.

The revision is a commit. Resolution settled which one before the policy was
built, therefore nothing here interprets a name.

Everything that only moves the working tree runs quiet. What reaches the remote
keeps reporting its progress, and keeps the spelling `helpers.validate_git_command`
reads to decide whether reaching one is allowed.
"""

import os
import subprocess
from dataclasses import replace

from golemcpp.golem import fetch_policy
from golemcpp.golem import helpers
from golemcpp.golem.fetch_policy import FetchMode
from golemcpp.golem.fetched import Fetched
from golemcpp.golem.fetcher import Fetcher


class GitFetcher(Fetcher):

    def __init__(self, path, source, policy):
        super().__init__(path, source, policy)
        # What the last fetch left to land on, when it named no ref for it.
        self._fetched_head = ""

    def populate(self) -> Fetched:
        """Obtain a source fresh from its remote, as much of it as asked for."""
        print("Cloning repository {} into {}".format(self.source.locator, self.path))
        os.makedirs(self.path, exist_ok=True)

        if self.policy.fetch_mode == FetchMode.SHALLOW:
            # Not a clone at all: fetching one commit by name is the only way to
            # ask for that commit and nothing around it.
            self.run(["init"], quiet=True)
            self.run(["remote", "add", "origin", str(self.source.locator)], quiet=True)
            self.fetch_revision()
        else:
            self.run(
                ["clone"] + self.mode_args() + ["--", str(self.source.locator), "."]
            )

        self.require_revision()
        self.reset()

        if self.has_submodules():
            self.update_submodules()

        # Obtained just now, exactly the way it was asked for.
        return self.fetched(self.policy.fetch_mode)

    def refresh(self) -> Fetched:
        """
        Bring a source that is already cloned back to what it should be.

        Clean first, so what the previous revision left behind does not survive
        into what this one holds.

        A refresh may land the root on a different commit, which is what a
        resource following a branch is for.
        """
        if self.is_up_to_date():
            return self.fetched(self.detected_mode())

        self.run(["clean", "-ffxd"], quiet=True)
        if self.has_submodules():
            self.run(
                ["submodule", "foreach", "--recursive", "git", "clean", "-ffxd"],
                quiet=True,
            )

        if self.policy.fetch_remote:
            self.fetch_for_refresh()

        self.require_revision()
        self.reset()

        # Asked again rather than remembered: the revision that just landed may
        # declare submodules the previous one did not.
        if self.has_submodules():
            self.run(
                ["submodule", "foreach", "--recursive", "git", "reset", "--hard"],
                quiet=True,
            )

            # After the reset, so .gitmodules is the one the revision names, and
            # before the update, which otherwise keeps fetching from the URL recorded
            # at clone time however the resource respelled it since.
            self.run(["submodule", "sync", "--recursive"], quiet=True)

            self.update_submodules(no_fetch=not self.policy.fetch_remote)

        self.collect_garbage()

        return self.fetched(self.detected_mode())

    # -- the steps a fetch is made of --------------------------------------

    def reset(self):
        """Land the working tree on the revision, or on the current HEAD when
        there is none."""
        revision = self.reset_revision()
        self.run(["reset", "--hard"] + ([revision] if revision else []), quiet=True)

    def reset_revision(self):
        """
        Give `git reset` what to land on.

        The policy names a commit, which needs no interpreting. A shallow fetch
        is the exception: it asks the remote for one object by name and git
        writes no ref for it, so FETCH_HEAD is the only thing naming what landed.
        """
        return self._fetched_head or self.policy.revision

    def update_submodules(self, no_fetch=False):
        """
        Bring the submodules to what the revision in place records, obtained the
        way the resource itself was.

        `no_fetch` tells git to work from the objects this repository already holds
        and to fail rather than go looking. Which is what a resource being refreshed
        without consulting its remote needs, and what keeps such a refresh allowed
        outside a resolve.
        """
        # --init is not optional here: --filter is only read beside it.
        args = ["submodule", "update", "--init", "--recursive"] + self.mode_args()
        if self.policy.fetch_jobs > 1:
            args += ["--jobs", str(self.policy.fetch_jobs)]
        if no_fetch:
            args.append("--no-fetch")
        self.run(args)

    def fetch_for_refresh(self):
        """
        Fetch the remote, as much of it as the fetch mode asks for.

        Shallow asks for one commit at a depth of one. The other modes ask for
        everything and prune branches and tags.
        """
        if self.policy.fetch_mode == FetchMode.SHALLOW:
            self.fetch_revision()
            return

        self.run(["fetch", "--prune", "--prune-tags", "--tags", "origin"])

    def fetch_revision(self):
        """
        Fetch one object from the remote, by name.

        Asked for a revision and no refspec, git writes no ref, therefore
        FETCH_HEAD is the only thing naming what landed.
        """
        self.run(
            ["fetch"]
            + self.mode_args()
            + ["origin"]
            + ([self.policy.revision] if self.policy.revision else [])
        )

        self._fetched_head = "FETCH_HEAD"

    def mode_args(self):
        """
        Make the arguments that obtain this source the way the policy asks for.

        A shallow resource takes shallow submodules: at a depth of one, a submodule
        whose recorded commit is not a tip the remote advertises cannot be fetched
        at all. That is what shallow costs.

        A server that will not filter says so and hands over everything instead, so
        asking costs a warning at worst.
        """
        if self.policy.fetch_mode == FetchMode.SHALLOW:
            return ["--depth=1"]
        if self.policy.fetch_mode == FetchMode.BLOBLESS:
            return ["--filter=" + fetch_policy.BLOBLESS_FILTER]
        return []

    def fetched(self, mode) -> Fetched:
        """Make the record of what this fetch left behind, for the manifest."""
        return Fetched(head=self.read_head(), mode=mode)

    def require_revision(self):
        """
        Refuse a revision the repository does not hold, before anything resets
        onto it.

        The check is local: whatever was going to be fetched has been by now, so
        a commit no branch and no tag reaches is one this root will never have.

        `git reset` would fail on its own. It names neither the repository nor
        what is missing, which is what this is for.
        """
        if not self.policy.revision or self.holds_revision(self.reset_revision()):
            return

        raise RuntimeError(
            'Cannot find "{}" in "{}": {} advertises no branch or tag that reaches it.'.format(
                self.policy.revision, self.path, self.source.locator
            )
        )

    # -- changing what a root already holds --------------------------------

    def migrate(self, recorded) -> Fetched | None:
        """
        Convert a root fetched one way into one fetched another, in place where
        that costs less than obtaining it again: git got upgraded and blobless
        became available, a dependency was switched to shallow, a cache was asked
        to become portable.

        Return None when it cannot be converted, so the caller obtains it again.
        That is correct whatever the root held, only slower.
        """
        target = self.policy.fetch_mode
        # A root cloned before golem recorded any of this still has to be
        # recognisable, or upgrading would re-clone every cache there is.
        current = recorded.mode or self.detected_mode()

        if current != target:
            # Truncating a history in place is not worth the subtlety, and shallow
            # is asked for by someone who wants the cheap thing anyway.
            if target == FetchMode.SHALLOW:
                return None

            print(
                "Migrating {} from {} to {}".format(
                    self.path, current.value, target.value
                )
            )

            if current == FetchMode.SHALLOW:
                # The history it never had. Everything else it holds stays.
                self.run(["fetch", "--unshallow", "origin"])

            if target == FetchMode.BLOBLESS:
                # Nothing to transfer: the objects are already here, and this only
                # says that later fetches may leave file content behind.
                self.run(["config", "remote.origin.promisor", "true"], quiet=True)
                self.run(
                    [
                        "config",
                        "remote.origin.partialclonefilter",
                        fetch_policy.BLOBLESS_FILTER,
                    ],
                    quiet=True,
                )
            else:
                # Back to a self-contained root: drop the filter, then ask for
                # everything it was allowed to leave out.
                self.unset("remote.origin.partialclonefilter")
                self.unset("remote.origin.promisor")
                self.run(["fetch", "--refetch", "origin"])

        # A migration changes how much of a history a root holds, never which
        # commit it is on. Said even when nothing was converted, so a root that
        # recorded no mode stops being detected on every resolve.
        return replace(recorded, mode=target)

    def collect_garbage(self):
        """
        Let git do its own housekeeping, if it decides any is due. A cache root
        is fetched into for as long as it is kept, and nothing else would ever
        pack what those fetches leave loose.

        Never worth failing a refresh over: what it does is what a later command
        would have done anyway.
        """
        helpers.try_git(
            ["gc", "--auto"],
            cwd=self.path,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def unset(self, key):
        """Remove a configuration key, succeeding when it was not there."""
        helpers.try_git(
            ["config", "--unset", key],
            cwd=self.path,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    # -- what the repository says about itself -----------------------------

    def is_up_to_date(self) -> bool:
        """
        Would the whole refresh leave the root exactly as it found it?

        Only a resource that consults no remote can be known to be up to date;
        anything else may have moved since it was last looked at.

        `status --porcelain` answers for the submodules too: untracked content in
        one, a modified file, a moved HEAD all show up as a change here.
        """
        if self.policy.fetch_remote:
            return False
        if self.policy.revision and not self.is_at(self.reset_revision()):
            return False
        return not self.is_dirty()

    def is_at(self, revision) -> bool:
        """Is HEAD already the commit this revision names?"""
        try:
            landed, wanted = helpers.read_git(
                ["rev-parse", "HEAD", "{}^{{commit}}".format(revision)],
                cwd=self.path,
                stderr=subprocess.DEVNULL,
            ).split()
        except Exception:
            return False
        return landed == wanted

    def is_dirty(self) -> bool:
        """
        Does anything in the root differ from what its revision records?

        Unreadable counts as dirty: what cannot be checked is not known to be
        clean.
        """
        try:
            return bool(
                helpers.read_git(
                    ["status", "--porcelain"], cwd=self.path, stderr=subprocess.DEVNULL
                ).strip()
            )
        except Exception:
            return True

    def detected_mode(self) -> FetchMode:
        """
        Read what a root looks like it was fetched as.

        A manifest says so, until one does not: a cache populated before golem
        knew about modes, or by a golem that knows ones this one does not. The
        mode a refresh reports comes from here for that reason, and may differ
        from the mode asked for, since migrating a root is a resolve step.
        """
        if self.reads_true(["rev-parse", "--is-shallow-repository"]):
            return FetchMode.SHALLOW
        if self.reads_true(["config", "--get", "remote.origin.promisor"]):
            return FetchMode.BLOBLESS
        return FetchMode.FULL

    def reads_true(self, args) -> bool:
        """Read git's answer to a question it answers with one word."""
        try:
            return (
                helpers.read_git(args, cwd=self.path, stderr=subprocess.DEVNULL).strip()
                == "true"
            )
        except Exception:
            return False

    def has_submodules(self) -> bool:
        """
        Does the revision in place declare any submodule?
        """
        return os.path.isfile(os.path.join(self.path, ".gitmodules"))

    def holds_revision(self, revision) -> bool:
        """Does the repository already hold the commit this revision names?"""
        return helpers.try_git(
            ["rev-parse", "--verify", "--quiet", "{}^{{commit}}".format(revision)],
            cwd=self.path,
            stdout=subprocess.DEVNULL,
        )

    def read_head(self) -> str:
        """
        Read the commit the working tree is on, for the manifest to record.

        An unreadable one answers empty: what a root holds is worth recording,
        never worth failing a fetch over.
        """
        try:
            return helpers.read_git(
                ["rev-parse", "HEAD"], cwd=self.path, stderr=subprocess.DEVNULL
            ).strip()
        except Exception:
            return ""

    def run(self, args, quiet=False):
        """Run a git command in the directory this fetcher works in."""
        helpers.run_git(args, cwd=self.path, quiet=quiet)
