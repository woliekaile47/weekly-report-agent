import hashlib
import json
import tarfile

import pytest

from scripts import package_release


def test_release_keeps_model_instructions_with_code_and_template(tmp_path, monkeypatch):
    files = {
        'report_agent/api.py': b'# application',
        'frontend/dist/index.html': b'<html></html>',
        'frontend/dist/assets/app.js': b'// built UI',
        'templates/weekly-report.docx': b'template',
        'skills/weekly-report/SKILL.md': '自动检索公开线索'.encode(),
        '.env': b'PRIVATE_KEY=secret',
        'runtime/tasks.sqlite': b'private data',
    }
    for name, content in files.items():
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    monkeypatch.setattr(package_release, 'ROOT', tmp_path)
    package_release.main()
    with tarfile.open(tmp_path / 'runtime/releases/weekly-report.tar.gz') as archive:
        manifest = json.load(archive.extractfile('release-manifest.json'))
        assert 'skills/weekly-report/SKILL.md' in manifest
        assert '.env' not in archive.getnames()
        assert 'runtime/tasks.sqlite' not in archive.getnames()
        for name, digest in manifest.items():
            assert hashlib.sha256(archive.extractfile(name).read()).hexdigest() == digest


def test_release_refuses_to_omit_employee_instructions(tmp_path, monkeypatch):
    for name in ('frontend/dist/index.html', 'templates/weekly-report.docx'):
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b'content')
    monkeypatch.setattr(package_release, 'ROOT', tmp_path)
    with pytest.raises(SystemExit, match='SKILL.md'):
        package_release.main()
