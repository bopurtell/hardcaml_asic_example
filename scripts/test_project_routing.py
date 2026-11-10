"""Actual consumer executable, synthetic provenance and recording provider; no EDA."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import unittest
import venv

EXE, EXPORTER, SOURCE = [Path(p).resolve() for p in sys.argv[1:4]]
sys.argv[1:] = []


class RoutingTests(unittest.TestCase):
    def setUp(self):
        evidence = os.environ.get('HARDCAML_ASIC_TEST_EVIDENCE')
        self.retain = bool(evidence and self._testMethodName in (
            'test_named_installed_native_early_reference_and_request',
            'test_native_prepared_synthesis_report_and_allocation_only_reconnect'))
        if self.retain:
            Path(evidence).mkdir(parents=True, exist_ok=True)
            self.tmp = tempfile.TemporaryDirectory(prefix="native-namedflow-", dir=evidence, delete=False)
        else:
            self.tmp = tempfile.TemporaryDirectory(prefix="fifo-routing-")
            self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.root = self.base / "project"
        self.root.mkdir()
        self.env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_") and k != "TOOLCHAIN"}
        self.env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
                        GIT_AUTHOR_NAME="Bundle test", GIT_AUTHOR_EMAIL="bundle@test.invalid",
                        GIT_COMMITTER_NAME="Bundle test", GIT_COMMITTER_EMAIL="bundle@test.invalid",
                        GIT_AUTHOR_DATE="2026-01-01T00:00:00Z", GIT_COMMITTER_DATE="2026-01-01T00:00:00Z")
        inputs = subprocess.check_output([str(EXPORTER), "--inputs"], env=self.env, text=True).splitlines()
        for name in inputs:
            dest = self.root / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(SOURCE / name, dest)
        def git(*args):
            return subprocess.check_output(["git", "-C", str(self.root), "-c", "core.hooksPath=/dev/null",
                "-c", "commit.gpgsign=false", "-c", "init.templateDir=", *args], env=self.env, text=True).strip()
        git("init", "--initial-branch=fixture")
        git("add", ".")
        git("commit", "-m", "baseline")
        self.assertEqual(git("show", "-s", "--format=%an <%ae>|%cn <%ce>"),
                         "Bundle test <bundle@test.invalid>|Bundle test <bundle@test.invalid>")
        self.assertEqual(git("remote"), "")
        self.nested = self.root / "nested" / "deeper"
        self.nested.mkdir(parents=True)
        self.outside = self.base / "outside"
        self.outside.mkdir()
        self.providers = self.base / "providers"
        self.providers.mkdir()
        self.log = self.base / "calls.jsonl"
        self.versions = self.base / "versions.jsonl"
        provider = self.providers / "hardcaml-asic-flow"
        provider.write_text(f"#!{sys.executable}\n" + '''import json, os, sys
if '--version' in sys.argv:
    if os.environ.get('VERSION_RECORD'):
        with open(os.environ['VERSION_RECORD'], 'a') as f: f.write(json.dumps(sys.argv[1:]) + '\\n')
    print(os.environ.get('METADATA', json.dumps({'cli_contract': {
        'version': json.loads(os.environ.get('CONTRACT', '2')),
        'capabilities': {'namedflow1': json.loads(os.environ.get('NAMEDFLOW', 'true'))}}})))
else:
    with open(os.environ['RECORD'], 'a') as f:
        f.write(json.dumps({'argv': sys.argv[1:], 'cwd': os.getcwd(), 'executable': sys.argv[0]}) + '\\n')
    if '--workspace' in sys.argv:
        workspace = sys.argv[sys.argv.index('--workspace') + 1]
        assert not os.path.lexists(workspace), 'consumer precreated workspace'
    if sys.argv[1] == 'stages' and '--json' in sys.argv:
        print(json.dumps({'event': 'observation_allocated', 'recorded': True}), flush=True)
        print(json.dumps({'execution': 'complete', 'recorded': True}), flush=True)
    else:
        print(json.dumps({'recorded': True}) if '--json' in sys.argv else 'Recorded implementation dispatch')
    if '--verbose' in sys.argv: print('provider diagnostic', file=sys.stderr)
    if os.environ.get('PROVIDER_SIGNAL'): os.kill(os.getpid(), int(os.environ['PROVIDER_SIGNAL']))
    sys.exit(int(os.environ.get('PROVIDER_EXIT', '0')))
''')
        provider.chmod(0o755)
        self.env.update(PATH=str(self.providers) + os.pathsep + self.env.get("PATH", ""),
                        RECORD=str(self.log), VERSION_RECORD=str(self.versions))

    def invoke(self, *args, cwd=None, status=0, env=None):
        result = subprocess.run([str(EXE), *args], cwd=cwd or self.nested, env=env or self.env,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, status, (args, result.stdout, result.stderr))
        return result

    def call(self):
        return json.loads(self.log.read_text().splitlines()[-1])

    def test_default_emit_reuse_and_corruption(self):
        first = json.loads(self.invoke("emit", "--json").stdout)
        path = Path(first['output_dir'])
        self.assertEqual(path.parent, self.root / '_flow_results/bundles')
        self.assertTrue(path.is_symlink())
        self.assertEqual(path.resolve().parent, path.parent / '.objects')
        self.assertEqual(json.loads(self.invoke('emit', '--json', '--verbose').stdout), first)
        self.assertIn('Reused', self.invoke('emit').stdout)
        manifest = path / 'manifest.json'
        manifest.write_text('corrupt')
        self.invoke('emit', '--json', status=1)
        self.assertEqual(manifest.read_text(), 'corrupt')

    def test_explicit_roots_and_exact_output(self):
        response = json.loads(self.invoke('emit', '--project-root', '../project', '--source-root', '../project',
            '--results-root', 'results', '--json', cwd=self.outside).stdout)
        self.assertEqual(Path(response['output_dir']).parent, self.outside / 'results/bundles')
        exact = json.loads(self.invoke('emit', '--source-root', '../project', '--output-dir', 'exact',
            '--json', cwd=self.outside).stdout)
        self.assertEqual(exact['output_dir'], str(self.outside / 'exact'))
        self.assertFalse(Path(exact['output_dir']).is_symlink())

    def test_validation_and_readonly(self):
        for args in [('run',), ('run', '--stage', 'invalid'),
                     ('emit', '--project-root', str(self.root), '--source-root', str(self.outside)),
                     ('run', '--stage', 'full', '--bogus'),
                     ('preflight', '--python', '--json'), ('emit', '--results-root', '')]:
            self.invoke(*args, status=2)
        self.invoke('emit', cwd=self.outside, status=2)
        generated = self.root / '_build/default'
        generated.mkdir(parents=True)
        self.invoke('emit', cwd=generated, status=2)
        self.assertFalse((self.root / '_flow_results').exists())
        self.assertFalse(self.log.exists())
        for command in ['describe', 'emit', 'preflight', 'run']:
            self.invoke(command, '--help', cwd=self.outside)
        self.invoke('describe', '--json', cwd=self.outside)
        self.assertFalse((self.root / '_flow_results').exists())
        (self.root / 'asics/fifo_demo/cli/project.ml').unlink()
        self.invoke('emit', status=2)
        self.assertFalse((self.root / '_flow_results').exists())

    def test_default_dispatch_json_and_current_source(self):
        response = self.invoke('preflight', '--json', '--verbose')
        self.assertEqual(json.loads(response.stdout), {'recorded': True})
        self.assertIn('provider diagnostic', response.stderr)
        call = self.call()
        argv = call['argv']
        self.assertEqual(call['cwd'], str(self.nested))
        self.assertEqual(argv[0], 'preflight')
        self.assertEqual(argv[2:], ['--results-root', str(self.root / '_flow_results'),
            '--toolchain', str(self.root / '_flow_tools'), '--json', '--verbose'])
        first = argv[1]
        with (self.root / 'README.md').open('a') as f: f.write('\nchanged source\n')
        self.invoke('run', '--stage', 'synthesis', '--json')
        self.assertNotEqual(self.call()['argv'][1], first)
        self.assertEqual(len(self.log.read_text().splitlines()), 2)  # no duplicated preflight

    def test_overrides_exit_and_explicit_bundle(self):
        env = dict(self.env, TOOLCHAIN='env tools', PROVIDER_EXIT='37')
        self.invoke('run', '--bundle', 'bundle', '--stage', 'full', '--results-root', 'results',
            '--runs', 'runs', '--toolchain', 'explicit tools', '--python', 'python',
            '--support-tools', 'support', '--pdk-root', 'pdk', '--native', '--json',
            cwd=self.outside, env=env, status=37, *['--project-root', str(self.root)])
        argv = self.call()['argv']
        self.assertEqual(argv, ['run', str(self.outside / 'bundle'), '--results-root', str(self.outside / 'results'),
            '--toolchain', str(self.outside / 'explicit tools'), '--python', str(self.outside / 'python'),
            '--support-tools', str(self.outside / 'support'), '--pdk-root', str(self.outside / 'pdk'),
            '--runs', str(self.outside / 'runs'), '--stage', 'full', '--native', '--json'])
        self.assertFalse((self.root / '_flow_results').exists())
        self.invoke('preflight', '--bundle', 'bundle', '--output', 'report.json', env=dict(self.env, TOOLCHAIN='env tools'))
        argv = self.call()['argv']
        self.assertEqual(argv[argv.index('--toolchain') + 1], str(self.nested / 'env tools'))
        self.assertEqual(argv[argv.index('--output') + 1], str(self.nested / 'report.json'))

    def test_missing_and_old_provider_no_emission(self):
        result = self.invoke('preflight', env=dict(self.env, PATH=''), status=1)
        self.assertIn('install/activate', result.stderr)
        result = self.invoke('preflight', env=dict(self.env, CONTRACT='1'), status=1)
        self.assertIn('CLI contract 2', result.stderr)
        self.assertFalse((self.root / '_flow_results').exists())
        self.assertFalse(self.log.exists())

    def test_supported_contracts_preserve_human_json_routing(self):
        for version in ('2', '3', '4'):
            for flags in ([], ['--json']):
                with self.subTest(version=version, flags=flags):
                    result = self.invoke('preflight', '--bundle', 'unused', *flags,
                                         env=dict(self.env, CONTRACT=version))
                    self.assertEqual('--json' in self.call()['argv'], bool(flags))
                    if flags:
                        self.assertEqual(json.loads(result.stdout), {'recorded': True})
                    else:
                        self.assertEqual(result.stdout.strip(), 'Recorded implementation dispatch')
        self.assertFalse((self.root / '_flow_results').exists())

    def test_unknown_or_malformed_contract_refused_before_emission(self):
        for version in ('5', 'null', '"4"', 'true', '4.0'):
            with self.subTest(version=version):
                result = self.invoke('preflight', env=dict(self.env, CONTRACT=version), status=1)
                self.assertIn('CLI contract 2, 3 or 4', result.stderr)
                self.assertFalse((self.root / '_flow_results').exists())
                self.assertFalse(self.log.exists())

    def test_endpoint_errors_before_emission(self):
        for args in [('--stage', 'full'), ('--native',), ('--runs', 'runs'),
                     ('--plan', 'recipe'), ('--checkpoint', 'checkpoint'), ('--endpoint', 'invalid')]:
            self.invoke('run', '--endpoint', 'synthesis', *args, status=2,
                        env=dict(self.env, CONTRACT='4'))
        for version in ('2', '3', '5', '"4"', 'true', '4.0'):
            self.invoke('run', '--endpoint', 'synthesis', status=1,
                        env=dict(self.env, CONTRACT=version))
        self.assertFalse((self.root / '_flow_results').exists())
        self.assertFalse(self.log.exists())

    def test_endpoint_dispatch_uniqueness_and_complete_output(self):
        env = dict(self.env, CONTRACT='4', TOOLCHAIN='env tools')
        workspaces = []
        for endpoint in ('synthesis', 'floorplan', 'placement', 'cts', 'routing', 'signoff', 'synthesis'):
            result = self.invoke('run', '--endpoint', endpoint, '--json', env=env)
            self.assertEqual([json.loads(line) for line in result.stdout.splitlines()],
                             [{'event': 'observation_allocated', 'recorded': True},
                              {'execution': 'complete', 'recorded': True}])
            argv = self.call()['argv']
            value = lambda flag: argv[argv.index(flag) + 1]
            workspace = Path(value('--workspace'))
            workspaces.append(workspace)
            self.assertEqual(argv[0], 'stages')
            self.assertEqual(value('--endpoint'), endpoint)
            self.assertEqual(workspace.parent, self.root / '_flow_results')
            self.assertFalse(workspace.exists())
            self.assertEqual(value('--checkpoint-store'), str(workspace / 'checkpoints'))
            self.assertEqual(value('--support-tools'), str(self.nested / 'env tools/tt'))
            self.assertEqual(value('--pdk-root'), str(self.nested / 'env tools/pdk'))
            self.assertEqual(value('--python'), str(self.nested / 'env tools/.venv/bin/python'))
            self.assertNotIn('--observation-store', argv)
            self.assertNotIn('--stage', argv)
        self.assertEqual(len(set(workspaces)), 7)
        self.assertIn('Recorded implementation dispatch', self.invoke(
            'run', '--endpoint', 'synthesis', env=env).stdout)

    def test_endpoint_explicit_bundle_spaces_overrides_and_exit(self):
        env = dict(self.env, CONTRACT='4', PROVIDER_EXIT='37', TOOLCHAIN='ignored tools')
        (self.root / 'asics/fifo_demo/cli/project.ml').unlink()  # would prevent emission
        self.invoke('run', '--endpoint', 'floorplan', '--project-root', str(self.root),
                    '--bundle', 'existing bundle', '--results-root', 'result store',
                    '--toolchain', 'explicit tools', '--support-tools', 'support tools',
                    '--pdk-root', 'pdk root', '--python', 'venv python', '--json', '--verbose',
                    cwd=self.outside, env=env, status=37)
        argv = self.call()['argv']
        value = lambda flag: argv[argv.index(flag) + 1]
        self.assertEqual(argv[1], str(self.outside / 'existing bundle'))
        self.assertEqual(Path(value('--workspace')).parent, self.outside / 'result store')
        for flag, suffix in [('--support-tools', 'support tools'), ('--pdk-root', 'pdk root'),
                             ('--python', 'venv python')]:
            self.assertEqual(value(flag), str(self.outside / suffix))
        self.assertFalse((self.outside / 'result store/bundles').exists())
        self.assertFalse((self.root / '_flow_results').exists())
        self.assertIn('--verbose', argv)
        self.invoke('run', '--endpoint', 'synthesis', '--bundle', 'unused', env=dict(
            self.env, CONTRACT='4', PROVIDER_SIGNAL=str(signal.SIGTERM)), status=-signal.SIGTERM)

    def test_directory_paths_preserve_symlink_parent_traversal(self):
        child = self.root / 'child'
        child.mkdir()
        (self.outside / 'alias').symlink_to(child, target_is_directory=True)
        for name in ('bundle', 'tools', 'support', 'pdk'):
            (self.root / name).mkdir()
        self.invoke('preflight', '--project-root', 'alias/..', '--source-root', str(self.root),
                    '--bundle', 'alias/../bundle', '--toolchain', 'alias/../tools',
                    '--support-tools', 'alias/../support', '--pdk-root', 'alias/../pdk',
                    '--results-root', 'alias/../results', '--output', 'alias/../report.json',
                    cwd=self.outside)
        argv = self.call()['argv']
        self.assertTrue(os.path.samefile(argv[1], self.root / 'bundle'))
        for flag, name in (('--toolchain', 'tools'), ('--support-tools', 'support'), ('--pdk-root', 'pdk')):
            self.assertTrue(os.path.samefile(argv[argv.index(flag) + 1], self.root / name))
        for flag, name in (('--results-root', 'results'), ('--output', 'report.json')):
            self.assertEqual(argv[argv.index(flag) + 1], str(self.outside / ('alias/../' + name)))
        response = json.loads(self.invoke('emit', '--source-root', 'alias/..',
            '--output-dir', 'alias/../exact', '--json', cwd=self.outside).stdout)
        self.assertTrue(os.path.samefile(response['output_dir'], self.root / 'exact'))
        self.assertFalse((self.outside / 'exact').exists())

    def test_provider_signal_is_preserved(self):
        self.invoke('run', '--stage', 'synthesis', '--bundle', 'unused',
                    env=dict(self.env, PROVIDER_SIGNAL=str(signal.SIGTERM)), status=-signal.SIGTERM)
        self.assertFalse((self.root / '_flow_results').exists())

    def preview(self, *args):
        explicit = ['--project-root', str(self.root)] if self.retain else []
        return json.loads(self.invoke('flow', 'plan', '--endpoint', 'synthesis', '--json', *explicit, *args).stdout)

    def named_run(self, plan, *args, **kwargs):
        explicit = ['--project-root', str(self.root)] if self.retain else []
        return self.invoke('flow', 'run', '--endpoint', 'synthesis', '--expected-plan-identity',
                           plan['plan_identity'], *explicit, *args, **kwargs)

    def test_named_profiles_and_pure_preview(self):
        plan = self.preview()
        delay = self.preview('--flow', 'standard', '--profile', 'synth_delay')
        default = self.preview('--flow', 'standard')
        self.assertEqual(plan, default)
        self.assertEqual(plan['contract'], 'hardcaml-asic.methodology-plan')
        self.assertEqual(plan['schema_version'], 1)
        self.assertNotEqual(plan['plan_identity'], delay['plan_identity'])
        self.assertNotEqual(plan['bundle_identity'], delay['bundle_identity'])
        for p, strategy in ((plan, 'AREA 0'), (delay, 'DELAY 1')):
            config = json.loads(p['configuration_bytes'])
            self.assertEqual(config['SYNTH_STRATEGY'], strategy)
            self.assertIs(config['SYNTH_ABC_BUFFERING'], False)
            self.assertIn('effective_parameters', p['methodology'])
            self.assertIn('snapshot', p['methodology'])
            manifest = json.loads(p['bundle_manifest'])
            # Every declaration file comes from the Project inventory used by export_trace.
            for name in ('asics/fifo_demo/project/flow_catalog.ml', 'asics/fifo_demo/project/flow_catalog.mli',
                         'asics/fifo_demo/project/flow_profiles.ml', 'asics/fifo_demo/project/flow_profiles.mli'):
                self.assertIn(name, json.dumps(manifest))
        self.assertFalse((self.root / '_flow_results').exists())
        self.assertFalse(self.log.exists())
        self.assertFalse(self.versions.exists())
        self.named_run(plan, '--json', env=dict(self.env, CONTRACT='4'))
        area_bundle = Path(self.call()['argv'][1])
        self.named_run(delay, '--flow', 'standard', '--profile', 'synth_delay', '--json',
                       env=dict(self.env, CONTRACT='4'))
        delay_bundle = Path(self.call()['argv'][1])
        generated = [p.relative_to(area_bundle) for p in area_bundle.rglob('*')
                     if p.is_file() and p.suffix in ('.v', '.sdc')]
        self.assertTrue(generated)
        self.assertTrue(any(p.suffix == '.sdc' for p in generated))
        for path in generated:
            self.assertEqual((area_bundle / path).read_bytes(), (delay_bundle / path).read_bytes(), path)

    def test_named_typed_request_and_invalid_parameters(self):
        baseline = self.preview()
        buffering = self.preview('--set', 'SYNTH_ABC_BUFFERING=true')
        self.assertIs(json.loads(buffering['configuration_bytes'])['SYNTH_ABC_BUFFERING'], True)
        self.assertNotEqual(baseline['plan_identity'], buffering['plan_identity'])
        strategy = self.preview('--set', 'SYNTH_STRATEGY=DELAY 1')
        self.assertEqual(json.loads(strategy['configuration_bytes'])['SYNTH_STRATEGY'], 'DELAY 1')
        for args in [('--set', 'SYNTH_BUFFERING=true'), ('--set', 'UNKNOWN=hello'),
                     ('--set', 'SYNTH_STRATEGY=AREA0'), ('--set', 'SYNTH_STRATEGY=area 0'),
                     ('--set', 'SYNTH_STRATEGY=AREA 0 '), ('--set', 'SYNTH_STRATEGY=true'),
                     ('--set', 'SYNTH_ABC_BUFFERING=1'), ('--set', 'SYNTH_ABC_BUFFERING="true"'),
                     ('--set', 'SYNTH_ABC_BUFFERING=True'), ('--set', 'SYNTH_ABC_BUFFERING=null'),
                     ('--set', 'SYNTH_ABC_BUFFERING=[]'), ('--set', 'SYNTH_ABC_BUFFERING'),
                     ('--set', 'SYNTH_ABC_BUFFERING=true', '--set', 'SYNTH_ABC_BUFFERING=false'),
                     ('--flow', 'standard', '--flow', 'standard')]:
            with self.subTest(args=args):
                self.invoke('flow', 'plan', '--endpoint', 'synthesis', *args, status=2)
        for args in [('--flow', 'missing'), ('--flow', 'standard', '--profile', 'missing')]:
            self.invoke('flow', 'plan', '--endpoint', 'synthesis', *args, status=1)
        self.assertFalse((self.root / '_flow_results').exists())
        self.assertFalse(self.log.exists())

    def test_named_stale_source_catalog_profile_and_endpoint_no_output(self):
        plan = self.preview()
        for args in [('--flow', 'standard', '--profile', 'synth_delay'),
                     ('--set', 'SYNTH_ABC_BUFFERING=true')]:
            self.named_run(plan, *args, status=1)
        self.invoke('flow', 'run', '--endpoint', 'floorplan', '--expected-plan-identity',
                    plan['plan_identity'], status=1)
        for name in ('README.md', 'asics/fifo_demo/project/flow_profiles.ml', 'asics/fifo_demo/project/flow_catalog.ml'):
            path = self.root / name
            before = path.read_bytes()
            path.write_bytes(before + b'\n(* source changed *)\n')
            self.named_run(plan, status=1)
            path.write_bytes(before)
        # Git-only context also belongs to the concrete bundle/plan identity.
        subprocess.check_call(['git', '-C', str(self.root), '-c', 'core.hooksPath=/dev/null',
                               '-c', 'commit.gpgsign=false', 'commit', '--allow-empty', '-m', 'new context'],
                              env=self.env, stdout=subprocess.DEVNULL)
        self.named_run(plan, status=1)
        self.assertFalse((self.root / '_flow_results').exists())
        self.assertFalse(self.log.exists())
        self.assertFalse(self.versions.exists())  # No capability query/lookup before stale rejection.

    def test_named_capability_negotiation_before_publication(self):
        plan = self.preview()
        for version in ('2', '3', '5', 'null', 'true', '"4"', '4.0'):
            self.named_run(plan, '--timeout', '3600', env=dict(self.env, CONTRACT=version), status=1)
        for capability in ('false', 'null', '1', '"true"', '{}', '[]'):
            self.named_run(plan, env=dict(self.env, CONTRACT='4', NAMEDFLOW=capability), status=1)
        for metadata in ('{}', '[]', 'null', 'garbage', '{"cli_contract":{"version":4}}',
                         '{"cli_contract":{"version":4,"version":4,"capabilities":{"namedflow1":true}}}',
                         '{"cli_contract":{"version":4,"capabilities":{"namedflow1":true,"namedflow1":true}}}'):
            self.named_run(plan, env=dict(self.env, METADATA=metadata), status=1)
        self.assertFalse((self.root / '_flow_results').exists())
        self.assertFalse(self.log.exists())

    def test_named_timeout_validation_and_runtime_identity(self):
        for values in [[], ['0'], ['-1'], ['nan'], ['inf'], ['-inf'], ['1.5'], ['oops'],
                       ['3600', '--timeout', '7200']]:
            self.invoke('flow', 'run', '--timeout', *values, status=2)
        for command in ('list', 'describe', 'plan'):
            self.invoke('flow', command, '--timeout', '3600', status=2)
        for command in ('describe', 'emit', 'preflight', 'run'):
            self.invoke(command, '--timeout', '3600', status=2)
        self.assertFalse(self.versions.exists())
        self.assertFalse((self.root / '_flow_results').exists())
        plan = self.preview()
        for budget in (None, '3600', '7200'):
            options = [] if budget is None else ['--timeout', budget]
            self.named_run(plan, *options, '--json', env=dict(self.env, CONTRACT='4'))
            argv = self.call()['argv']
            if budget is None:
                self.assertNotIn('--timeout', argv)
            else:
                self.assertEqual(argv[argv.index('--timeout') + 1], budget)
            launchspec = Path(argv[argv.index('--methodology-plan') + 1])
            self.assertEqual(json.loads(launchspec.read_text()), plan)
            self.assertEqual(self.preview(), plan)

    def test_named_public_routing_launchspec_paths_and_process(self):
        plan = self.preview()
        real = self.base / 'real provider parent'
        (real / 'child').mkdir(parents=True)
        (self.outside / 'alias').symlink_to(real / 'child', target_is_directory=True)
        provider = real / 'provider with spaces'
        shutil.copyfile(self.providers / 'hardcaml-asic-flow', provider)
        provider.chmod(0o755)
        alias = str(self.outside / 'alias/../provider with spaces')
        env = dict(self.env, CONTRACT='4', PROVIDER_EXIT='37')
        result = self.named_run(plan, '--provider', alias, '--toolchain', 'explicit tools',
                               '--support-tools', 'support tools', '--pdk-root', 'pdk root',
                               '--python', 'alias/../venv python', '--results-root', 'result store',
                               '--project-root', str(self.root), '--timeout', '3600', '--json', '--verbose',
                               cwd=self.outside, env=env, status=37)
        self.assertEqual([json.loads(line) for line in result.stdout.splitlines()],
                         [{'event': 'observation_allocated', 'recorded': True},
                          {'execution': 'complete', 'recorded': True}])
        call = self.call()
        self.assertEqual(call['executable'], alias)
        argv = call['argv']
        value = lambda flag: argv[argv.index(flag) + 1]
        self.assertEqual(argv[0], 'stages')
        self.assertEqual(value('--expected-plan-identity'), plan['plan_identity'])
        self.assertEqual(value('--timeout'), '3600')
        self.assertEqual(value('--python'), str(self.outside / 'alias/../venv python'))
        self.assertEqual(value('--support-tools'), str(self.outside / 'support tools'))
        self.assertEqual(value('--pdk-root'), str(self.outside / 'pdk root'))
        workspace = Path(value('--workspace'))
        self.assertEqual(workspace.parent, self.outside / 'result store')
        self.assertFalse(workspace.exists())
        self.assertEqual(value('--checkpoint-store'), str(workspace / 'checkpoints'))
        for flag in ('--endpoint', '--plan', '--checkpoint', '--stage', '--toolchain'):
            self.assertNotIn(flag, argv)
        launchspec = Path(value('--methodology-plan'))
        self.assertEqual(launchspec.parent, self.outside / 'result store/launchspecs')
        self.assertEqual(json.loads(launchspec.read_text()), plan)
        self.assertEqual(launchspec.stat().st_mode & 0o222, 0)
        self.assertEqual(json.loads((Path(argv[1]) / 'manifest.json').read_text()),
                         json.loads(plan['bundle_manifest']))
        self.named_run(plan, '--json', env=dict(self.env, CONTRACT='4', PROVIDER_SIGNAL=str(signal.SIGTERM)),
                       status=-signal.SIGTERM)
        self.assertNotEqual(value('--workspace'), self.call()['argv'][self.call()['argv'].index('--workspace') + 1])

    @unittest.skipUnless(os.environ.get('HARDCAML_ASIC_TEST_PROVIDER'), 'explicit installed native fixture provider')
    def test_named_installed_native_early_reference_and_request(self):
        plan = self.preview()
        tools = self.base / 'fixture tools'
        (tools / 'tt').mkdir(parents=True)
        (tools / 'pdk').mkdir()
        result = self.named_run(plan, '--provider', os.environ['HARDCAML_ASIC_TEST_PROVIDER'],
                               '--toolchain', str(tools), '--python', '/bin/false', '--timeout', '3600', '--json', status=2)
        if self.retain:
            (self.base / 'preview.json').write_text(json.dumps(plan, indent=2) + '\n')
            (self.base / 'native.stdout.jsonl').write_text(result.stdout)
            (self.base / 'native.stderr.txt').write_text(result.stderr)
            print(f'Retained native named-flow fixture: {self.base}')
        events = [json.loads(line) for line in result.stdout.splitlines()]
        self.assertGreaterEqual(len(events), 2)
        self.assertEqual(events[0]['event'], 'observation_allocated')
        # Native code owns the pending/checked snapshot and the exact request receipt.
        self.assertIn('methodology', events[0])
        self.assertEqual(events[0]['methodology']['state'], 'pending')
        self.assertIsNone(events[0]['methodology']['reference'])
        self.assertEqual(events[-1]['methodology']['state'], 'checked')
        reference = events[-1]['methodology']['reference']
        self.assertEqual(reference['attempt_id'], events[0]['stream_id'])
        self.assertEqual(reference['snapshot_path'], events[0]['methodology']['snapshot_path'])
        self.assertEqual(reference['expected_plan_identity'], plan['plan_identity'])
        self.assertEqual(reference['plan_identity'], plan['plan_identity'])
        snapshots = list((self.root / '_flow_results').rglob('methodology-plan.json'))
        self.assertEqual(len(snapshots), 1, (events, result.stderr))
        self.assertEqual(json.loads(snapshots[0].read_text()), plan)
        self.assertEqual(str(snapshots[0]), reference['snapshot_path'])
        self.assertEqual(hashlib.sha256(snapshots[0].read_bytes()).hexdigest(), reference['snapshot_sha256'])
        self.assertFalse(self.log.exists())
        receipts = list((self.root / '_flow_results').rglob('operation.json'))
        self.assertEqual(len(receipts), 1)
        receipt = json.loads(receipts[0].read_text())
        self.assertIn('request', receipt)
        self.assertIn('methodology', receipt['request'])
        self.assertEqual(receipt['request']['methodology']['plan_identity'], plan['plan_identity'])
        self.assertEqual(receipt['request']['methodology'], reference)
        self.assertEqual(receipt['request']['support_tools'], str(tools / 'tt'))
        self.assertEqual(receipt['request']['python'], '/bin/false')
        self.assertFalse(Path(receipt['request']['workspace']).exists())

    def test_executable_paths_preserve_symlink_parent_traversal(self):
        real = self.base / 'real'
        (real / 'child').mkdir(parents=True)
        (self.outside / 'alias').symlink_to(real / 'child', target_is_directory=True)
        provider_dir = real / 'providers'
        provider_dir.mkdir()
        shutil.copyfile(self.providers / 'hardcaml-asic-flow', provider_dir / 'hardcaml-asic-flow')
        (provider_dir / 'hardcaml-asic-flow').chmod(0o755)
        env = dict(self.env, PATH='alias/../providers')
        python_dir = real / 'venv'
        venv.EnvBuilder(with_pip=False, symlinks=True).create(python_dir)
        for python in ('alias/../venv/bin/python', str(self.outside / 'alias/../venv/bin/python')):
            with self.subTest(python=python):
                self.invoke('preflight', '--project-root', str(self.root), '--bundle', 'unused',
                            '--python', python, '--json', cwd=self.outside, env=env)
                call = self.call()
                intended = str(self.outside / 'alias/../venv/bin/python')
                forwarded = call['argv'][call['argv'].index('--python') + 1]
                self.assertEqual(forwarded, intended)
                self.assertEqual(call['executable'], str(self.outside / 'alias/../providers/hardcaml-asic-flow'))
                self.assertFalse((self.outside / 'venv').exists())
                self.assertTrue(os.path.samefile(Path(forwarded).parent.parent / 'pyvenv.cfg',
                                                python_dir / 'pyvenv.cfg'))
        prefix = subprocess.check_output([str(python_dir / 'bin/python'), '-c',
                                          'import sys; print(sys.prefix)'], text=True).strip()
        self.assertEqual(Path(prefix).resolve(), python_dir)
        self.assertFalse((self.root / '_flow_results').exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
