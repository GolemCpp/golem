import types


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
