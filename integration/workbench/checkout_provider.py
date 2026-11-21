#!/usr/bin/env python3
"""Checkout-backed composite FS2 adapter. Preparation is explicit; routing never builds."""
import os
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode = True
import workbench_provider as router

LAYOUT = 'checkout-v1'
PREPARE = 'python3 -B scripts/silver.py build'
REFRESH = 'python3 -B scripts/configure-simulation.py --refresh'
TARGETS = (
    'ip/controlled_fifo/verif/simulation/test_provider.exe',
    'ip/controlled_fifo/verif/simulation/fifo_sim.exe',
    'tooling_acceptance/workloads/workload_emit.exe',
    'tooling_acceptance/workloads/workload_public.exe',
    'asics/fifo_demo/cli/chip.exe',
)
MODELS = ('RM_IHPSG13_1P_256x16_c2_bm_bist.v',
          'RM_IHPSG13_1P_core_behavioral_bm_bist.v')
SUPPORT = ('integration/workbench/checkout_provider.py',
           'integration/workbench/checkout_setup.py')
SOURCE_PATHS = {
    suite: tuple(dict.fromkeys((*router.SUITE_PATHS[suite], *SUPPORT)))
    for suite in router.SUITES
}
SOURCE_PATHS[router.MEMORY_SUITE] += (
    'asics/fifo_demo/project', 'asics/fifo_demo/flows', 'tooling_acceptance/variants/controls/pt8_acceptance.py',
)


def clean_environment(environment):
    """Match the launcher's checkout environment without captured-session selectors."""
    env = router.clean_environment(environment)
    for name in list(env):
        if name.startswith(('PT8_', 'HARDCAML_WORKBENCH_')) or name == 'HARDCAML_ASIC_SYNTHESIS_TASK_LIMIT':
            env.pop(name)
    return env


def environment(manifest):
    # Absence is deliberate: never recover removed variables from the ambient
    # daemon/provider shell. Checkout manifests record a complete environment.
    return clean_environment({**manifest['environment'], 'PYTHONDONTWRITEBYTECODE': '1'})


def source_inventory(root, suite):
    # Re-evaluate root build metadata on every check, detecting additions/deletions
    # as well as edits. inventory recursively covers newly added source files.
    root = Path(root)
    metadata = []
    template = 'scripts/dune-workspace.local'
    for path in sorted(root.iterdir()):
        if not path.name.startswith('dune'):
            continue
        if (path.name == 'dune-workspace' and path.is_symlink()
                and os.readlink(path) == template):
            # configure_dune creates exactly this relative link. Inventory the
            # authored file under its own name so removing the link or replacing
            # it with a byte-identical regular workspace still changes the keys.
            source = root / template
            if source.parent.is_symlink() or source.is_symlink() or not source.is_file():
                raise ValueError('missing/nonregular workspace template: ' + str(source))
            metadata.append(template)
        elif path.is_symlink() or path.is_file():
            metadata.append(path.name)
    return router.inventory(root, (*SOURCE_PATHS[suite], *metadata))


def library_path(manifest):
    return 'lib/hardcaml_asic' if manifest.get('installed_package') else 'lib'


def target_inventory(manifest, suite):
    result = {}
    for name in manifest['suite_targets'][suite]:
        path = Path(name)
        if not path.is_absolute() or not path.is_file():
            raise ValueError('missing/nonregular target: ' + name)
        result[name] = router.sha(path)
    # The emitter/inspector depend on the persistent installed ASIC library too.
    if suite == router.MEMORY_SUITE:
        root = Path(manifest['asic_generation'])
        result.update({str(root / name): digest for name, digest in
                       router.inventory(root, (library_path(manifest),)).items()})
    return result


def drift(manifest, suite):
    try:
        actual_sources = source_inventory(manifest['project_root'], suite)
        actual_targets = target_inventory(manifest, suite)
        changed = []
        for expected, actual in ((manifest['suite_sources'][suite], actual_sources),
                                 (manifest['target_hashes'][suite], actual_targets)):
            changed.extend(k for k in expected.keys() | actual.keys()
                           if expected.get(k) != actual.get(k))
        for name in manifest['suite_executables'][suite]:
            if not os.access(name, os.X_OK):
                changed.append('target is not executable: ' + name)
        return sorted(changed)
    except (OSError, ValueError) as error:
        return ['inventory unavailable: ' + str(error)]


def refresh_command(manifest):
    return REFRESH if manifest.get('installed_package') else PREPARE


def validate_manifest(manifest, operation):
    prepare = refresh_command(manifest)
    if manifest.get('checkout_layout') != LAYOUT or manifest.get('source_layout') != router.SOURCE_LAYOUT:
        raise ValueError('checkout simulation manifest unavailable; run ' + prepare)
    suite_maps = ('suite_sources', 'suite_targets', 'suite_executables', 'target_hashes', 'provider_commands')
    old_suites = {'controlled-fifo', 'pt8-memory-workloads'}
    if all(set(manifest.get(key, {})) == old_suites for key in suite_maps):
        raise ValueError('checkout simulation suite catalog has changed; run ' + prepare)
    for key in suite_maps:
        if set(manifest.get(key, {})) != set(router.SUITES):
            raise ValueError('invalid checkout simulation manifest; run ' + prepare)
    if operation == 'discover':
        for suite in router.SUITES:
            changed = drift(manifest, suite)
            if changed:
                raise ValueError('stale ' + suite + ' checkout (' + ', '.join(changed[:8]) +
                                 '); run ' + prepare)


def main(argv=None):
    return router.main(argv, manifest_check=validate_manifest, drift_check=drift,
                       stale_guidance=lambda manifest: 'run ' + refresh_command(manifest),
                       environment_factory=environment)


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (ValueError, OSError, RuntimeError, KeyError, RecursionError,
            subprocess.TimeoutExpired) as error:
        print('Checkout composite provider: ' + str(error), file=sys.stderr)
        sys.exit(2)
