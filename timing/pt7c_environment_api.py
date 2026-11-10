"""Native subprocess environment probe; no design or P&R."""
import os
from pathlib import Path
import shutil
import subprocess

path = Path(shutil.which('sta'))
print('STA', str(path), 'RESOLVED', str(path.resolve()))
if path.read_bytes()[:2] == b'#!':
    print('WRAPPER', path.read_text())
script = Path('env.tcl')
script.write_text('puts "ENV_EXISTS [info exists ::env(PT7_TEST)]"\nputs "ENV_NAMES [array names ::env]"\nexit 0\n')
result = subprocess.run(['sta', '-threads', '1', '-no_splash', '-exit', str(script)],
                        env=dict(os.environ, PT7_TEST='yes'), capture_output=True, text=True)
print('EXIT', result.returncode, 'STDOUT', result.stdout, 'STDERR', result.stderr)
print('PT7C_ENVIRONMENT_API_COMPLETE')
