"""Silver companion lookup; paths inside a config remain project-root relative.

Writers retain existing locations (including both identical copies). This helper
never creates a directory or migrates a configuration.
"""
import os
from pathlib import Path
import stat

BASENAMES = ('silver.sexp', 'silver-asic.sexp',
             'silver-simulation.sexp', 'silver-preparation.sexp')


def legacy_name(filename):
    return filename.replace('silver', 'hardcaml-workbench', 1)


def candidate_paths(root, filename):
    root = Path(root)
    if not root.is_absolute() or filename not in BASENAMES:
        raise ValueError('expected absolute root and a Silver configuration basename')
    old = legacy_name(filename)
    return (root / '.silver' / filename, root / filename,
            root / '.silver' / old, root / '.workbench' / filename,
            root / '.workbench' / old, root / old)


def captured(root, filename):
    """Immutable prepared selections used either basename across versions."""
    paths = (root / filename, root / legacy_name(filename))
    found = {path: data for path in paths if (data := read_regular(path)) is not None}
    if len(set(found.values())) > 1:
        raise RuntimeError('Conflicting captured configuration files: ' + str(root))
    return next(iter(found), paths[0])


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
    paths = candidate_paths(root, filename)
    found = {path: data for path in paths if (data := read_regular(path)) is not None}
    if len(set(found.values())) > 1:
        raise RuntimeError('Conflicting configuration files: ' + ' and '.join(map(str, found)) + ' differ')
    return found


def selected(root, filename):
    found = copies(root, filename)
    return next(iter(found), candidate_paths(root, filename)[0])


def destinations(root, filename):
    """Freeze these paths before publication: intermediate dual writes can differ."""
    return tuple(copies(root, filename)) or (candidate_paths(root, filename)[0],)


def existing_configs(root):
    """All present recognized configs, including byte-identical aliases."""
    return [path for filename in BASENAMES for path in copies(root, filename)]
