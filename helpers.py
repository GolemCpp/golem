import os
import sys
import types
import shutil
import subprocess


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
        def canprint(o): return isinstance(
            o, (int, float, str, unicode, bool, types.NoneType, types.LambdaType))
        try:
            if canprint(obj) or sum(not canprint(o) for o in obj) == 0:
                return repr(obj)
        except TypeError, e:
            pass
        # try to iterate as if obj were a list
        try:
            return "[\n" + "\n".join(l + print_obj(k, depth=depth-1, l=l+"  ") + "," for k in obj) + "\n" + l + "]"
        except TypeError, e:
            # else, expand/recurse object attribs
            name = (hasattr(obj, '__class__')
                    and obj.__class__.__name__ or type(obj).__name__)
            objdict = {}
            for a in dir(obj):
                if a[:2] != "__" and (not hasattr(obj, a) or not hasattr(getattr(obj, a), '__call__')):
                    try:
                        objdict[a] = getattr(obj, a)
                    except Exception, e:
                        objdict[a] = str(e)
    return name + " {\n" + "\n".join(l + repr(k) + ": " + print_obj(v, depth=depth-1, l=l+"  ") + "," for k, v in objdict.iteritems()) + "\n" + l + "}"


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


def make_dep_base(dep):
    return dep.name + "-" + str(dep.resolved_version if dep.resolved_version else dep.version)


def copy_tree(source_path, destination_path):
    if not os.path.isdir(destination_path):
        raise ValueError(str(destination_path) + " is not a directory")

    destination_path = make_directory(destination_path)

    for dirName, subdirList, fileList in os.walk(source_path):
        for fname in fileList:
            copy_file(os.path.join(dirName, fname), destination_path)
        for dname in subdirList:
            dname_destination = make_directory(destination_path, dname)
            copy_tree(os.path.join(dirName, dname),
                      dname_destination)
        break


def copy_file(source_path, destination_path):
    if os.path.isdir(destination_path):
        destination_directory = destination_path
        destination_path = os.path.join(
            destination_path, os.path.basename(source_path))
    else:
        destination_directory = os.path.dirname(destination_path)

    if os.path.islink(source_path):
        link_path = os.readlink(source_path)
        if os.path.isabs(link_path):
            link_path_absolute = link_path
            link_path_relative = os.path.basename(link_path_absolute)
        else:
            link_path_relative = link_path
            link_path_absolute = os.path.join(
                os.path.dirname(source_path), link_path_relative)

        copy_file(link_path_absolute, destination_directory)
        if os.path.exists(destination_path):
            os.remove(destination_path)
        os.symlink(link_path_relative, destination_path)
    else:
        shutil.copy(source_path, destination_path)


def run_task(args, cwd=None, **kwargs):
    process = subprocess.Popen(args, cwd=cwd, shell=sys.platform.startswith(
        'win32'), **kwargs)
    ret = process.wait()
    if ret != 0:
        raise RuntimeError(
            "Return code {} when running \"{}\" from \"{}\"".format(ret, ' '.join(args), os.getcwd() if cwd is None else cwd))


def RepresentsInt(s):
    try:
        int(s)
        return True
    except ValueError:
        return False


def byteify(input):
    if isinstance(input, dict):
        return {byteify(key): byteify(value)
                for key, value in input.iteritems()}
    elif isinstance(input, list):
        return [byteify(element) for element in input]
    elif isinstance(input, unicode):
        return input.encode('utf-8')
    else:
        return input
