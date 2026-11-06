#!/usr/bin/env python3
"""Fail before build/sync if an interrupted clone left empty module worktrees."""
from pathlib import Path
import subprocess
root=Path(__file__).resolve().parents[1]
markers={'NewProject/InterOp':'README.md','NewProject/fate':'README.md','NewProject/kuscia':'go.mod','NewProject/secretflow':'bfia/run_all_tests.sh','NewProject/secretpad':'pom.xml','NewProject/secretpad-frontend':'package.json','NewProject/secretpad-kimi-upstream':'pom.xml','NewProject/spu':'README.md','NewProject/yacl':'WORKSPACE','PaddleDTX':'README.md'}
for module,marker in markers.items():
    expected=subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD:'+module]).decode().strip()
    actual=subprocess.check_output(['git','-C',str(root/module),'rev-parse','HEAD']).decode().strip()
    if actual!=expected or not (root/module/marker).is_file():
        raise SystemExit('Incomplete or mismatched source module: '+module)
print('All 10 source modules match the pinned commits and contain their required files')
