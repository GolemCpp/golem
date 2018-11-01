import re
import subprocess
import helpers


class Dependency:
    def __init__(self, name=None, repository=None, version=None):
        self.name = '' if name is None else name
        self.repository = '' if repository is None else repository
        self.version = '' if version is None else version
        self.resolved_version = ''

    def __str__(self):
        return helpers.print_obj(self)

    def resolve(self):
        if self.resolved_version:
            return self.resolved_version

        dep_version = ''
        if str(self.version) == 'latest':
            tags = subprocess.check_output(
                ['git', 'ls-remote', '--tags', self.repository])
            tags = tags.split('\n')
            badtag = ['^{}']
            tmp = ''
            for line in tags:
                if '^{}' not in line:
                    tmp += line + '\n'
            tags = tmp
            versions_list = re.findall('refs\/tags\/v(\d*(?:\.\d*)*)', tags)
            versions_list = set(versions_list)
            versions_list = list(versions_list)
            versions_list.sort(key=lambda s: map(int, s.split('.')))
            last = versions_list[-1:]
            if not last:
                print("ERROR: no latest version")
                return
            last = 'v' + last[0]
            hash = subprocess.check_output(
                ['git', 'ls-remote', '--tags', self.repository, last])
            if not hash:
                print("ERROR: can't find " + last)
                return
            #dep_version = hash[:8]
            dep_version = last
        else:
            hash = subprocess.check_output(
                ['git', 'ls-remote', '--heads', self.repository, str(self.version)])
            if hash:
                dep_version = hash[:8]
            else:
                dep_version = str(self.version)

        self.resolved_version = dep_version
        return self.resolved_version
