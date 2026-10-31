"""Bounded, isolated Word renderer. Used for real page-count inspection, not metadata guesses."""

import asyncio
import json
import os
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
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        result = (
            json.loads(stdout.decode("utf-8"))
            if proc.returncode == 0
            else {"details": "Word页数检查失败，请检查本机Word可用性"}
        )
    except (asyncio.TimeoutError, ValueError):
        proc.kill()
        await proc.communicate()
        result = {"details": "Word渲染检查超时或返回无效，已暂停等待人工检查"}
    result_file.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    return result


def render(path):
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
        sys.exit(1)
