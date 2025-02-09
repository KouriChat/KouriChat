from comtypes.tools import typedesc


def _calc_packing(struct, fields, pack, isStruct):
    # Try a certain packing, raise PackingError if field offsets,
    # total size ot total alignment is wrong.
    if struct.size is None:  # incomplete struct
        return -1
    if struct.name in dont_assert_size:
        return None
    if struct.bases:
        size = struct.bases[0].size
        total_align = struct.bases[0].align
    else:
        size = 0
        total_align = 8  # in bits
    for i, f in enumerate(fields):
        if f.bits:  # this code cannot handle bit field sizes.
            # print "##XXX FIXME"
            return -2  # XXX FIXME
        s, a = storage(f.typ)
        if pack is not None:
            a = min(pack, a)
        if size % a:
            size += a - size % a
        if isStruct:
            if size != f.offset:
                raise PackingError(f"field {f.name} offset ({size}/{f.offset})")
            size += s
        else:
            size = max(size, s)
        total_align = max(total_align, a)
    if total_align != struct.align:
        raise PackingError(f"total alignment ({total_align}/{struct.align})")
    a = total_align
    if pack is not None:
        a = min(pack, a)
    if size % a:
        size += a - size % a
    if size != struct.size:
        raise PackingError(f"total size ({size}/{struct.size})")


def calc_packing(struct, fields):
    # try several packings, starting with unspecified packing
    isStruct = isinstance(struct, typedesc.Structure)
    for pack in [None, 16 * 8, 8 * 8, 4 * 8, 2 * 8, 1 * 8]:
        try:
            _calc_packing(struct, fields, pack, isStruct)
        except PackingError as details:
            continue
        else:
            if pack is None:
                return None

            return int(pack / 8)

    raise PackingError(f"PACKING FAILED: {details}")


class PackingError(Exception):
    pass


# XXX These should be filtered out in gccxmlparser.
dont_assert_size = set(
    [
        "__si_class_type_info_pseudo",
        "__class_type_info_pseudo",
    ]
)


def storage(t):
    # return the size and alignment of a type
    if isinstance(t, typedesc.Typedef):
        return storage(t.typ)
    elif isinstance(t, typedesc.ArrayType):
        s, a = storage(t.typ)
        return s * (int(t.max) - int(t.min) + 1), a
    return int(t.size), int(t.align)
