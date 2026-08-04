import locale
import os
import sys
import types
import shutil
import subprocess
from pathlib import Path

from golemcpp.golem import network


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
        from time import sleep
        while os.path.exists(path):
            os.system('rmdir /s /q {}'.format(subprocess.list2cmdline([path])))
            sleep(0.1)
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


def resolved_reference(resolved_version, resolved_hash):
    '''
    The effective git reference of a resolved resource: the short hash when known,
    else the resolved version name. Used to build a resource's cache key so any
    resolved resource (dependency, tool, repository) keys the same way.
    '''
    return resolved_hash[:8] if resolved_hash else resolved_version


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
    git_index = os.path.join(path, '.git', 'HEAD')
    return os.path.exists(git_index)

def is_not_git_repository(path):
    git_dir = os.path.join(path, '.git')
    return not os.path.exists(git_dir)

def does_git_command_need_no_repository(args):
    if args[1] in ['init', 'clone']:
        return True
    return False

def does_git_command_need_nothing(args):
    if args[1] in ['ls-remote']:
        return True
    return False

def is_network_git_command(args):
    '''
    Git commands that reach the remote. `submodule update` clones a submodule
    that is not there, while `submodule foreach` only runs in the ones already
    cloned, so the two are not the same.

    `submodule update --no-fetch` is told to work from the objects already here
    and to fail rather than go looking, which is what a resource being refreshed
    without consulting its remote needs.
    '''
    command = args[1]
    if command == 'submodule':
        return args[2:3] == ['update'] and '--no-fetch' not in args
    return command in ['clone', 'fetch', 'pull', 'push', 'ls-remote']

def validate_git_command(args, cwd):
    if is_network_git_command(args=args) and not network.is_allowed():
        raise RuntimeError(
            "Cannot run \"{}\" from \"{}\": reaching a remote is a resolve step. "
            "Run golem resolve first.".format(' '.join(args), cwd))

    if does_git_command_need_no_repository(args=args):
        if not is_not_git_repository(path=cwd):
            raise RuntimeError(
                "Already a git repository: \"{}\" from \"{}\"".format(' '.join(args), cwd))
    elif does_git_command_need_nothing(args=args):
        pass
    else:
        # Needs a repository
        if not is_git_repository(path=cwd):
            raise RuntimeError(
                "Not a git repository: \"{}\" from \"{}\"".format(' '.join(args), cwd))

def run_git(params, cwd, quiet=False, **kwargs):
    '''
    `quiet` drops what the command has to say on stdout.
    '''
    args = ['git'] + params

    validate_git_command(args=args, cwd=cwd)

    if quiet:
        kwargs.setdefault('stdout', subprocess.DEVNULL)

    run_task(args=args, cwd=cwd, **kwargs)

def check_git_output(params, cwd, **kwargs):
    args = ['git'] + params

    validate_git_command(args=args, cwd=cwd)

    output = subprocess.check_output(args, cwd=cwd, **kwargs)
    output = decode_output(output)
    
    return output

def call_git(params, cwd, **kwargs):
    args = ['git'] + params

    validate_git_command(args=args, cwd=cwd)

    return subprocess.call(args, cwd=cwd, **kwargs)

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