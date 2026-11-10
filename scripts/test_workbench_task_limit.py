"""Refresh resource-policy retention; isolated controls, no builds or EDA."""
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

import workbench_dev as dev

VARIABLE = 'HARDCAML_ASIC_SYNTHESIS_TASK_LIMIT'


class TaskLimitRetention(unittest.TestCase):
    def test_default_and_inactive_refresh_remain_inactive(self):
        args = SimpleNamespace(synthesis_task_limit=None)
        self.assertIsNone(dev.synthesis_task_limit(args, None))
        self.assertIsNone(dev.synthesis_task_limit(args, dict(environment={})))

    def test_refresh_retains_prior_six_without_repeating_flag(self):
        prior = dict(environment={VARIABLE: '6'})
        self.assertEqual(dev.synthesis_task_limit(SimpleNamespace(), prior), 6)
        self.assertEqual(dev.synthesis_task_limit(SimpleNamespace(synthesis_task_limit=None), prior), 6)
        self.assertEqual(prior, dict(environment={VARIABLE: '6'}))

    def test_explicit_six_selects_or_retains_opt_in(self):
        args = SimpleNamespace(synthesis_task_limit=6)
        for prior in (None, dict(environment={}), dict(environment={VARIABLE: '6'})):
            self.assertEqual(dev.synthesis_task_limit(args, prior), 6)

    def test_invalid_retained_policy_fails_capture_before_mutation(self):
        for value in ('', '0', '20', '06', '6 '):
            with self.subTest(value=value), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                with self.assertRaisesRegex(RuntimeError, 'invalid retained synthesis'):
                    dev.capture(SimpleNamespace(synthesis_task_limit=None), root / 'store',
                                dict(environment={VARIABLE: value}), root / 'receipt')
                self.assertEqual(list(root.iterdir()), [])

    def test_invalid_programmatic_request_cannot_drop_or_expand_policy(self):
        for value in (0, 2, 20, '6'):
            with self.subTest(value=value), self.assertRaisesRegex(RuntimeError, 'absent or 6'):
                dev.synthesis_task_limit(SimpleNamespace(synthesis_task_limit=value), dict(environment={VARIABLE: '6'}))


if __name__ == '__main__':
    unittest.main()
