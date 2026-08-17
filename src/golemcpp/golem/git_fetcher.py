'''
A source obtained from a git remote.

The mechanism here is the richest one any resource kind needs: shallow clones,
submodules, cleaning, checkout-then-reset. A kind asks for what it wants through
the FetchPolicy it hands over.

Whatever a resource holds, it is fetched whole and kept faithful to the reference
it names: the submodules come with it, and local changes are discarded before it
is refreshed.

Everything that only moves the working tree runs quiet. What reaches the remote
keeps reporting its progress, and stays recognisable to the network guard that
decides whether reaching one is allowed here at all.
'''

import os
import subprocess

from golemcpp.golem import helpers
from golemcpp.golem.fetched import Fetched
from golemcpp.golem.fetcher import Fetcher


class GitFetcher(Fetcher):

    def populate(self) -> Fetched:
        '''A source obtained fresh from its remote, as much of it as asked for.'''
        print("Cloning repository {} into {}".format(self.source.location, self.path))
        os.makedirs(self.path, exist_ok=True)

        if self.policy.shallow:
            self.run(['init'], quiet=True)
            self.run(['remote', 'add', 'origin', self.source.location], quiet=True)
            self.run(['fetch', '--depth=1', 'origin', self.policy.reference])
            self.run(['reset', '--hard', 'FETCH_HEAD'], quiet=True)
        else:
            self.run(['clone', '--', self.source.location, '.'])
            if self.policy.checkout:
                self.run(['checkout', self.policy.checkout], quiet=True)
            self.ensure_reference()
            self.reset()

        if self.has_submodules():
            # Only a shallow resource takes shallow submodules: at a depth of one, a
            # submodule whose recorded commit is not a tip the remote advertises
            # cannot be fetched at all.
            self.update_submodules(depth=self.policy.shallow)

        return Fetched(head=self.read_head())

    def refresh(self) -> Fetched:
        '''
        An already-cloned source brought back to what it should be.

        Cleaning comes first: a reset alone leaves behind what the previous
        reference put there, and a cached resource is only worth reading when it
        holds the reference it names and nothing else.
        '''
        self.run(['clean', '-ffxd'], quiet=True)
        if self.has_submodules():
            self.run(['submodule', 'foreach', '--recursive', 'git', 'clean', '-ffxd'], quiet=True)

        if self.policy.fetch_remote:
            # Pruning both ways: a branch deleted upstream stops being tracked, and a
            # tag that moved is honoured rather than kept at what it used to point to.
            self.run(['fetch', '--prune', '--prune-tags', '--tags', 'origin'])

        self.ensure_reference()
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

        return Fetched(head=self.read_head())

    # -- the steps a fetch is made of --------------------------------------

    def reset(self):
        '''Onto the reference, or onto the current HEAD when there is none.'''
        self.run(
            ['reset', '--hard'] + ([self.policy.reference] if self.policy.reference else []),
            quiet=True)

    def update_submodules(self, depth=False, no_fetch=False):
        '''
        The submodules brought to what the revision in place records.

        `no_fetch` tells git to work from the objects this repository already holds
        and to fail rather than go looking. Which is what a resource being refreshed
        without consulting its remote needs, and what keeps such a refresh allowed
        outside a resolve.
        '''
        args = ['submodule', 'update', '--init', '--recursive']
        if depth:
            args.append('--depth=1')
        if no_fetch:
            args.append('--no-fetch')
        self.run(args)

    def ensure_reference(self):
        '''
        The reference has to name something the repository holds before anything
        resets to it.
        '''
        if not self.policy.reference or self.holds_reference(self.policy.reference):
            return

        missing = RuntimeError(
            'Cannot find "{}" in "{}", and {} does not offer it. '
            'Run golem resolve first.'.format(
                self.policy.reference, self.path, self.source.location))

        try:
            self.run(['fetch', 'origin', self.policy.reference])
        except RuntimeError as error:
            # A reference the remote no longer has: a branch pruned away, a tag
            # deleted, a commit never pushed.
            #
            # What git says about a refspec it could not find says nothing about
            # which resource asked for it.
            raise missing from error

        if not self.holds_reference(self.policy.reference):
            raise missing

    # -- what the repository says about itself -----------------------------

    def has_submodules(self) -> bool:
        '''
        Whether the revision in place declares any submodule.
        '''
        return os.path.isfile(os.path.join(self.path, '.gitmodules'))

    def holds_reference(self, reference) -> bool:
        '''Whether the repository already holds the commit a reference names.'''
        return helpers.call_git(
            ['rev-parse', '--verify', '--quiet', '{}^{{commit}}'.format(reference)],
            cwd=self.path, stdout=subprocess.DEVNULL) == 0

    def read_head(self) -> str:
        '''
        The commit the working tree is on, for the manifest to record. Best-effort:
        what the root holds is worth knowing, never worth failing a fetch over.
        '''
        try:
            return helpers.check_git_output(
                ['rev-parse', 'HEAD'], cwd=self.path, stderr=subprocess.DEVNULL).strip()
        except Exception:
            return ''

    def run(self, args, quiet=False):
        '''Every git command this fetcher runs, in the directory it works in.'''
        helpers.run_git(args, cwd=self.path, quiet=quiet)
