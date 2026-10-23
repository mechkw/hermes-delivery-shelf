"""Real Hermes Doctor + catalog admission. No install, enable or restart."""
import os
from pathlib import Path
import sys
import tempfile

root=Path(__file__).resolve().parents[1]
source=Path(os.environ.get('HERMES_SOURCE',Path.home()/'.hermes/hermes-agent'))
sys.path.insert(0,str(source))
# Keep even the doctor's post-sandbox Desktop-copy lookup fictional.
with tempfile.TemporaryDirectory(prefix='dsc-',dir=os.environ.get('TMPDIR')) as home:
    os.environ['HERMES_HOME']=home
    from hermes_cli.plugin_dev import doctor_plugin
    from hermes_cli.plugin_validate import validate_plugin_dir
    doctor=doctor_plugin(root)
    assert not doctor.findings,doctor.findings
    assert set(doctor.registered_tools)=={'delivery_shelf_register','delivery_shelf_search'},doctor
    print('DOCTOR: 2 native tools registered; zero errors/warnings; no hooks/providers.')
    report=validate_plugin_dir(root)
    for name,passed,detail in report.checks:
        print(f'{"PASS" if passed else "FAIL"}: {name}: {detail}')
    assert all(passed for _,passed,_ in report.checks),report
    assert not report.warnings,report.warnings
    assert report.isolation is not None
    print(f'VALIDATE: {len(report.checks)} checks passed; zero warnings; isolation={report.isolation["verdict"]}.')
