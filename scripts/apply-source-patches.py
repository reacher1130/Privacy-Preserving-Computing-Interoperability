#!/usr/bin/env python3
"""Apply reviewed FATE source changes idempotently after submodule checkout."""
from pathlib import Path
import subprocess
root=Path(__file__).resolve().parents[1]
for module,patch in [('fate_flow','flow.patch'),('fate_board','board.patch'),
                     ('fate_board','board-string-party-id.patch')]:
    repo=root/'platform/fate'/module
    file=root/'platform/patches/fate'/patch
    check=subprocess.run(['git','-C',str(repo),'apply','--reverse','--check',str(file)],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    if check.returncode==0:
        print(module+': patch already applied');continue
    subprocess.run(['git','-C',str(repo),'apply','--check',str(file)],check=True)
    subprocess.run(['git','-C',str(repo),'apply',str(file)],check=True)
    print(module+': patch applied')
