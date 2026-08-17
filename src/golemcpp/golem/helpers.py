import locale
import os
import re
import sys
import time
import types
import shutil
import subprocess
from pathlib import Path

from golemcpp.golem import network


# Options carried by every git command golem runs. The advice is about landing on
# a detached HEAD, which every resource golem checks out does, on purpose.
GIT_OPTIONS = ['-c', 'advice.detachedHead=false']

# How long to wait before running a failed network command again, once per entry.
# An early EOF or a refused connection is routine on a busy network and says
# nothing about the command, where a local git command failing means what it says.
GIT_RETRY_DELAYS = (2, 5)

# How many times to ask Windows again to remove a directory, a tenth of a second
# apart. A file an indexer or a scanner is holding is let go of in moments; a
# tree still standing after that is not going away on its own.
REMOVE_TREE_ATTEMPTS = 50


def print_obj(obj, depth=5, l=""):
    # fall back to repr
    if depth < 0:
        return repr(obj)
    # expand/recurse dict
    if isinstance(obj, dict):
        name = ""
        objdict = obj
    else:
        # if basic type, or list thereof, just print
        def canprint(o):
            return isinstance(
                o, (int, float, str, bool, type(None), types.LambdaType))

        try:
            if canprint(obj) or sum(not canprint(o) for o in obj) == 0:
                return repr(obj)
        except TypeError as e:
            pass
        # try to iterate as if obj were a list
        try:
            return "[\n" + "\n".join(
                l + print_obj(k, depth=depth - 1, l=l + "  ") + ","
                for k in obj) + "\n" + l + "]"
        except TypeError as e:
            # else, expand/recurse object attribs
            name = (hasattr(obj, '__class__') and obj.__class__.__name__
                    or type(obj).__name__)
            objdict = {}
            for a in dir(obj):
                if a[:2] != "__" and (not hasattr(obj, a) or not hasattr(
                        getattr(obj, a), '__call__')):
                    try:
                        objdict[a] = getattr(obj, a)
                    except Exception as e:
                        objdict[a] = str(e)
    return name + " {\n" + "\n".join(
        l + repr(k) + ": " + print_obj(v, depth=depth - 1, l=l + "  ") + ","
        for k, v in objdict.items()) + "\n" + l + "}"


def remove_tree(path):
    if not os.path.exists(path):
        return

    if os.path.isfile(path):
        os.remove(path)
    elif os.path.islink(path):
        os.unlink(path)
    elif sys.platform.startswith('win32'):
        # rmdir removes a whole tree in one pass where shutil.rmtree unlinks every
        # file from Python: on a build directory holding many small ones that is
        # the difference between moments and minutes.
        #
        # Quoted here rather than through subprocess.list2cmdline, which spells an
        # argument the way a program reads it back: cmd re-tokenizes its own
        # command line and breaks on '=' as much as on a space, and a cache root
        # is named after the reference it holds (r@host+main=0d6e4079).
        command = 'rmdir /s /q "{}"'.format(path)
        for _ in range(REMOVE_TREE_ATTEMPTS):
            # Through the shell because rmdir is a cmd built-in: there is no
            # executable to run. What an attempt has to say is worth reading only
            # once they have all failed, and then it is said once, with the path.
            attempt = subprocess.run(
                command, shell=True,
                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            if not os.path.exists(path):
                return
            time.sleep(0.1)
        raise RuntimeError('Cannot remove directory {}: {}'.format(
            path, decode_output(attempt.stderr).strip()))
    else:
        shutil.rmtree(path)


def get_environ(env_name):
    if env_name in os.environ and os.environ[env_name] and len(str(os.environ[env_name])) > 0:
        return str(os.environ[env_name])
    return None


def decode_output(output):
    if isinstance(output, str):
        return output

    encoding = getattr(sys.stdout, 'encoding', None) or locale.getpreferredencoding(False) or 'utf-8'

    try:
        return output.decode(encoding)
    except UnicodeDecodeError:
        return output.decode('utf-8', errors='replace')


def make_directory(base, path=None):
    directory = base
    if path is not None:
        directory = os.path.join(directory, path)
    if not os.path.exists(directory):
        os.makedirs(directory)
    return directory


def get_golemcpp_golem_dir():
    return os.path.abspath(os.path.dirname(os.path.realpath(__file__)))


def get_golemcpp_data_dir():
    return os.path.join(get_golemcpp_dir(), 'data')


def get_golemcpp_dir():
    return Path(get_golemcpp_golem_dir()).parent


def make_golem_command(command_name):
    golem_path = get_golemcpp_golem_dir()
    return [sys.executable, golem_path, command_name]


def copy_tree(source_path, destination_path):
    if not os.path.isdir(destination_path):
        raise ValueError(str(destination_path) + " is not a directory")

    destination_path = make_directory(destination_path)

    for dirName, subdirList, fileList in os.walk(source_path):
        for fname in fileList:
            copy_file(os.path.join(dirName, fname), destination_path)
        for dname in subdirList:
            dname_destination = make_directory(destination_path, dname)
            copy_tree(os.path.join(dirName, dname), dname_destination)
        break


def directory_basename(path):
    clean_path = path.rstrip('\\') if sys.platform.startswith(
        'win32') else path.rstrip('/')
    return os.path.basename(clean_path)


def copy_file(source_path, destination_path):
    if os.path.isdir(destination_path):
        destination_directory = destination_path
        destination_path = os.path.join(destination_path,
                                        directory_basename(source_path))
    else:
        destination_directory = os.path.dirname(destination_path)

    if os.path.islink(source_path):
        link_path = os.readlink(source_path)
        if os.path.isabs(link_path):
            link_path_absolute = link_path
            link_path_relative = os.path.basename(link_path_absolute)
        else:
            link_path_relative = link_path
            link_path_absolute = os.path.join(os.path.dirname(source_path),
                                              link_path_relative)

        copy_file(link_path_absolute, destination_directory)
        if os.path.exists(destination_path):
            os.remove(destination_path)
        os.symlink(link_path_relative, destination_path)
    else:
        shutil.copy(source_path, destination_path)


def copy_file_if_recent(source_path, destination_directory, callback=None):
    filename = os.path.basename(source_path)
    destination_path = os.path.join(destination_directory, filename)
    if os.path.exists(destination_path) and (
            os.path.getmtime(source_path) <=
            os.path.getmtime(destination_path)):
        return False

    if not os.path.exists(destination_directory):
        os.makedirs(destination_directory)

    if callback:
        callback(filename)

    copy_file(source_path=source_path, destination_path=destination_path)
    return True

def is_git_repository(path):
    '''Whether a repository is there to work in: one with a HEAD to read.'''
    git_index = os.path.join(path, '.git', 'HEAD')
    return os.path.exists(git_index)

def has_git_directory(path):
    '''
    Whether git has anything here at all. Not the opposite of is_git_repository:
    that one asks whether a repository can be worked in, this one whether the
    ground is free for a clone.
    '''
    return os.path.exists(os.path.join(path, '.git'))

def does_git_command_need_no_repository(params):
    if params[0] in ['init', 'clone']:
        return True
    return False

def does_git_command_need_nothing(params):
    if params[0] in ['ls-remote']:
        return True
    return False

_git_version = None


def git_version():
    '''
    The client git's version, as a tuple to compare against. Asked once per
    process: it cannot change under us, and every caller asking is a subprocess
    spawned to learn the same thing.

    An unreadable version reads as (0, 0), so whatever it gates falls back to
    whatever the oldest git would get.
    '''
    global _git_version
    if _git_version is not None:
        return _git_version

    try:
        output = subprocess.check_output(['git', 'version'])
        numbers = re.search(r'(\d+)\.(\d+)(?:\.(\d+))?', decode_output(output))
        _git_version = tuple(int(part) for part in numbers.groups(default='0'))
    except Exception:
        _git_version = (0, 0, 0)

    return _git_version


def is_network_git_command(params):
    '''
    Git commands that reach the remote. `submodule update` clones a submodule
    that is not there, while `submodule foreach` only runs in the ones already
    cloned, so the two are not the same.

    `submodule update --no-fetch` is told to work from the objects already here
    and to fail rather than go looking, which is what a resource being refreshed
    without consulting its remote needs.
    '''
    command = params[0]
    if command == 'submodule':
        return params[1:2] == ['update'] and '--no-fetch' not in params
    return command in ['clone', 'fetch', 'pull', 'push', 'ls-remote']

def validate_git_command(params, cwd):
    '''
    What a git command is allowed to do here, read from the command itself. Not
    from the line it runs as: the options golem carries are its own, and one of
    them in front of the command would answer for it (see git_command_line).
    '''
    if is_network_git_command(params=params) and not network.is_allowed():
        raise RuntimeError(
            "Cannot run \"git {}\" from \"{}\": reaching a remote is a resolve step. "
            "Run golem resolve first.".format(' '.join(params), cwd))

    if does_git_command_need_no_repository(params=params):
        if has_git_directory(path=cwd):
            raise RuntimeError(
                "Already a git repository: \"git {}\" from \"{}\"".format(
                    ' '.join(params), cwd))
    elif does_git_command_need_nothing(params=params):
        pass
    else:
        # Needs a repository
        if not is_git_repository(path=cwd):
            raise RuntimeError(
                "Not a git repository: \"git {}\" from \"{}\"".format(
                    ' '.join(params), cwd))

# Whether git may stop and ask for credentials. Off until a command's settings
# say otherwise: a prompt nobody is watching reads as a hang rather than as the
# failure it is, and forgetting to ask only ever makes golem fail sooner.
_git_prompt_allowed = False


def allow_git_prompt(allowed):
    '''
    What a command's settings say about git asking for credentials, kept for every
    git invocation the process makes afterwards (see git_environment).

    Process-wide, like the network scope, because the commands that would ask are
    not all reached through a resource: resolving a version runs `ls-remote` from
    a static method that is handed a URL and nothing else.
    '''
    global _git_prompt_allowed
    _git_prompt_allowed = bool(allowed)


def is_git_prompt_allowed() -> bool:
    return _git_prompt_allowed


def git_environment():
    '''
    The environment a git command runs in.

    1. Ensuring no git command issues network calls outside those authorised to:

    A partial clone (blobless mode) completes itself as it goes: any command can
    reach the remote for an object it is missing, and no command name says so.

    Outside a resolve, GIT_NO_LAZY_FETCH makes git fail there instead of quietly
    phoning home, which is what keeps is_network_git_command's verdict true of
    what actually happens.

    2. Never stopping to ask for credentials:

    A private or mistyped URL otherwise parks a build at a prompt nobody is
    watching. An empty GIT_ASKPASS is not the same as an unset one: it stops git
    looking for another asker, leaving GIT_TERMINAL_PROMPT to refuse the terminal
    it falls back to.

    Both are git's own, and cover what git asks for itself. A repository reached
    over ssh is handed to ssh, which unlocks the key it needs on its own terms.

    Credential helpers are left alone: one that already holds the credential
    answers without asking anybody, which is the case worth serving.
    '''
    environment = dict(os.environ)

    if not network.is_allowed():
        environment['GIT_NO_LAZY_FETCH'] = '1'

    if not is_git_prompt_allowed():
        environment['GIT_TERMINAL_PROMPT'] = '0'
        environment['GIT_ASKPASS'] = ''

    return environment


def git_command_line(params):
    '''
    The line golem runs a git command as, its own options included.

    The line, not the command: what a command is allowed to do is read from
    `params` alone (see validate_git_command).
    '''
    return ['git'] + GIT_OPTIONS + params


def run_git(params, cwd, quiet=False, **kwargs):
    '''
    Runs a git command, and raises if it fails.

    `quiet` drops what the command has to say on stdout.

    What reaches a remote is run again when it fails: the network is the one part
    of this that fails for reasons that have nothing to do with what was asked.
    '''
    validate_git_command(params=params, cwd=cwd)

    if quiet:
        kwargs.setdefault('stdout', subprocess.DEVNULL)
    kwargs.setdefault('env', git_environment())

    delays = GIT_RETRY_DELAYS if is_network_git_command(params) else ()
    run_task_with_retries(args=git_command_line(params), cwd=cwd, delays=delays, **kwargs)


def read_git(params, cwd, **kwargs):
    '''
    Runs a git command and hands back what it printed. Raises if it fails, so
    what comes back is always an answer.
    '''
    validate_git_command(params=params, cwd=cwd)
    kwargs.setdefault('env', git_environment())

    return decode_output(
        subprocess.check_output(git_command_line(params), cwd=cwd, **kwargs))


def try_git(params, cwd, **kwargs) -> bool:
    '''
    Runs a git command and says whether it worked. Never raises: this is the one
    for asking a repository a question it is allowed to answer no to.
    '''
    validate_git_command(params=params, cwd=cwd)
    kwargs.setdefault('env', git_environment())

    return subprocess.call(git_command_line(params), cwd=cwd, **kwargs) == 0

def run_task_with_retries(args, cwd=None, delays=(), **kwargs):
    '''
    A command run again for as many delays as it is given, waiting each one out
    before trying once more.

    Whatever it is retried for has to be worth waiting for twice: a command that
    fails because of what it was asked only fails again, later.
    '''
    for delay in delays:
        try:
            return run_task(args=args, cwd=cwd, **kwargs)
        except RuntimeError as error:
            print("{}\nTrying again in {}s.".format(error, delay))
            time.sleep(delay)

    return run_task(args=args, cwd=cwd, **kwargs)


def run_task(args, cwd=None, debug=True, **kwargs):
    if debug:
        print("Run \"{}\" from \"{}\"".format(' '.join(args), cwd))
    process = subprocess.Popen(args,
                               cwd=cwd,
                               shell=False,
                               **kwargs)
    ret = process.wait()
    if ret != 0:
        raise RuntimeError(
            "Return code {} when running \"{}\" from \"{}\"".format(
                ret, ' '.join(args),
                os.getcwd() if cwd is None else cwd))


def RepresentsInt(s):
    try:
        int(s)
        return True
    except ValueError:
        return False


def byteify(input):
    if isinstance(input, dict):
        return {byteify(key): byteify(value) for key, value in input.items()}
    elif isinstance(input, list):
        return [byteify(element) for element in input]
    elif isinstance(input, str):
        return input.encode('utf-8')
    else:
        return input


def filter_unique(value):
    new_list = []
    for item in value:
        if item not in new_list:
            new_list.append(item)
    return new_list


def parameter_to_list(input):
    if input is None:
        return []
    elif not isinstance(input, list):
        return [input]
    else:
        return input

def make_absolute_path(path: str, cwd: str) -> str:
    if not path:
        return ''
    if os.path.isabs(path):
        return path
    if cwd:
        return os.path.join(cwd, path)
    return os.path.abspath(path)


def _allocated_size(stat_result):
    # st_blocks counts 512-byte units actually allocated on disk (matching what
    # `du` reports), so small files are rounded up to the filesystem block size.
    # It is absent on platforms such as Windows, where we fall back to the
    # apparent size.
    st_blocks = getattr(stat_result, 'st_blocks', None)
    if st_blocks is not None:
        return st_blocks * 512
    return stat_result.st_size


def get_tree_size(path):
    '''
    Total allocated disk space of a file or directory tree, matching `du`: each
    file, directory, and symlink counts the blocks it actually occupies, and
    hard-linked files are counted only once. Falls back to the apparent size on
    platforms that do not expose st_blocks (e.g. Windows).
    '''
    try:
        root_stat = os.lstat(path)
    except OSError:
        return 0

    if not os.path.isdir(path) or os.path.islink(path):
        return _allocated_size(root_stat)

    total = 0
    seen_inodes = set()

    def add_entry(entry_path):
        nonlocal total
        try:
            stat_result = os.lstat(entry_path)
        except OSError:
            return
        # Count hard-linked files only once, like `du`.
        if stat_result.st_nlink > 1:
            key = (stat_result.st_dev, stat_result.st_ino)
            if key in seen_inodes:
                return
            seen_inodes.add(key)
        total += _allocated_size(stat_result)

    for dir_path, dir_names, file_names in os.walk(path):
        add_entry(dir_path)  # the directory itself
        for name in file_names:
            add_entry(os.path.join(dir_path, name))
        # os.walk does not recurse into symlinked directories, so count them
        # here; real subdirectories are counted when they become dir_path.
        for name in dir_names:
            entry_path = os.path.join(dir_path, name)
            if os.path.islink(entry_path):
                add_entry(entry_path)

    return total


def format_size(num_bytes):
    size = float(num_bytes)
    for unit in ('B', 'KiB', 'MiB', 'GiB', 'TiB'):
        if size < 1024.0 or unit == 'TiB':
            if unit == 'B':
                return '{} {}'.format(int(size), unit)
            return '{:.1f} {}'.format(size, unit)
        size /= 1024.0


def confirm(prompt, assume_yes=False):
    '''
    Ask the user to confirm a destructive action. Returns True only on an
    explicit yes. When stdin is not interactive (e.g. CI) and the caller did not
    pass assume_yes, defaults to False so nothing is deleted by accident.
    '''
    if assume_yes:
        return True

    if not sys.stdin or not sys.stdin.isatty():
        return False

    try:
        answer = input('{} [y/N] '.format(prompt))
    except EOFError:
        return False

    return answer.strip().lower() in ('y', 'yes')

def first_non_empty(*values):
    for value in values:
        if value:
            return value
    return None

def first_non_empty_among_keys(dictionary, *keys):
    for key in keys:
        value = dictionary.get(key)
        if value:
            return value
    return ''