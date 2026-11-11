"""Small launcher API for explicit, in-place simulation preparation.

prepare_simulation(..., run=...) invokes run(argv, cwd=Path, env=dict). The supplied
callable MUST bound execution time/output, raise on failure, and serialize builds
using the launcher's shared example flock. Dune uses exactly two jobs. It may
return bytes/None or a CompletedProcess (whose return code is checked here).
The launcher owns its overall pool budget. No build is performed at import time.
"""
import json
import os
from pathlib import Path
import sys
import uuid

import checkout_provider as checkout
import workbench_provider as router


def prepare_simulation(*, project_root, build_dir, asic_generation, model_root,
                       run, environment=None, dune='dune', python=sys.executable,
                       simulation_dir=None):
    """Build actual checkout targets, then atomically publish manifest.json.

    All roots are persistent, caller-selected paths; project_root is the editable
    example checkout, never a copied store/project. Returns the manifest dict,
    including manifest_path, provider_command, project_executable and targets.
    A failed/racing build never publishes a new inventory. If environment is
    supplied, it is the complete build/runtime environment, not an overlay on
    os.environ. simulation_dir optionally selects the persistent manifest and
    producer-evidence directory used by the launcher.
    """
    root = Path(project_root).resolve(strict=True)
    build = Path(build_dir)
    if not build.is_absolute():
        build = root / build
    build = build.resolve()
    generation = Path(asic_generation).resolve(strict=True)
    models = Path(model_root).resolve(strict=True)
    state = (Path(simulation_dir) if simulation_dir is not None else
             root / '.dev/workbench-main/simulation').resolve()
    state.mkdir(parents=True, exist_ok=True)
    manifest_path = state / 'manifest.json'
    env = checkout.clean_environment(os.environ if environment is None else environment)
    env.update(PYTHONDONTWRITEBYTECODE='1', OMP_NUM_THREADS='1',
               OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1',
               HARDCAML_ASIC_GENERATION=str(generation))
    # Use the supplied dependency environment, extending rather than discarding
    # an SDK OCAMLPATH. The generation itself is always first.
    env['OCAMLPATH'] = str(generation / 'lib') + (
        os.pathsep + env['OCAMLPATH'] if env.get('OCAMLPATH') else '')
    env['PATH'] = str(generation / 'bin') + os.pathsep + env.get('PATH', '')
    binaries = {name: str(build / 'default' / name) for name in checkout.TARGETS}
    fifo = [binaries[checkout.TARGETS[0]], '--simulator', binaries[checkout.TARGETS[1]]]
    pt8 = [str(python), '-B', str(root / 'integration/workbench/pt8_workbench_provider.py'),
           '--generation', str(generation), '--producer-root', str(root),
           '--emitter', binaries[checkout.TARGETS[2]], '--model-root', str(models),
           '--output-root', str(state / 'workloads')]
    command = [str(python), '-B', str(root / 'integration/workbench/checkout_provider.py'),
               '--manifest', str(manifest_path)]
    # Record everything executed or read at run time; no captured executable,
    # copied models, shim dune, or acceptance session is needed.
    suite_targets = {
        'controlled-fifo': fifo[::2],
        'pt8-memory-workloads': [binaries[checkout.TARGETS[2]],
                                str(generation / 'bin/hardcaml-asic-flow'),
                                *[str(models / name) for name in checkout.MODELS]],
    }
    manifest = dict(schema_version=1, checkout_layout=checkout.LAYOUT,
                    source_layout=router.SOURCE_LAYOUT, project_root=str(root),
                    build_dir=str(build), asic_generation=str(generation),
                    model_root=str(models), manifest_path=str(manifest_path),
                    targets=binaries, project_executable=binaries[checkout.TARGETS[4]],
                    provider_command=command,
                    provider_commands=dict(zip(router.SUITES, (fifo, pt8))),
                    environment=env,
                    suite_targets=suite_targets,
                    suite_executables={'controlled-fifo': fifo[::2],
                        'pt8-memory-workloads': suite_targets['pt8-memory-workloads'][:2]},
                    max_jobs=2, eda_allocation=0)
    before = {suite: checkout.source_inventory(root, suite) for suite in router.SUITES}
    # Catch changes to supplied immutable dependencies during the build too.
    dependency_before = router.inventory(generation, ('bin/hardcaml-asic-flow', 'lib'))
    models_before = router.inventory(models, checkout.MODELS)
    argv = [str(dune), 'build', '--root', str(root), '--build-dir', str(build),
            '-j', '2', *checkout.TARGETS]
    result = run(argv, cwd=root, env=env)
    if getattr(result, 'returncode', 0):
        raise RuntimeError('checkout simulation build failed; run ' + checkout.PREPARE)
    after = {suite: checkout.source_inventory(root, suite) for suite in router.SUITES}
    if (before != after or dependency_before != router.inventory(
            generation, ('bin/hardcaml-asic-flow', 'lib')) or
            models_before != router.inventory(models, checkout.MODELS)):
        raise RuntimeError('simulation inputs changed during build; run ' + checkout.PREPARE)
    manifest['suite_sources'] = after
    manifest['target_hashes'] = {suite: checkout.target_inventory(manifest, suite)
                                 for suite in router.SUITES}
    # Also verify ancillary launcher/preparation build products, even though
    # these are not used by FS2 simulation runs.
    manifest['built_target_hashes'] = {path: router.sha(path) for path in binaries.values()}
    for paths in manifest['suite_executables'].values():
        if any(not os.access(path, os.X_OK) for path in paths):
            raise RuntimeError('build did not produce executable simulation targets')
    temporary = state / ('.manifest-' + uuid.uuid4().hex)
    try:
        with temporary.open('x') as stream:
            json.dump(manifest, stream, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, manifest_path)
    finally:
        temporary.unlink(missing_ok=True)
    return manifest
