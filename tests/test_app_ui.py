"""app/main.py 화면 테스트 (specs/004 T003·T005·T007·T009). streamlit AppTest, 서버는 띄우지 않는다.

모델: 동작 테스트는 ODE 래퍼(ode_sur)를 logic.load_model 자리에 넣고, 실제 불러오기 경로는 작게 학습한 모델
(LH2_MODEL)로 한 번 확인한다.
"""
import ast
import time
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from app import logic

MAIN = str(Path(__file__).resolve().parents[1] / "app" / "main.py")
TABS = ["예측", "비교", "검증", "최적화"]


def _new(monkeypatch, sur):
    monkeypatch.setenv("LH2_MODEL", "fake-ode-model")
    monkeypatch.setattr(logic, "load_model", lambda p: sur)
    at = AppTest.from_file(MAIN, default_timeout=60)
    at.run()
    return at


@pytest.fixture
def app(monkeypatch, ode_sur):
    at = _new(monkeypatch, ode_sur)
    assert not at.exception
    return at


def _metrics(block):
    return {m.label: m.value for m in block.metric}


def _num(s):
    return float(s.replace(",", "").replace("$", "").replace("+", ""))


def _find(block, part):
    hit = [v for k, v in _metrics(block).items() if part in k]
    assert hit, (part, list(_metrics(block)))
    return hit[0]


# ---------- T003 ----------
def test_runs_and_tabs(app):
    assert [t.label for t in app.tabs] == TABS


def test_sidebar_ranges_and_log_select_slider(app, ode_sur):
    tr = ode_sur.train_range
    for name, lo, hi in zip(tr["names"], tr["lo"], tr["hi"]):
        key = f"in_{name}"
        if name in ("G_sup", "Pv0", "G_out", "S"):
            ss = app.sidebar.select_slider(key=key)
            assert len(ss.options) == 61
            assert float(ss.options[0]) == pytest.approx(lo) and float(ss.options[-1]) == pytest.approx(hi)
        else:
            sl = app.sidebar.slider(key=key)
            assert (sl.min, sl.max) == (lo, hi)


def test_predict_metrics_have_units(app):
    ms = _metrics(app.tabs[0])
    assert len(ms) == 7
    assert all("[" in k and k.endswith("]") for k in ms), list(ms)


def test_n_change_lowers_boiloff_cost_within_1s(app):
    b0 = _num(_find(app.tabs[0], "보일오프 비용"))
    m0 = _num(_find(app.tabs[0], "MLI 비용"))
    app.sidebar.slider(key="in_N").set_value(90)
    t0 = time.perf_counter()
    app.run()
    assert time.perf_counter() - t0 < 1.0
    assert not app.exception
    assert _num(_find(app.tabs[0], "보일오프 비용")) < b0
    assert _num(_find(app.tabs[0], "MLI 비용")) > m0


def test_depleted_design_warns(app, ode_sur):
    app.sidebar.slider(key="in_R").set_value(0.3)
    app.sidebar.select_slider(key="in_Pv0").set_value(logic.input_specs(ode_sur)[4].options[-1])  # 0.1 Pa
    app.sidebar.slider(key="in_N").set_value(10)
    app.run()
    assert not app.exception
    assert any("과소평가" in w.value for w in app.tabs[0].warning)


def test_model_missing_shows_error_and_no_tabs(monkeypatch, tmp_path):
    bad = str(tmp_path / "없는모델")
    monkeypatch.setenv("LH2_MODEL", bad)
    at = AppTest.from_file(MAIN, default_timeout=60).run()
    assert not at.exception
    assert any(bad in e.value for e in at.error)
    assert len(at.tabs) == 0


def test_t_query_updates_metric(app):
    before = _find(app.tabs[0], "잔량비")
    app.number_input(key="t_query").set_value(30.0)
    app.run()
    after = _find(app.tabs[0], "잔량비")
    assert after != before and float(after) > float(before)


def test_real_model_loading_path(monkeypatch, small_dataset, tmp_path_factory):
    """LH2_MODEL로 지정한 (작게 학습한) 실제 모델 파일을 읽어 예외 없이 그려진다."""
    from surrogate import train
    out = tmp_path_factory.mktemp("ui_model")
    assert train.main(["--dataset", str(small_dataset), "--out", str(out), "--name", "tiny", "--hidden", "8,8",
                       "--max-epochs", "6", "--patience", "3", "--batch", "32", "--no-report"]) == 0
    monkeypatch.setenv("LH2_MODEL", str(out / "tiny"))
    at = AppTest.from_file(MAIN, default_timeout=60).run()
    assert not at.exception
    assert not any("모델을 불러올 수 없음" in e.value for e in at.error)  # 작은 모델은 최적화 불가 오류가 날 수 있음
    assert [t.label for t in at.tabs] == TABS
    assert len(_metrics(at.tabs[0])) == 7


# ---------- T005 최적화 탭 ----------
def test_optimize_tab_metrics_and_p_h2(app):
    n5 = int(_find(app.tabs[3], "최적 N"))
    app.sidebar.slider(key="econ_p_h2").set_value(10.0)
    t0 = time.perf_counter()
    app.run()
    assert time.perf_counter() - t0 < 1.0
    assert not app.exception
    n10 = int(_find(app.tabs[3], "최적 N"))
    assert n10 > n5


def test_boundary_warning_at_extreme_price(app):
    app.sidebar.number_input(key="econ_c_layer").set_value(0.01)
    app.sidebar.slider(key="econ_p_h2").set_value(15.0)
    app.run()
    assert any("BOUNDARY" in w.value for w in app.tabs[3].warning)


def test_economic_widgets_reject_nonpositive_life(app):
    assert app.sidebar.number_input(key="econ_life").min >= 1
    assert app.sidebar.number_input(key="econ_c_layer").min > 0
    assert app.sidebar.number_input(key="econ_discount").min >= 0


def test_ode_verify_button(app):
    assert not any("상대오차" in k for k in _metrics(app.tabs[3]))
    app.tabs[3].button(key="opt_verify_btn").click()
    app.run()
    assert not app.exception
    ms = _metrics(app.tabs[3])
    k = [k for k in ms if "상대오차" in k]
    assert k and "[%]" in k[0]
    float(ms[k[0]])
    # 입력이 바뀌면 지운다
    app.sidebar.slider(key="econ_p_h2").set_value(9.0)
    app.run()
    assert not any("상대오차" in k for k in _metrics(app.tabs[3]))


def test_residual_constraint_ui(app):
    """잔량 제약 체크박스 (optimize의 residual 구현 필요)."""
    app.tabs[3].checkbox(key="res_on").check()
    app.run()
    assert not app.exception
    assert app.tabs[3].number_input(key="res_min").max == 1.0


def test_volume_constraint_ui(app):
    """체적 고정 체크박스 (optimize.optimize_volume 구현 필요)."""
    app.tabs[3].checkbox(key="vol_on").check()
    app.run()
    assert not app.exception
    assert any("체적 고정 결과" in s.value for s in app.tabs[3].subheader)


# ---------- T007 검증 탭 ----------
def test_validate_tab(app):
    assert not _metrics(app.tabs[2])
    app.tabs[2].button(key="validate_btn").click()
    app.run()
    assert not app.exception
    ms = _metrics(app.tabs[2])
    assert len(ms) == 4
    assert any("최대 오차" in k for k in ms) and any("365일" in k for k in ms)
    assert any("비용 차이" in k and "[$/yr]" in k for k in ms) and any("[ms]" in k for k in ms)


# ---------- T009 비교 탭과 세션 분리 ----------
def _save(at, name):
    at.text_input(key="save_name").set_value(name)
    at.tabs[0].button(key="save_btn").click()
    at.run()
    assert not at.exception


def test_save_compare_delete(app):
    assert not app.tabs[1].dataframe
    _save(app, "A")
    app.sidebar.slider(key="in_N").set_value(80)
    app.run()
    _save(app, "B")
    assert len(app.tabs[1].dataframe[0].value) == 2
    app.tabs[1].button(key="del_A").click()
    app.run()
    df = app.tabs[1].dataframe[0].value
    assert list(df["이름"]) == ["B"]


def test_duplicate_name_error(app):
    _save(app, "A")
    _save(app, "A")
    assert any("이미" in e.value for e in app.error)
    assert len(app.tabs[1].dataframe[0].value) == 1


def test_sessions_isolated(monkeypatch, ode_sur):
    a = _new(monkeypatch, ode_sur)
    b = _new(monkeypatch, ode_sur)
    _save(a, "비밀설계")
    assert len(a.tabs[1].dataframe) == 1
    b.run()
    assert not b.tabs[1].dataframe
    assert b.session_state["saved"] == []


def test_no_global_mutable_user_state():
    root = Path(MAIN).parent
    for f in root.glob("*.py"):
        tree = ast.parse(f.read_text(encoding="utf-8"))
        for node in tree.body:
            assert not isinstance(node, ast.Global)
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                if f.name == "main.py":  # 스크립트는 세션마다 다시 실행되므로 설계 입력 dict만 허용
                    targets = [t for t in targets if getattr(t, "id", "") != "design"]
                if isinstance(node.value, (ast.List, ast.Dict, ast.Set, ast.ListComp, ast.DictComp, ast.SetComp)):
                    for t in targets:
                        name = getattr(t, "id", "")
                        assert name.lstrip("_").isupper(), f"{f.name}: 전역 가변 객체 {name}"
        assert "global " not in f.read_text(encoding="utf-8")


# ---------- UI 개선 (2026-11-13): 키보드 입력, 예측 지표 테두리, 맑은 고딕 ----------
def test_every_design_input_has_keyboard_number_input(app, ode_sur):
    tr = ode_sur.train_range
    for name, lo, hi in zip(tr["names"], tr["lo"], tr["hi"]):
        ni = app.sidebar.number_input(key=f"num_{name}")
        assert ni.min == pytest.approx(lo) and ni.max == pytest.approx(hi), name
    assert app.sidebar.number_input(key="num_econ_p_h2").min == 2.0


def test_keyboard_value_drives_prediction_and_slider(app):
    before = _num(_find(app.tabs[0], "보일오프 비용"))
    app.sidebar.number_input(key="num_N").set_value(90)
    app.run()
    assert not app.exception
    assert app.sidebar.slider(key="in_N").value == 90
    assert _num(_find(app.tabs[0], "보일오프 비용")) < before
    app.sidebar.number_input(key="num_R").set_value(1.2345)
    app.run()
    assert app.sidebar.slider(key="in_R").value == pytest.approx(1.2345)


def test_keyboard_log_input_exact_value(app, ode_sur):
    """로그 입력은 격자에 없는 값도 키보드로 정확히 넣을 수 있고, 슬라이더는 가장 가까운 격자로 따라간다."""
    app.sidebar.number_input(key="num_Pv0").set_value(0.0123)
    app.run()
    assert not app.exception
    opts = logic.input_specs(ode_sur)[4].options
    nearest = min(opts, key=lambda v: abs(__import__("math").log10(v) - __import__("math").log10(0.0123)))
    assert app.sidebar.select_slider(key="in_Pv0").value == pytest.approx(nearest)
    assert app.sidebar.number_input(key="num_Pv0").value == pytest.approx(0.0123)


def test_slider_change_updates_number_input(app):
    app.sidebar.slider(key="in_N").set_value(77)
    app.run()
    assert app.sidebar.number_input(key="num_N").value == 77


def test_prediction_metrics_have_border(app):
    ms = app.tabs[0].metric
    assert len(ms) >= 7 and all(m.proto.show_border for m in ms)


def test_malgun_gothic_font(app):
    css = " ".join(m.value for m in app.markdown)
    assert "Malgun Gothic" in css
    src = Path(MAIN).read_text(encoding="utf-8")
    assert 'font="Malgun Gothic"' in src or "FONT" in src