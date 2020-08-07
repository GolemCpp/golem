import os
import sys
import types
import shutil
import subprocess
from urllib.parse import urlparse


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


def handle_remove_readonly(func, path, exc_info):
    """
    Error handler for ``shutil.rmtree``.

    If the error is due to an access error (read only file)
    it attempts to add write permission and then retries.

    If the error is for another reason it re-raises the error.

    Usage : ``shutil.rmtree(path, onerror=handle_remove_readonly)``
    """
    import stat
    if not os.access(path, os.W_OK):
        # Is the error an access error ?
        os.chmod(path, stat.S_IWUSR)
        func(path)
    else:
        raise RuntimeError("Can't access to \"{}\"".format(path))


def remove_tree(ctx, path):
    if os.path.exists(path):
        if ctx.is_windows():
            # shutil.rmtree(build_dir, ignore_errors=False, onerror=handle_remove_readonly)
            from time import sleep
            while os.path.exists(path):
                os.system("rmdir /s /q %s" % path)
                sleep(0.1)
        else:
            shutil.rmtree(path)


def make_directory(base, path=None):
    directory = base
    if path is not None:
        directory = os.path.join(directory, path)
    if not os.path.exists(directory):
        os.makedirs(directory)
    return directory


def generate_recipe_id(url):
    url = url.replace('file:///', 'file://')
    o = urlparse(url)
    host = o.hostname.split('.')
    host.reverse()
    path = list(filter(None, o.path.split('/')))

    if len(path) > 0 and path[-1].endswith('.git'):
        path[-1] = path[-1][:-4]

    path = list(filter(None, path))

    identifier = host + path
    for index, s in enumerate(identifier):
        identifier[index] = ''.join(
            filter(
                lambda x: x in
                "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ-_",
                s)).lower()

    name = identifier[-1]
    host = identifier[:-1]

    host = '.'.join(host)

    if not host:
        host = '_no_host_'

    repo_id = name + '@' + host

    return ''.join(repo_id)


def make_dep_base(dep):
    dep_id = generate_recipe_id(dep.repository)
    return dep_id + '+' + str(
        dep.resolved_hash[:8] if dep.resolved_hash else dep.resolved_version)


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


def run_task(args, cwd=None, debug=False, **kwargs):
    if debug:
        print("Run {}".format(' '.join(args)))
    process = subprocess.Popen(args,
                               cwd=cwd,
                               shell=sys.platform.startswith('win32'),
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
