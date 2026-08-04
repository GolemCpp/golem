'''
A source obtained by copying it, since there is no remote to track.

Nothing distinguishes a fresh copy from a later one: both replace whatever is
there with what the source holds now.
'''

import os
import shutil

from golemcpp.golem.fetched import Fetched
from golemcpp.golem.fetcher import Fetcher


# Records where a copied directory came from, so a resource obtained without git
# can still name its origin (see Context.load_git_remote_origin_url).
ORIGIN_FILENAME = '.golem-origin'


class DirectoryFetcher(Fetcher):

    def populate(self) -> Fetched:
        return self.copy()

    def refresh(self) -> Fetched:
        return self.copy()

    def copy(self) -> Fetched:
        print("Copying directory {} into {}".format(self.source.location, self.path))
        local_path = self.local_path

        if os.path.isdir(self.path):
            shutil.rmtree(self.path)
        shutil.copytree(local_path, self.path, dirs_exist_ok=True, symlinks=True)
        with open(os.path.join(self.path, ORIGIN_FILENAME), 'w') as fileout:
            fileout.write(self.source.location)

        # A copied directory has no commit to name.
        return Fetched()
