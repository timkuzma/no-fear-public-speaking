"""Parse ESM modules explicitly; Node's automatic .js detection can skip --check."""
import subprocess
from pathlib import Path


def test_maintained_frontend_modules_parse_as_es_modules():
    root=Path(__file__).resolve().parents[1]
    modules=sorted((root/'public').glob('*.js'))
    assert modules
    script='import {readFileSync} from "node:fs"; import {SourceTextModule} from "node:vm"; for(const path of process.argv.slice(1)) new SourceTextModule(readFileSync(path,"utf8"),{identifier:path});'
    result=subprocess.run(['node','--experimental-vm-modules','--input-type=module','-e',script,*map(str,modules)],capture_output=True,text=True,timeout=15)
    assert result.returncode==0,result.stdout+result.stderr
