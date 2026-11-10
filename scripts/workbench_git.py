#!/usr/bin/env python3
"""Real Git dispatcher: private source context is scoped to exact source roots.

No Git output is synthesized. Supported global options are parsed only to locate
the effective working directory; the original argv is exec'd unchanged. Explicit
repository/config selectors are rejected instead of overriding an uncertain root.
"""
import hashlib
import json
import os
from pathlib import Path
import sys

sys.dont_write_bytecode = True

REPOSITORY_ENV = frozenset((
    'GIT_DIR', 'GIT_WORK_TREE', 'GIT_COMMON_DIR', 'GIT_INDEX_FILE',
    'GIT_OBJECT_DIRECTORY', 'GIT_ALTERNATE_OBJECT_DIRECTORIES', 'GIT_NAMESPACE',
    'GIT_CEILING_DIRECTORIES', 'GIT_DISCOVERY_ACROSS_FILESYSTEM', 'GIT_PREFIX',
    'GIT_INTERNAL_SUPER_PREFIX', 'GIT_SUPER_PREFIX', 'GIT_IMPLICIT_WORK_TREE',
    'GIT_CONFIG', 'GIT_CONFIG_SYSTEM', 'GIT_CONFIG_PARAMETERS', 'GIT_CONFIG_COUNT',
    'GIT_REPLACE_REF_BASE', 'GIT_NO_REPLACE_OBJECTS', 'GIT_SHALLOW_FILE', 'GIT_GRAFT_FILE',
    'GIT_EXEC_PATH',
))
CONTROLLED_ENV = dict(GIT_OPTIONAL_LOCKS='0', GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull)
GLOBAL_FLAGS = frozenset((
    '--no-pager', '--paginate', '-p', '-P', '--no-optional-locks',
    '--literal-pathspecs', '--no-literal-pathspecs', '--glob-pathspecs',
    '--noglob-pathspecs', '--icase-pathspecs', '--no-replace-objects', '--no-lazy-fetch',
))


def clean_environment(environ):
    """Preserve non-repository settings; remove selectors and injected config."""
    result = {key: value for key, value in environ.items()
              if key not in REPOSITORY_ENV and not key.startswith(('GIT_CONFIG_KEY_', 'GIT_CONFIG_VALUE_'))}
    result.update(CONTROLLED_ENV)
    return result


def effective_directory(argv, cwd):
    directory = Path(cwd)
    index = 0
    while index < len(argv):
        arg = argv[index]
        if arg == '-C':
            index += 1
            if index == len(argv):
                # Let real Git diagnose the original malformed argv/status.
                return None
            value = argv[index]
            if value:
                directory = directory / value
            index += 1
        elif arg.startswith('-C'):
            # Git requires the separate argument form. Delegate its own error,
            # without selecting any source repository for malformed argv.
            return None
        elif arg in GLOBAL_FLAGS:
            index += 1
        elif arg in ('--version', '-v', '--help', '-h'):
            return None
        elif arg.startswith('-'):
            raise ValueError('ambiguous/unsupported global Git option: ' + arg +
                             '; explicit repository/config overrides are not admitted by the development dispatcher')
        else:
            # Subcommand arguments, including `rev-parse --git-dir`, are queries
            # or pathspecs, not global repository-selection overrides.
            return str(directory.resolve())
    return None


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main(argv=None, *, context_path=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    path = Path(context_path) if context_path else Path(__file__).with_name('git-context.json')
    context = json.loads(path.read_text())
    if context['schema_version'] != 1:
        raise ValueError('unsupported scoped Git context')
    real = context['real_git']
    if sha(real) != context['real_git_sha256']:
        raise ValueError('pinned real Git executable changed; explicitly refresh the stopped development session')
    env = clean_environment(os.environ)
    directory = effective_directory(argv, Path.cwd())
    git_dir = context['source_roots'].get(directory)
    if git_dir is not None:
        env.update(GIT_DIR=git_dir, GIT_WORK_TREE=directory)
    os.execve(real, [real, *argv], env)


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError) as error:
        print('Scoped Git dispatcher: ' + str(error), file=sys.stderr)
        sys.exit(2)
