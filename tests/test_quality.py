from docx import Document

from weekly_report.report import build_document, inspect
from weekly_report.store import task_path


def test_valid_source_id_in_prose_and_invalid_source_rejected(service, spec, files):
    task_id = service.create(spec, files)
    state = service.run(task_id)
    state["draft"]["summary"] += "相关经营背景见 M002。"
    path = task_path(service.settings.data_dir, task_id, "checks/report.docx")
    build_document(
        path,
        task_path(service.settings.data_dir, task_id, state["chart_file"]),
        state["spec"],
        state["metrics"],
        state["minutes"],
        state["draft"],
        1,
        "mock",
        [],
    )
    check = inspect(
        path, state["draft"], state["metrics"], state["minutes"], state["employee"]["quality"], []
    )
    assert check["passed"]
    state["draft"]["summary"] += "见 M999。"
    check = inspect(
        path, state["draft"], state["metrics"], state["minutes"], state["employee"]["quality"], []
    )
    assert not check["passed"]


def test_word_body_modified_before_qc_is_rejected(service, spec, files):
    task_id = service.create(spec, files)
    state = service.run(task_id)
    path = task_path(service.settings.data_dir, task_id, state["report_file"])
    doc = Document(path)
    for paragraph in doc.paragraphs:
        if "39,000.00" in paragraph.text:
            paragraph.text = paragraph.text.replace("39,000.00", "99,000.00")
    doc.save(path)
    check = inspect(
        path, state["draft"], state["metrics"], state["minutes"], state["employee"]["quality"], []
    )
    assert not check["passed"]
    assert not next(c["passed"] for c in check["checks"] if c["name"] == "数据一致性")
