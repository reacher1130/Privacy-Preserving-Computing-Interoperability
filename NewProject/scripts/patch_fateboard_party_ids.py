#!/usr/bin/env python3
"""Compile the reviewed string-party-ID fix against the installed Board's libraries.

All JARs, configuration and backups stay inside the Board container. Only Board
classes are replaced; the native Flow, federation services and job data are untouched.
"""
import io
from pathlib import Path
import shlex
import shutil
import subprocess
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[2]
BOARD = ROOT / 'NewProject/fate/fate_board'
PATCH = ROOT / 'NewProject/patches/fate/board-string-party-id.patch'
CONTAINER = 'fateboard-native-e2e'
BASE = '/data/projects/fate/fateboard'
JDK = '/data/projects/fate/env/jdk/jdk-8u345'
BUILD = BASE + '/.string-party-id-build'
SOURCES = [
    'websocket/JobWebSocketController.java', 'services/JobWebSocketService.java',
    'controller/JobManagerController.java', 'services/JobDetailService.java',
    'websocket/LogWebSocketController.java', 'controller/JobDetailController.java',
]


def inside(script):
    try:
        return subprocess.check_output(['docker', 'exec', CONTAINER, 'sh', '-c', script],
                                       universal_newlines=True, stderr=subprocess.STDOUT, timeout=180)
    except subprocess.CalledProcessError as error:
        raise RuntimeError(error.output[-6000:]) from error


def main():
    with tempfile.TemporaryDirectory(prefix='ppci-board-') as temporary:
        source = Path(temporary)
        for name in SOURCES:
            relative = Path('src/main/java/org/fedai/fate/board') / name
            target = source / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(BOARD / relative), str(target))
        applied = subprocess.run(['git', 'apply', '--reverse', '--check', str(PATCH)],
                                 cwd=str(source), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if applied.returncode:
            subprocess.run(['git', 'apply', '--check', str(PATCH)], cwd=str(source), check=True)
            subprocess.run(['git', 'apply', str(PATCH)], cwd=str(source), check=True)
        archive = io.BytesIO()
        with tarfile.open(fileobj=archive, mode='w') as package:
            for file in source.rglob('*.java'):
                package.add(str(file), arcname=str(file.relative_to(source)))
        inside('mkdir -p ' + shlex.quote(BUILD))
        subprocess.run(['docker', 'exec', '-i', CONTAINER, 'tar', '-xf', '-', '-C', BUILD],
                       input=archive.getvalue(), check=True, timeout=30)
    files = ' '.join(shlex.quote('src/main/java/org/fedai/fate/board/' + name) for name in SOURCES)
    print(inside('''set -eu
export JAVA_HOME="%s"
export PATH="$JAVA_HOME/bin:$PATH"
cd "%s"
jarfile=$(readlink -f "%s/fateboard.jar")
backup="$jarfile.before-string-party-id-20261102"
if [ ! -f "$backup" ]; then umask 077; cp -p "$jarfile" "$backup"; chmod 600 "$backup"; fi
mkdir -p patched
javac -encoding UTF-8 -proc:none -source 8 -target 8 -cp "$jarfile:%s/lib/*" -d patched %s
cp -p "$jarfile" fateboard-next.jar
jar uf fateboard-next.jar -C patched org
echo 'Board compatibility classes compiled; original JAR backed up inside container.'
''' % (JDK, BUILD, BASE, BASE, files)).strip())
    signatures = inside('"%s/bin/javap" -classpath "%s/patched" '
                        'org.fedai.fate.board.websocket.JobWebSocketController' % (JDK, BUILD))
    if 'onOpen(javax.websocket.Session, java.lang.String, java.lang.String, java.lang.String)' not in signatures:
        raise RuntimeError('Compiled Board still rejects string party IDs')
    print(inside('''set -eu
export JAVA_HOME="%s"
export PATH="$JAVA_HOME/bin:$PATH"
cd "%s"
jarfile=$(readlink -f fateboard.jar)
bash service.sh stop
mv "%s/fateboard-next.jar" "$jarfile"
if ! bash service.sh start; then
  cp -p "$jarfile.before-string-party-id-20261102" "$jarfile"
  bash service.sh start
  exit 1
fi
echo 'Only Board JVM restarted with string-party-ID support.'
''' % (JDK, BASE, BUILD)).strip())


if __name__ == '__main__':
    main()
