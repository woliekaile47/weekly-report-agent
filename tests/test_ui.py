from streamlit.testing.v1 import AppTest

from weekly_report.service import EmployeeService
from weekly_report.settings import ROOT, Settings


def test_ui_upload_workflow_and_rejection(tmp_path, monkeypatch, files):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "ui"))
    app = AppTest.from_file(ROOT / "app.py").run(timeout=20)
    assert not app.exception
    assert not any("样例" in x.label for x in app.checkbox)
    assert not any(x.label == "新任务使用" for x in app.radio)
    app.date_input[0].set_value("2026-10-26")
    app.date_input[1].set_value("2026-11-01")
    next(x for x in app.button if x.label == "创建并执行").click().run(timeout=40)
    assert not app.exception
    assert any(x.value == "已暂停" for x in app.metric)
    service = EmployeeService(Settings())
    service.resume(app.session_state.task_id, files=files)
    app.run(timeout=20)
    assert any(x.value == "等待审核" for x in app.metric)
    next(x for x in app.text_input if x.label == "审核人").set_value("界面测试")
    next(x for x in app.radio if x.label == "审核结果").set_value("退回修改")
    next(x for x in app.text_area if x.label.startswith("修改意见")).set_value("请补充华东区原因与核实步骤。")
    next(x for x in app.button if x.label == "提交审核结果").click().run(timeout=40)
    assert not app.exception
    assert any("版本 2" in x.value for x in app.caption)
