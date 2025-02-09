from ctypes import pythonapi, py_object


pythonapi.PyInstanceMethod_New.argtypes = [py_object]
pythonapi.PyInstanceMethod_New.restype = py_object
PyInstanceMethod_Type = type(pythonapi.PyInstanceMethod_New(id))


def instancemethod(func, inst, cls):
    mth = PyInstanceMethod_Type(func)
    if inst is None:
        return mth
    return mth.__get__(inst)
