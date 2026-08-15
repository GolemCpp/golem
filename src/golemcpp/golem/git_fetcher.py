'''
A source obtained from a git remote.

The mechanism here is the richest one any resource kind needs: shallow clones,
submodules, cleaning, resetting onto a reference. A kind asks for what it wants
through the FetchPolicy it hands over.

Whatever a resource holds, it is fetched whole and kept faithful to the reference
it names: the submodules come with it, and local changes are discarded before it
is refreshed.

Everything that only moves the working tree runs quiet. What reaches the remote
keeps reporting its progress, and stays recognisable to the network guard that
decides whether reaching one is allowed here at all.
'''

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
        # What the reference turns out to name
        self._resolved_reset_reference = None

    def populate(self) -> Fetched:
        '''A source obtained fresh from its remote, as much of it as asked for.'''
        print("Cloning repository {} into {}".format(self.source.locator, self.path))
        os.makedirs(self.path, exist_ok=True)

        if self.policy.fetch_mode == FetchMode.SHALLOW:
            # Not a clone at all: fetching one commit by name is the only way to
            # ask for that commit and nothing around it.
            self.run(['init'], quiet=True)
            self.run(['remote', 'add', 'origin', str(self.source.locator)], quiet=True)
            self.fetch_reference()
        else:
            self.run(['clone'] + self.mode_args() + ['--', str(self.source.locator), '.'])

        self.require_reference()
        self.reset()

        if self.has_submodules():
            self.update_submodules()

        # Obtained just now, exactly the way it was asked for.
        return self.fetched(self.policy.fetch_mode)

    def refresh(self) -> Fetched:
        '''
        An already-cloned source brought back to what it should be.

        Cleaning comes first by resetting to only leave behind what the
        previous reference put there.

        A refresh may move a root to a different commit, when following a
        branch for example.
        '''
        if self.is_up_to_date():
            # The mode has to be pulled from the state of the root. It can be different
            # from the mode asked, because a golem resolve is needed to migrate the root.
            return self.fetched(self.detected_mode())

        self.run(['clean', '-ffxd'], quiet=True)
        if self.has_submodules():
            self.run(['submodule', 'foreach', '--recursive', 'git', 'clean', '-ffxd'], quiet=True)

        if self.policy.fetch_remote:
            self.fetch_for_refresh()

        self.require_reference()
        self.reset()

        # Asked again: the reference just landed, and what it declares is not what
        # the previous one did.
        if self.has_submodules():
            self.run(['submodule', 'foreach', '--recursive', 'git', 'reset', '--hard'], quiet=True)

            # After the reset, so .gitmodules is the one the reference names, and
            # before the update, which otherwise keeps fetching from the URL recorded
            # at clone time however the resource respelled it since.
            self.run(['submodule', 'sync', '--recursive'], quiet=True)

            self.update_submodules(no_fetch=not self.policy.fetch_remote)

        self.collect_garbage()

        # The mode has to be pulled from the state of the root. It can be different
        # from the mode asked, because a golem resolve is needed to migrate the root.
        return self.fetched(self.detected_mode())

    # -- the steps a fetch is made of --------------------------------------

    def reset(self):
        '''Onto the reference, or onto the current HEAD when there is none.'''
        reference = self.resolved_reset_reference()
        self.run(['reset', '--hard'] + ([reference] if reference else []), quiet=True)

    def resolved_reset_reference(self):
        '''
        Returns a non-ambiguous reference for `git reset` to function.

        Handing the bare reference to git instead would answer nearly the same
        way, and cannot be relied on to. Because cache clone always carries a
        local branch, etc.
        '''
        if self._resolved_reset_reference is None:
            self._resolved_reset_reference = self._resolve_reference()
        return self._resolved_reset_reference

    def _resolve_reference(self):
        '''
        Disambiguate a reference.

        How should the reference be interpreted to remove any ambiguity?

        Precedence:
        1. Tag
        2. Branch
        3. The reference as given (e.g. a commit hash).
        '''
        reference = self.policy.reference
        if not reference:
            return ''
        if self.holds_reference('refs/tags/' + reference):
            return 'refs/tags/' + reference
        if self.holds_reference('refs/remotes/origin/' + reference):
            return 'origin/' + reference
        return reference

    def update_submodules(self, no_fetch=False):
        '''
        The submodules brought to what the revision in place records, obtained the
        way the resource itself was.

        `no_fetch` tells git to work from the objects this repository already holds
        and to fail rather than go looking. Which is what a resource being refreshed
        without consulting its remote needs, and what keeps such a refresh allowed
        outside a resolve.
        '''
        # --init is not optional here: --filter is only read beside it.
        args = ['submodule', 'update', '--init', '--recursive'] + self.mode_args()
        if self.policy.fetch_jobs > 1:
            args += ['--jobs', str(self.policy.fetch_jobs)]
        if no_fetch:
            args.append('--no-fetch')
        self.run(args)

    def fetch_for_refresh(self):
        '''
        Fetches the remote, according to what the fetch mode asks for.

        Shallow asks for one commit at a depth of one. The other modes ask for
        everything and prune branches and tags.
        '''
        if self.policy.fetch_mode == FetchMode.SHALLOW:
            self.fetch_reference()
            return

        self.run(['fetch', '--prune', '--prune-tags', '--tags', 'origin'])
        # Every ref may have moved, so what the reference names has to be asked
        # again rather than remembered from before.
        self._resolved_reset_reference = None

    def fetch_reference(self):
        '''
        Fetches the reference by name on the remote.

        When asking for a reference without refspec, git doesn't write any ref, so
        FETCH_HEAD comes to the rescue.
        '''
        self.run(['fetch'] + self.mode_args() + ['origin'] + (
            [self.policy.reference] if self.policy.reference else []))

        self._resolved_reset_reference = 'FETCH_HEAD'

    def mode_args(self):
        '''
        What obtaining this source the way the policy asks for takes.

        A shallow resource takes shallow submodules: at a depth of one, a submodule
        whose recorded commit is not a tip the remote advertises cannot be fetched
        at all, which is the bargain shallow is.

        A server that will not filter says so and hands over everything instead, so
        asking costs a warning at worst.
        '''
        if self.policy.fetch_mode == FetchMode.SHALLOW:
            return ['--depth=1']
        if self.policy.fetch_mode == FetchMode.BLOBLESS:
            return ['--filter=' + fetch_policy.BLOBLESS_FILTER]
        return []

    def fetched(self, mode) -> Fetched:
        '''What this fetch left behind, for the manifest to keep.'''
        return Fetched(head=self.read_head(), mode=mode)

    def require_reference(self):
        '''
        The reference has to name something the repository holds before anything
        resets to it.

        Since no fetch is performed, the checks are local based on what was
        previously fetched for the repository.
        
        It means that referring to a commit that can't be found locally, because
        it can't be reached by any branch or any tag previously fetched, is
        considered a missing commit.
        '''
        if not self.policy.reference or self.holds_reference(self.resolved_reset_reference()):
            return

        raise RuntimeError(
            'Cannot find "{}" in "{}": {} advertises no branch or tag that reaches it.'
            .format(self.policy.reference, self.path, self.source.locator))

    # -- changing what a root already holds --------------------------------

    def migrate(self, recorded) -> Fetched | None:
        '''
        A root fetched one way brought to another, in place where that costs less
        than obtaining it again: git got upgraded and blobless became available, a
        dependency was switched to shallow, a cache was asked to become portable.

        None means it cannot be converted and has to be re-cloned, which is
        always correct and never wrong, only slower.
        '''
        target = self.policy.fetch_mode
        # A root cloned before golem recorded any of this still has to be
        # recognisable, or upgrading would re-clone every cache there is.
        current = recorded.mode or self.detected_mode()

        if current != target:
            # Truncating a history in place is not worth the subtlety, and shallow
            # is asked for by someone who wants the cheap thing anyway.
            if target == FetchMode.SHALLOW:
                return None

            print("Migrating {} from {} to {}".format(
                self.path, current.value, target.value))

            if current == FetchMode.SHALLOW:
                # The history it never had. Everything else it holds stays.
                self.run(['fetch', '--unshallow', 'origin'])

            if target == FetchMode.BLOBLESS:
                # Nothing to transfer: the objects are already here, and this only
                # says that later fetches may leave file content behind.
                self.run(['config', 'remote.origin.promisor', 'true'], quiet=True)
                self.run(['config', 'remote.origin.partialclonefilter',
                          fetch_policy.BLOBLESS_FILTER],
                         quiet=True)
            else:
                # Back to a self-contained root: drop the filter, then ask for
                # everything it was allowed to leave out.
                self.unset('remote.origin.partialclonefilter')
                self.unset('remote.origin.promisor')
                self.run(['fetch', '--refetch', 'origin'])

        # A migration changes how much of a history a root holds, never which
        # commit it is on. Said even when nothing was converted, so a root that
        # recorded no mode stops being detected on every resolve.
        return replace(recorded, mode=target)

    def collect_garbage(self):
        '''
        Git's own housekeeping, which it decides is due or not. A cache root is
        fetched into for as long as it is kept, and nothing else would ever pack
        what those fetches leave loose.

        Never worth failing a refresh over: what it does is what a later command
        would have done anyway.
        '''
        helpers.try_git(['gc', '--auto'], cwd=self.path,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def unset(self, key):
        '''A configuration key removed if it is there. Absent is the same as gone.'''
        helpers.try_git(['config', '--unset', key], cwd=self.path,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # -- what the repository says about itself -----------------------------

    def is_up_to_date(self) -> bool:
        '''
        Whether the whole refresh would leave the root exactly as it found it.

        Only a resource that consults no remote can be known to be up to date;
        anything else may have moved since it was last looked at.

        `status --porcelain` answers for the submodules too: untracked content in
        one, a modified file, a moved HEAD all show up as a change here.
        '''
        if self.policy.fetch_remote:
            return False
        if self.policy.reference and not self.is_at(self.resolved_reset_reference()):
            return False
        return not self.is_dirty()

    def is_at(self, reference) -> bool:
        '''Whether HEAD is already the commit a reference names.'''
        try:
            landed, wanted = helpers.read_git(
                ['rev-parse', 'HEAD', '{}^{{commit}}'.format(reference)],
                cwd=self.path, stderr=subprocess.DEVNULL).split()
        except Exception:
            return False
        return landed == wanted

    def is_dirty(self) -> bool:
        '''
        Whether anything in the root differs from what its revision records.
        Unreadable counts as dirty: what cannot be checked is not known to be
        clean.
        '''
        try:
            return bool(helpers.read_git(
                ['status', '--porcelain'], cwd=self.path,
                stderr=subprocess.DEVNULL).strip())
        except Exception:
            return True

    def detected_mode(self) -> FetchMode:
        '''
        What a root looks like it was fetched as, for one whose manifest does not
        say: a cache populated before golem knew about modes, or by a golem that
        knows ones this one does not.
        '''
        if self.reads_true(['rev-parse', '--is-shallow-repository']):
            return FetchMode.SHALLOW
        if self.reads_true(['config', '--get', 'remote.origin.promisor']):
            return FetchMode.BLOBLESS
        return FetchMode.FULL

    def reads_true(self, args) -> bool:
        '''What git says, for the questions it answers with a word.'''
        try:
            return helpers.read_git(
                args, cwd=self.path, stderr=subprocess.DEVNULL).strip() == 'true'
        except Exception:
            return False

    def has_submodules(self) -> bool:
        '''
        Whether the revision in place declares any submodule.
        '''
        return os.path.isfile(os.path.join(self.path, '.gitmodules'))

    def holds_reference(self, reference) -> bool:
        '''Whether the repository already holds the commit a reference names.'''
        return helpers.try_git(
            ['rev-parse', '--verify', '--quiet', '{}^{{commit}}'.format(reference)],
            cwd=self.path, stdout=subprocess.DEVNULL)

    def read_head(self) -> str:
        '''
        The commit the working tree is on, for the manifest to record. Best-effort:
        what the root holds is worth knowing, never worth failing a fetch over.
        '''
        try:
            return helpers.read_git(
                ['rev-parse', 'HEAD'], cwd=self.path, stderr=subprocess.DEVNULL).strip()
        except Exception:
            return ''

    def run(self, args, quiet=False):
        '''Every git command this fetcher runs, in the directory it works in.'''
        helpers.run_git(args, cwd=self.path, quiet=quiet)
