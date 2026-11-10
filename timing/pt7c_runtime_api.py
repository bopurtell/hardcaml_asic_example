"""Read actual installed Step API; no Step execution or synthesis."""
import inspect
from pathlib import Path
import librelane
from librelane.steps.openroad import STAPrePNR, OpenSTAStep
from librelane.steps.tclstep import TclStep
from librelane.steps.step import Step
from librelane.common import Toolbox

print('LIBRELANE', librelane.__file__)
for cls, names in ((STAPrePNR, ('get_command', 'get_script_path', '_get_corner_files', 'run_corner', 'run', 'load', 'start')),
                   (TclStep, ('value_to_tcl', 'run_subprocess', '_reroute_env')), (Toolbox, ('__init__',))):
    for name in names:
        method = getattr(cls, name)
        print('API', cls.__name__, name, inspect.signature(method))
        print(inspect.getsource(method))
for cls in STAPrePNR.__mro__[1:]:
    print('MRO', cls)
    for name in ('run_corner', 'run'):
        if name in cls.__dict__:
            print('PARENT_API', cls.__name__, name)
            print(inspect.getsource(getattr(cls, name)))
print('PT7C_RUNTIME_API_COMPLETE')
print('RUN_SUBPROCESS', inspect.getsource(Step.run_subprocess))
corner = Path(STAPrePNR.get_script_path(None))
print('CORNER_SCRIPT', corner, corner.read_text())
