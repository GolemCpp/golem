import os
import types
import shutil


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


def handleRemoveReadonly(func, path, exc_info):
    """
    Error handler for ``shutil.rmtree``.

    If the error is due to an access error (read only file)
    it attempts to add write permission and then retries.

    If the error is for another reason it re-raises the error.

    Usage : ``shutil.rmtree(path, onerror=handleRemoveReadonly)``
    """
    import stat
    if not os.access(path, os.W_OK):
        # Is the error an access error ?
        os.chmod(path, stat.S_IWUSR)
        func(path)
    else:
        raise RuntimeError("Can't access to \"{}\"".format(path))


def removeTree(ctx, path):
    if os.path.exists(path):
        if ctx.is_windows():
            # shutil.rmtree(build_dir, ignore_errors=False, onerror=handleRemoveReadonly)
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
