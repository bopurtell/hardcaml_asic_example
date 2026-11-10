#!/usr/bin/env python3
"""Exact RTL and timing-environment byte comparison to retained original specimen."""
import argparse
import json
from pathlib import Path

from commands import ROOT, STORE, sha, write_new


def check(bundle):
    manifest = json.loads((bundle / 'manifest.json').read_text())
    assert len(manifest['synthesis_sources']) == 1
    rtl = bundle / manifest['synthesis_sources'][0]
    original_rtl = ROOT / 'acceptance/timing/synth-scalar-r3/emitted.v'
    original_sdc = ROOT / 'acceptance/timing/sta-scalar-r3/top.sdc'
    sdc = bundle / 'constraints/top.sdc'
    marker = '# Generated exact scalar timing intent'
    rtl_identical = rtl.read_bytes() == original_rtl.read_bytes()
    environment_identical = sdc.read_text().split(marker, 1)[0] == original_sdc.read_text().split(marker, 1)[0]
    result = {'bundle': str(bundle), 'bundle_identity': manifest['identity'],
              'emitted_rtl_sha256': sha(rtl), 'original_rtl_sha256': sha(original_rtl),
              'emitted_sdc_sha256': sha(sdc), 'original_sdc_sha256': sha(original_sdc),
              'rtl_identical': rtl_identical, 'environment_prefix_identical': environment_identical}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    bundle = args.bundle.resolve(strict=True)
    output = args.output.resolve()
    assert bundle.is_relative_to(STORE / 'bundles') and output.is_relative_to(STORE)
    result = check(bundle)
    write_new(output, result)
    print(json.dumps(result))
    assert result['rtl_identical'] and result['environment_prefix_identical']


if __name__ == '__main__':
    main()
