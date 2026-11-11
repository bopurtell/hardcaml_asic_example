"""Workbench companion lookup; paths inside a config remain project-root relative.

Writers retain existing locations (including both identical copies). This helper
never creates .workbench or migrates a configuration.
"""
import os
from pathlib import Path
import stat

BASENAMES = ('hardcaml-workbench.sexp', 'hardcaml-workbench-asic.sexp',
             'hardcaml-workbench-simulation.sexp', 'hardcaml-workbench-preparation.sexp')


def read_regular(path, max_bytes=1024 * 1024):
    path = Path(path)
    for part in reversed((path, *path.parents)):
        try:
            info = part.lstat()
        except FileNotFoundError:
            return None
        if stat.S_ISLNK(info.st_mode):
            raise RuntimeError('symlink configuration path: ' + str(part))
        if part != path and not stat.S_ISDIR(info.st_mode):
            raise RuntimeError('not a configuration directory: ' + str(part))
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
    before = os.fstat(fd)
    if not stat.S_ISREG(before.st_mode) or before.st_size > max_bytes:
        os.close(fd)
        raise RuntimeError('expected bounded regular configuration: ' + str(path))
    with os.fdopen(fd, 'rb') as stream:
        data = stream.read(max_bytes + 1)
        after = os.fstat(stream.fileno())
        current = path.lstat()
        if (len(data) > max_bytes or len(data) != before.st_size
                or (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns)
                != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)
                or (after.st_dev, after.st_ino) != (current.st_dev, current.st_ino)
                or path.resolve() != path):
            raise RuntimeError('configuration changed while reading: ' + str(path))
        return data


def copies(root, filename):
    root = Path(root)
    if not root.is_absolute() or filename not in BASENAMES:
        raise ValueError('expected absolute root and a Workbench configuration basename')
    paths = (root / '.workbench' / filename, root / filename)
    found = {path: data for path in paths if (data := read_regular(path)) is not None}
    if len(found) == 2 and len(set(found.values())) != 1:
        raise RuntimeError('Conflicting configuration files: ' + ' and '.join(map(str, found)) + ' differ')
    return found


def selected(root, filename):
    found = copies(root, filename)
    return next(iter(found), Path(root) / filename)


def destinations(root, filename):
    """Freeze these paths before publication: intermediate dual writes can differ."""
    return tuple(copies(root, filename)) or (Path(root) / filename,)
