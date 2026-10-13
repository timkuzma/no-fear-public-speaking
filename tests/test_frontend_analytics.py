import subprocess
from pathlib import Path


def test_visibility_and_owner_bound_delivery():
    result=subprocess.run(['node',str(Path(__file__).with_name('frontend_analytics.mjs'))],capture_output=True,text=True,timeout=10)
    assert result.returncode==0,result.stdout+result.stderr
