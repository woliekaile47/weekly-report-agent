"""Optional Windows QA: render an application-generated Word via installed Microsoft Word.

Requires Microsoft Word, pywin32 and PyMuPDF; output remains local under runtime/qa.
"""

import argparse
from pathlib import Path

import pymupdf
import win32com.client

parser = argparse.ArgumentParser()
parser.add_argument("report", type=Path)
parser.add_argument("--output", type=Path, default=Path("runtime/qa"))
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=True)
pdf = (args.output / "report.pdf").resolve()
word = win32com.client.DispatchEx("Word.Application")
word.Visible = False
word.DisplayAlerts = 0
document = None
try:
    document = word.Documents.Open(str(args.report.resolve()), ReadOnly=True, AddToRecentFiles=False)
    document.ExportAsFixedFormat(str(pdf), 17)
finally:
    if document is not None:
        document.Close(False)
    word.Quit()
with pymupdf.open(pdf) as rendered:
    for index, page in enumerate(rendered):
        page.get_pixmap(matrix=pymupdf.Matrix(1.25, 1.25)).save(args.output / f"page-{index + 1}.png")
    print(f"Rendered {len(rendered)} pages to {args.output.resolve()}")
