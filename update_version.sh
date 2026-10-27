#!/bin/sh
set -eu
cd "$(dirname "$0")"
python3 - <<'PY'
import json
from pathlib import Path
import re
match = re.search(r'^## \[(\d+\.\d+\.\d+)\]', Path('CHANGELOG.md').read_text(), re.M)
if not match:
    raise SystemExit('CHANGELOG.md needs a numeric release entry')
path = Path('version.json')
previous = json.loads(path.read_text()) if path.exists() else None
version = match[1]
if previous and tuple(map(int, version.split('.'))) < tuple(map(int, previous['version'].split('.'))):
    raise SystemExit('Release versions cannot decrease')
path.write_text(json.dumps(dict(version=version), indent=2) + '\n')
print('Dew release metadata synchronized: ' + version)
PY
