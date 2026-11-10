"""Package code, built UI and Word template together; exclude runtime data and secrets."""

import hashlib
import io
import json
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    required = [ROOT / 'frontend/dist/index.html', ROOT / 'templates/weekly-report.docx',
                ROOT / 'skills/weekly-report/SKILL.md']
    if any(not path.is_file() for path in required):
        raise SystemExit('Build frontend/dist and provide the Word template and employee SKILL.md before packaging')
    files = sorted([
        *ROOT.glob('report_agent/**/*.py'),
        *(path for path in (ROOT / 'frontend/dist').rglob('*') if path.is_file()),
        ROOT / 'templates/weekly-report.docx', ROOT / 'skills/weekly-report/SKILL.md',
    ])
    manifest = {path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest() for path in files}
    output = ROOT / 'runtime/releases/weekly-report.tar.gz'
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix('.tmp')
    with tarfile.open(temporary, 'w:gz') as archive:
        for path in files:
            archive.add(path, arcname=path.relative_to(ROOT).as_posix())
        content = json.dumps(manifest, indent=2, sort_keys=True).encode()
        info = tarfile.TarInfo('release-manifest.json')
        info.size = len(content)
        archive.addfile(info, io.BytesIO(content))
    temporary.replace(output)
    print(output)


if __name__ == '__main__':
    main()
