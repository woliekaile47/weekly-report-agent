from streamlit.testing.v1 import AppTest

from weekly_report.settings import ROOT


def test_ui_sample_submission_and_rejection(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "ui"))
    monkeypatch.setenv("LLM_MODE", "mock")
    app = AppTest.from_file(ROOT / "app.py").run(timeout=20)
    assert not app.exception
    sample = next(x for x in app.checkbox if x.label == "使用项目自带的模拟样例数据")
    sample.check()
    next(x for x in app.button if x.label == "创建并执行").click().run(timeout=40)
    assert not app.exception
    assert any(x.value == "等待审核" for x in app.metric)
    next(x for x in app.text_input if x.label == "审核人").set_value("界面测试")
    next(x for x in app.radio if x.label == "审核结果").set_value("退回修改")
    next(x for x in app.text_area if x.label.startswith("修改意见")).set_value("请补充华东区原因与核实步骤。")
    next(x for x in app.button if x.label == "提交审核结果").click().run(timeout=40)
    assert not app.exception
    assert any("版本 2" in x.value for x in app.caption)
