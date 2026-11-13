"""LH2 탱크 단열 설계 웹 UI (specs/004). 실행: streamlit run app/main.py

계산은 app/logic.py. 모델은 서버당 한 번 불러와 공유하고(cache_resource), 입력·저장 설계안은 세션 상태에 둔다.
"""
import math
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import altair as alt  # noqa: E402
import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from app import logic  # noqa: E402
from optimize import DEFAULT_MODEL, verify_with_ode  # noqa: E402
from physics import CostParams  # noqa: E402
from surrogate import OutOfRangeError  # noqa: E402

FONT = "Malgun Gothic"  # 화면·그래프 글꼴 (맑은 고딕)

st.set_page_config(page_title="LH2 탱크 단열 설계", layout="wide")
# 아이콘(Material Symbols span)은 건드리지 않도록 span에는 적용하지 않는다.
st.markdown(
    f"<style>html, body, .stApp, .stApp p, .stApp label, .stApp div, .stApp li, .stApp input, .stApp textarea,"
    f" .stApp button, .stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp th, .stApp td"
    f" {{font-family: '{FONT}', '맑은 고딕', sans-serif !important;}}</style>",
    unsafe_allow_html=True)
st.title("액화수소 탱크 단열 설계 대리모델")


@st.cache_resource
def get_surrogate(path: str):
    return logic.load_model(path)


def _model_path() -> str:
    p = Path(os.environ.get("LH2_MODEL", DEFAULT_MODEL))
    if not p.is_absolute() and not p.exists() and (ROOT / p).exists():
        p = ROOT / p
    return str(p)


try:
    sur = get_surrogate(_model_path())
except Exception as e:  # noqa: BLE001  모델 실패 시 ODE로 대체하지 않고 중단
    st.error(f"{e}")
    st.stop()

if "saved" not in st.session_state:
    st.session_state["saved"] = []
saved = st.session_state["saved"]


def curve_chart(curves: dict, dash: dict | None = None):
    rows = [{"t": float(ti), "y": float(yi), "설계": name} for name, (t, y) in curves.items() for ti, yi in zip(t, y)]
    return (alt.Chart(pd.DataFrame(rows)).mark_line()
            .encode(x=alt.X("t:Q", title="시간 [day]"),
                    y=alt.Y("y:Q", title="잔량비 [-]", scale=alt.Scale(domain=[0, 1])),
                    color=alt.Color("설계:N", title="설계")))


def show_chart(ch):
    st.altair_chart(ch.configure(font=FONT), width="stretch")


def fmt(x, nd=1):
    return f"{x:,.{nd}f}"


# ---------------- 사이드바: 슬라이더 + 키보드 입력(동기화) ----------------
ss = st.session_state


def _nkey(key):
    return "num_" + key.removeprefix("in_")


def _nearest(options, v):
    return min(options, key=lambda o: abs(math.log10(o) - math.log10(v)))


def _from_slider(key):
    ss[_nkey(key)] = ss[key]


def _from_number(key, options):
    v = ss[_nkey(key)]
    ss[key] = _nearest(options, v) if options else v


def dual_input(label, key, lo, hi, default, step, *, options=None, integer=False, num_fmt="%.2f"):
    """슬라이더(마우스)와 숫자 입력(키보드)을 같은 값으로 묶는다. 로그 입력은 키보드 값이 정확한 값이다."""
    nkey = _nkey(key)
    if key not in ss:
        ss[key] = default
    if nkey not in ss:
        ss[nkey] = default
    if options:
        sv = st.sidebar.select_slider(label, options=options, format_func=lambda v: f"{v:.2e}", key=key,
                                      on_change=_from_slider, args=(key,))
    elif integer:
        sv = st.sidebar.slider(label, int(lo), int(hi), step=1, key=key, on_change=_from_slider, args=(key,))
    else:
        sv = st.sidebar.slider(label, float(lo), float(hi), step=float(step), key=key,
                               on_change=_from_slider, args=(key,))
    if integer:
        nv = st.sidebar.number_input(f"{label} 직접 입력", int(lo), int(hi), step=1, key=nkey,
                                     on_change=_from_number, args=(key, None), label_visibility="collapsed")
    else:
        nv = st.sidebar.number_input(f"{label} 직접 입력", float(lo), float(hi), step=float(step), format=num_fmt,
                                     key=nkey, on_change=_from_number, args=(key, options),
                                     label_visibility="collapsed")
    if options:  # 키보드 값이 슬라이더 격자와 맞으면 정확한 키보드 값을 쓴다
        return float(nv) if _nearest(options, nv) == sv else float(sv)
    return int(sv) if integer else float(sv)


design = {}
st.sidebar.header("설계 입력")
st.sidebar.caption("슬라이더로 조정하거나 아래 칸에 값을 직접 입력하세요(Enter로 반영).")
for s in logic.input_specs(sur):
    key = f"in_{s.name}"
    if s.log:
        design[s.name] = dual_input(s.label, key, s.lo, s.hi, s.default, s.lo, options=s.options, num_fmt="%.3e")
    elif s.name == "N":
        design[s.name] = dual_input(s.label, key, s.lo, s.hi, int(s.default), 1, integer=True)
    else:
        nd = 3 if s.hi - s.lo < 1 else 2
        design[s.name] = dual_input(s.label, key, s.lo, s.hi, float(s.default), s.step, num_fmt=f"%.{nd}f")

st.sidebar.header("경제 변수 (후처리, 대리모델 입력 아님)")
cost = CostParams(
    c_layer=st.sidebar.number_input("층당 MLI 비용 c_layer [$/(m²·layer)]", min_value=0.01, value=10.0, step=1.0,
                                    key="econ_c_layer"),
    c_fixed=st.sidebar.number_input("MLI 고정비 c_fixed [$/m²]", min_value=0.0, value=50.0, step=5.0,
                                    key="econ_c_fixed"),
    p_h2=dual_input("수소 가격 p_H2 [$/kg]", "econ_p_h2", 2.0, 15.0, 5.0, 0.5),
    life_years=st.sidebar.number_input("수명 [yr]", min_value=1.0, max_value=100.0, value=20.0, step=1.0,
                                       key="econ_life"),
    discount=st.sidebar.number_input("할인율 [-]", min_value=0.0, max_value=0.2, value=0.05, step=0.01,
                                     key="econ_discount"),
)
st.sidebar.info("저장한 설계안은 이 브라우저 세션에만 있으며 새로고침하면 사라집니다.")

tab_pred, tab_cmp, tab_val, tab_opt = st.tabs(["예측", "비교", "검증", "최적화"])

# ---------------- 예측 ----------------
with tab_pred:
    t_query = st.number_input("지정 기간 t [day]", min_value=1.0, max_value=365.0, value=180.0, step=1.0,
                              key="t_query")
    try:
        sm = logic.summarize(sur, design, cost, t_query)
    except OutOfRangeError as e:
        st.error(f"입력이 학습 범위 밖: {e}")
        st.stop()
    if sm.depleted:
        st.warning(f"액체가 {sm.t_empty:.0f} day에 소진됨 — 소진 이후 손실이 잘려 보일오프 비용을 과소평가합니다.")
    show_chart(curve_chart({"현재 설계": (sm.t, sm.curve)}))
    c = st.columns(4)
    c[0].metric("초기 열유입 [W]", fmt(sm.Q0, 2), border=True)
    c[1].metric(f"{t_query:g}일 후 잔량비 [-]", f"{sm.ratio_at_query:.3f}", border=True)
    c[2].metric("일일 보일오프율 [%/day]", f"{sm.boiloff_rate:.3f}", border=True)
    c[3].metric("소진 시점 [day]", "1년 내 소진 없음" if sm.t_empty is None else fmt(sm.t_empty, 0), border=True)
    c = st.columns(3)
    c[0].metric("연간 MLI 비용 [$/yr]", fmt(sm.annual_mli), border=True)
    c[1].metric("연간 보일오프 비용 [$/yr]", fmt(sm.annual_boiloff), border=True)
    c[2].metric("연간 총비용 [$/yr]", fmt(sm.annual_total), border=True)
    name = st.text_input("설계안 이름", key="save_name")
    if st.button("설계안 저장", key="save_btn"):
        try:
            logic.add_saved(saved, name, design, sm)
            st.success(f"저장함: {name.strip()}")
        except ValueError as e:
            st.error(str(e))

# ---------------- 비교 ----------------
with tab_cmp:
    if not saved:
        st.info("저장한 설계안이 없습니다. 예측 탭에서 '설계안 저장'을 누르세요.")
    else:
        show_chart(curve_chart({s["name"]: (s["summary"].t, s["summary"].curve) for s in saved}))
        st.dataframe(pd.DataFrame(logic.compare_table(saved)), hide_index=True)
        for s in saved:
            st.button(f"삭제: {s['name']}", key=f"del_{s['name']}", on_click=logic.remove_saved,
                      args=(saved, s["name"]))
    st.caption("저장한 설계안은 이 세션에만 있으며 새로고침하면 사라집니다.")

# ---------------- 검증 ----------------
with tab_val:
    vkey = repr((sorted(design.items()), cost))
    if st.button("ODE로 검증", key="validate_btn"):
        st.session_state["validate"] = {"key": vkey, "res": logic.validate(sur, design, cost)}
    vs = st.session_state.get("validate")
    if vs and vs["key"] == vkey:
        v = vs["res"]
        show_chart(curve_chart({"AI(대리모델)": (v.t, v.curve_ai), "ODE": (v.t, v.curve_ode)}))
        c = st.columns(4)
        c[0].metric("최대 오차 [-]", f"{v.max_abs_err:.4f}")
        c[1].metric("365일 잔량비 오차 [-]", f"{v.err365:+.4f}")
        c[2].metric("보일오프 비용 차이 [$/yr]", fmt(v.cost_diff, 2))
        c[3].metric("계산 시간 AI/ODE [ms]", f"{v.ms_ai:.1f} / {v.ms_ode:.1f}")
    else:
        st.info("버튼을 누르면 현재 설계를 ODE로 다시 계산해 비교합니다.")

# ---------------- 최적화 ----------------
with tab_opt:
    residual = volume = None
    c1, c2 = st.columns(2)
    with c1:
        if st.checkbox("잔량 목표 제약", key="res_on"):
            rd = st.number_input("목표 기간 [day]", min_value=1.0, max_value=365.0, value=180.0, step=1.0,
                                 key="res_day")
            rm = st.number_input("최소 잔량비 [-]", min_value=0.0, max_value=1.0, value=0.2, step=0.05,
                                 key="res_min")
            residual = (float(rd), float(rm))
    with c2:
        if st.checkbox("체적 고정 (L/D·N 동시 최적화)", key="vol_on"):
            vv = st.number_input("체적 [m³]", min_value=1.0, value=50.0, step=5.0, key="vol_V")
            dm = st.number_input("최대 직경 [m]", min_value=0.1, value=4.0, step=0.5, key="vol_dmax")
            volume = (float(vv), float(dm))

    ov = logic.optimize_view(sur, design, cost, residual=residual, volume=volume)
    res = ov.result
    for w in ov.warnings:
        st.warning(w)
    if ov.n_opt is None:
        st.error("실행 가능한 적층수가 없습니다.")
    else:
        c = st.columns(3)
        c[0].metric("최적 N [layer]", f"{ov.n_opt}")
        c[1].metric("최적 총비용 [$/yr]", fmt(ov.total_opt))
        c[2].metric("평평한 구간(+1%) [layer]", f"{ov.flat[0]} ~ {ov.flat[1]}")
    rows = []
    for n, a, b, tt in zip(res.N, res.annual_mli, res.annual_boiloff, res.annual_total):
        rows += [{"N": int(n), "비용": float(a), "항목": "MLI 비용"}, {"N": int(n), "비용": float(b), "항목": "보일오프 비용"},
                 {"N": int(n), "비용": float(tt), "항목": "총비용"}]
    ch = alt.Chart(pd.DataFrame(rows)).mark_line().encode(
        x=alt.X("N:Q", title="적층수 N [layer]"), y=alt.Y("비용:Q", title="연간 비용 [$/yr]"),
        color=alt.Color("항목:N"))
    if ov.n_opt is not None:
        ch = ch + alt.Chart(pd.DataFrame({"N": [ov.n_opt]})).mark_rule(strokeDash=[4, 4]).encode(x="N:Q")
    show_chart(ch)
    if ov.n_opt is not None:
        i = ov.n_opt - int(res.N[0])
        show_chart(curve_chart({f"최적 N={ov.n_opt}": (res.t, res.curves[i])}))

    if ov.volume is not None:
        vr = ov.volume
        st.subheader("체적 고정 결과")
        for w in getattr(vr, "warnings", []):
            st.warning(str(w))
        if vr.n_opt is None:
            st.error("체적·직경 조건을 만족하는 설계가 없습니다.")
        else:
            st.dataframe(pd.DataFrame([{
                "최적 L/D [-]": float(vr.ld_opt), "최적 N [layer]": int(vr.n_opt), "반경 R [m]": float(vr.R_opt),
                "총비용 [$/yr]": float(vr.total_opt)}]), hide_index=True)

    okey = repr((sorted((k, v) for k, v in design.items() if k != "N"), cost, residual))
    if st.button("최적 후보 ODE 검증", key="opt_verify_btn", disabled=ov.n_opt is None):
        st.session_state["verify"] = {"key": okey, "ver": verify_with_ode(ov.problem, res)}
    vs = st.session_state.get("verify")
    if vs and vs["key"] == okey:
        ver = vs["ver"]
        c = st.columns(4)
        c[0].metric("추천 N [layer]", "-" if ver.n_recommended is None else f"{ver.n_recommended}")
        c[1].metric("ODE 최적 N [layer]", "-" if ver.n_ode is None else f"{ver.n_ode}")
        c[2].metric("근사식 N* [layer]", f"{ver.n_analytic:.1f}")
        c[3].metric("대리모델 최적 N의 ODE 총비용 상대오차 [%]",
                    "-" if ver.rel_cost_err is None else f"{ver.rel_cost_err * 100:.2f}")
