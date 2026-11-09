#!/usr/bin/env python3
"""Fail before build/sync if an interrupted clone left empty module worktrees."""
from pathlib import Path
import subprocess
root=Path(__file__).resolve().parents[1]
markers={'platform/InterOp':'README.md','platform/fate':'README.md','platform/kuscia':'go.mod','platform/secretflow':'bfia/run_all_tests.sh','platform/secretpad':'pom.xml','platform/secretpad-frontend':'package.json','platform/secretpad-kimi-upstream':'pom.xml','platform/spu':'README.md','platform/yacl':'WORKSPACE','PaddleDTX':'README.md'}
for module,marker in markers.items():
    expected=subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD:'+module]).decode().strip()
    actual=subprocess.check_output(['git','-C',str(root/module),'rev-parse','HEAD']).decode().strip()
    if actual!=expected or not (root/module/marker).is_file():
        raise SystemExit('Incomplete or mismatched source module: '+module)
print('All 10 source modules match the pinned commits and contain their required files')
