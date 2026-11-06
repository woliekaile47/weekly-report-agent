"""Bounded, isolated Word renderer. Used for real page-count inspection, not metadata guesses."""

import asyncio
import json
import os
import signal
import sys
from pathlib import Path


async def inspect_pages(path, timeout=90):
    result_file = path.parent / "page-audit.json"
    from report_agent.config import ROOT

    env = {**os.environ, "PYTHONPATH": str(ROOT), "PYTHONUTF8": "1"}
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "report_agent.render_worker",
        str(path),
        env=env,
        start_new_session=sys.platform != "win32",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        result = (
            json.loads(stdout.decode("utf-8"))
            if proc.returncode == 0
            else {"details": "文档渲染检查失败，草稿可下载，请联系管理员检查渲染服务"}
        )
    except (asyncio.TimeoutError, ValueError):
        if sys.platform != "win32":
            os.killpg(proc.pid, signal.SIGKILL)
        else:
            proc.kill()
        await proc.communicate()
        result = {"details": "Word渲染检查超时或返回无效，已暂停等待人工检查"}
    result_file.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    return result


def render_linux(path):
    import re
    import subprocess
    import tempfile

    with tempfile.TemporaryDirectory(prefix="report-render-") as profile:
        subprocess.run(
            [
                "libreoffice",
                "-env:UserInstallation=" + Path(profile).as_uri(),
                "--headless",
                "--convert-to",
                "pdf",
                "--outdir",
                str(path.parent),
                str(path),
            ],
            check=True,
            capture_output=True,
            timeout=65,
        )
    pdf = path.with_suffix(".pdf")
    output = subprocess.run(
        ["pdfinfo", str(pdf)],
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, "LC_ALL": "C"},
        timeout=10,
    ).stdout
    pages = int(re.search(r"^Pages:\s+(\d+)", output, re.MULTILINE)[1])
    return {
        "pages": pages,
        "renderer": "LibreOffice",
        "pdf": pdf.name,
        "details": f"LibreOffice 实际排版 {pages} 页（与 Microsoft Word 可能存在差异）",
    }


def render(path):
    if sys.platform != "win32":
        return render_linux(path)
    import pythoncom
    import win32com.client

    pythoncom.CoInitialize()
    word = None
    doc = None
    try:
        word = win32com.client.DispatchEx("Word.Application")
        word.Visible = False
        word.DisplayAlerts = 0
        doc = word.Documents.Open(str(path.resolve()), ReadOnly=True, AddToRecentFiles=False, Visible=False)
        doc.Repaginate()
        pages = doc.ComputeStatistics(2)
        pdf = path.with_suffix(".pdf")
        doc.ExportAsFixedFormat(str(pdf.resolve()), 17)
        return {
            "pages": pages,
            "renderer": "Microsoft Word",
            "pdf": pdf.name,
            "details": f"Microsoft Word 实际排版 {pages} 页",
        }
    finally:
        if doc:
            doc.Close(False)
        if word:
            word.Quit()
        pythoncom.CoUninitialize()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        print(json.dumps(render(Path(sys.argv[1])), ensure_ascii=False))
    except Exception:
        if sys.platform != "win32" and os.getpgrp() == os.getpid():
            os.killpg(os.getpid(), signal.SIGKILL)
        sys.exit(1)
