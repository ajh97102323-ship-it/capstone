"""optimize·surrogate 결과 JSON을 모아 정적 HTML 한 장(docs/index.html)을 만든다.

입력을 바꿀 수 없는 결과 보고서다(대화형 앱은 app/main.py). 그래프는 Chart.js(버전 고정 CDN)로 그리며
데이터는 페이지 안에 JSON으로 넣는다. 물리 계산은 하지 않고 이미 ODE로 재검증된 결과만 보여 준다.

    python -m report_site.build [--out docs] [--report reports/opt_vol30]
        [--validate reports/opt_validate_<모델>] [--model models/<모델>]
"""
import argparse
import json
import math
import sys
from datetime import date
from pathlib import Path

from optimize import DEFAULT_MODEL

ROOT = Path(__file__).resolve().parents[1]
MODEL_NAME = Path(DEFAULT_MODEL).name
DEFAULTS = {
    "report": "reports/opt_vol30",
    "validate": f"reports/opt_validate_{MODEL_NAME}",
    "model": DEFAULT_MODEL,
}
CHART_JS = "https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"
CURVE_N = (20, 40, 100)  # 최적 N과 함께 보여 줄 잔량 곡선


def _clean(x):
    """NaN/inf → None (JSON.parse 가능하게)."""
    if isinstance(x, float):
        return x if math.isfinite(x) else None
    if isinstance(x, dict):
        return {k: _clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_clean(v) for v in x]
    return x


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def collect(report_dir: Path, validate_dir: Path, model_dir: Path) -> dict:
    r = _load(report_dir / "results.json")
    v = _load(validate_dir / "results.json")
    meta = _load(model_dir / "meta.json")
    metrics = _load(model_dir / "report" / "metrics.json")
    L, ver = r["layers"], r["verification"]
    Ns = L["N"]
    show = sorted({n for n in (*CURVE_N, L["n_opt"]) if n is not None and n in Ns})
    curves = {str(n): L["curves"][Ns.index(n)] for n in show}

    vol = r.get("volume")
    vol_out = None
    if vol:
        best = [min((t for t in row if t is not None), default=None) for row in vol["total"]]
        vol_out = {k: vol[k] for k in ("V", "D_max", "LD", "R", "ld_feasible", "ld_opt", "n_opt", "total_opt", "R_opt")}
        vol_out["best_total"] = best

    return _clean({
        "built": date.today().isoformat(),
        "design": r["problem"]["design"],
        "cost": r["problem"]["cost"],
        "layers": {k: L[k] for k in ("N", "annual_mli", "annual_boiloff", "annual_total", "feasible", "n_opt",
                                     "total_opt", "flat", "warnings", "t", "elapsed_s")} | {"curves": curves},
        "verification": {k: ver[k] for k in ("candidates", "candidate_totals_ode", "n_recommended", "n_ode",
                                             "total_ode", "total_ode_at_sur", "rel_cost_err", "dN", "n_analytic")}
        | {"scan": ver["scan"]},
        "sensitivity": r["sensitivity"],
        "pareto": r["pareto"],
        "volume": vol_out,
        "validate": {"summary": v["summary"], "designs": [
            {k: d[k] for k in ("m0", "n_sur", "n_ode", "n_recommended", "n_analytic", "dN", "rel_cost_err", "elapsed_s")}
            for d in v["designs"]]},
        "model": {"name": meta["name"], "dataset": meta["dataset"]["name"], "hidden": meta["training"]["hidden"],
                  "test_r2": metrics["test_r2"], "ratio365_mae": metrics["ratio365_mae"],
                  "ratio365_max": metrics["ratio365_max"], "speedup": metrics["speedup"],
                  "n_test": metrics["n_test"], "sc_pass": metrics["sc_pass"]},
        "physics": r.get("provenance", {}).get("physics"),
    })


def render(data: dict) -> str:
    payload = json.dumps(data, ensure_ascii=False, allow_nan=False).replace("</", "<\\/")
    return TEMPLATE.replace("__CHART_JS__", CHART_JS).replace("__DATA__", payload)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m report_site.build", description="정적 결과 보고서 HTML 생성")
    ap.add_argument("--out", default="docs")
    ap.add_argument("--report", default=DEFAULTS["report"], help="optimize.run 결과 디렉터리(--volume 포함 권장)")
    ap.add_argument("--validate", default=DEFAULTS["validate"], help="optimize.validate 결과 디렉터리")
    ap.add_argument("--model", default=DEFAULTS["model"], help="002 모델 디렉터리")
    a = ap.parse_args(argv)

    def p(x):
        x = Path(x)
        return x if x.is_absolute() or x.exists() else ROOT / x

    try:
        data = collect(p(a.report), p(a.validate), p(a.model))
    except (OSError, KeyError, ValueError) as e:
        print(f"ERROR 입력을 읽을 수 없음: {e}", file=sys.stderr)
        return 1
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.html").write_text(render(data), encoding="utf-8")
    (out / ".nojekyll").write_text("", encoding="utf-8")
    print(out / "index.html")
    return 0


TEMPLATE = r"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>LH2 단열 설계 결과</title>
<style>
:root {
  color-scheme: light;
  --bg: #f6f6f4; --surface: #fcfcfb; --border: #e3e2de;
  --text: #0b0b0b; --text-2: #52514e; --muted: #85837d; --grid: #ecebe7;
  --s1: #2a78d6; --s2: #eb6834; --s3: #1baf7a; --s4: #eda100;
  --warn-bg: #fff4dc; --warn: #8a5a00; --ok: #1a7f37; --bad: #b42318;
}
@media (prefers-color-scheme: dark) {
  :root:where(:not([data-theme="light"])) {
    color-scheme: dark;
    --bg: #121211; --surface: #1a1a19; --border: #2e2d2b;
    --text: #f0efec; --text-2: #c3c2b7; --muted: #8f8d86; --grid: #2a2927;
    --s1: #3987e5; --s2: #d95926; --s3: #199e70; --s4: #c98500;
    --warn-bg: #3a2e12; --warn: #f2c766; --ok: #5ccf7c; --bad: #f2867c;
  }
}
:root[data-theme="dark"] {
  color-scheme: dark;
  --bg: #121211; --surface: #1a1a19; --border: #2e2d2b;
  --text: #f0efec; --text-2: #c3c2b7; --muted: #8f8d86; --grid: #2a2927;
  --s1: #3987e5; --s2: #d95926; --s3: #199e70; --s4: #c98500;
  --warn-bg: #3a2e12; --warn: #f2c766; --ok: #5ccf7c; --bad: #f2867c;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--text);
  font-family: 'Malgun Gothic', '맑은 고딕', 'Apple SD Gothic Neo', sans-serif; line-height: 1.55; }
main { max-width: 1120px; margin: 0 auto; padding: 32px 16px 64px; }
header h1 { font-size: 28px; margin: 0 0 6px; letter-spacing: -0.01em; }
header p { margin: 0; color: var(--text-2); }
h2 { font-size: 20px; margin: 44px 0 6px; }
h2 + p.lead { margin: 0 0 16px; color: var(--text-2); }
.tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 12px; margin-top: 20px; }
.tile { background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 14px 16px; }
.tile .k { font-size: 13px; color: var(--text-2); }
.tile .v { font-size: 26px; font-weight: 700; margin-top: 2px; font-variant-numeric: tabular-nums; }
.tile .s { font-size: 12px; color: var(--muted); }
.grid2 { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 460px), 1fr)); gap: 16px; }
.card { background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 16px; min-width: 0; }
.card h3 { font-size: 15px; margin: 0 0 2px; }
.card .sub { font-size: 13px; color: var(--muted); margin: 0 0 10px; }
.chart { position: relative; height: 300px; }
.note { background: var(--warn-bg); color: var(--warn); border-radius: 8px; padding: 10px 14px; font-size: 14px; margin-top: 12px; }
table { width: 100%; border-collapse: collapse; font-size: 13px; font-variant-numeric: tabular-nums; }
th, td { padding: 6px 8px; border-bottom: 1px solid var(--border); text-align: right; white-space: nowrap; }
th { color: var(--text-2); font-weight: 600; }
th:first-child, td:first-child { text-align: left; }
.scroll { overflow-x: auto; }
.pass { color: var(--ok); font-weight: 700; } .fail { color: var(--bad); font-weight: 700; }
footer { margin-top: 48px; color: var(--muted); font-size: 12px; }
code { font-size: 12px; }
</style>
</head>
<body>
<main>
<header>
  <h1>액화수소 탱크 단열 설계: 적층 비용 ↔ 보일오프 손실</h1>
  <p>대리모델(MLP)로 찾은 최적 MLI 적층수를 물리 모델(ODE)로 재검증한 결과 보고서입니다. 값은 고정된 결과이며, 입력을 바꿔 보려면 Streamlit 앱(<code>streamlit run app/main.py</code>)을 쓰세요.</p>
  <div class="tiles" id="tiles"></div>
</header>

<h2>1. 적층수에 따른 연간 비용</h2>
<p class="lead" id="cost-lead"></p>
<div class="grid2">
  <div class="card"><h3>연간 비용 분해</h3><p class="sub">MLI 비용·보일오프 비용·총비용 [$/yr], 대리모델과 ODE</p>
    <div class="chart"><canvas id="chart-cost" role="img" aria-label="적층수별 연간 비용 그래프"></canvas></div></div>
  <div class="card"><h3>액체 잔량 곡선 (대리모델)</h3><p class="sub">적층수별 잔량비 [-], 0~365일</p>
    <div class="chart"><canvas id="chart-curves" role="img" aria-label="적층수별 잔량 곡선"></canvas></div></div>
</div>
<div class="card" style="margin-top:16px"><h3>ODE 재검증 후보</h3><p class="sub">대리모델 총비용 상위 후보를 ODE로 다시 계산</p>
  <div class="scroll"><table id="tbl-cand"></table></div></div>

<h2>2. 경제 변수 민감도</h2>
<p class="lead">수소 가격이 오르면 최적 적층수가 늘고, 적층 단가가 오르면 줄어든다. 근사식 N* ∝ √(p_H2 / (c_layer·CRF))와 비교.</p>
<div class="grid2">
  <div class="card"><h3>수소 가격 → 최적 적층수</h3><p class="sub">p_H2 [$/kg] 대 N* [layer]</p>
    <div class="chart"><canvas id="chart-sens-p" role="img" aria-label="수소 가격 민감도"></canvas></div></div>
  <div class="card"><h3>적층 단가 → 최적 적층수</h3><p class="sub">c_layer [$/(m²·layer)] 대 N* [layer]</p>
    <div class="chart"><canvas id="chart-sens-c" role="img" aria-label="적층 단가 민감도"></canvas></div></div>
</div>

<h2>3. 투자비와 손실, 탱크 형상</h2>
<p class="lead" id="shape-lead"></p>
<div class="grid2">
  <div class="card"><h3>투자비–연간 손실 질량 Pareto</h3><p class="sub">MLI 초기 투자비 [$] 대 연간 보일오프 [kg/yr]</p>
    <div class="chart"><canvas id="chart-pareto" role="img" aria-label="Pareto 그래프"></canvas></div></div>
  <div class="card"><h3>체적 고정: L/D별 최소 총비용</h3><p class="sub" id="ld-sub"></p>
    <div class="chart"><canvas id="chart-ld" role="img" aria-label="L/D별 최소 총비용"></canvas></div></div>
</div>

<h2>4. 대리모델 검증</h2>
<p class="lead" id="val-lead"></p>
<div class="tiles" id="tiles-model"></div>
<div class="note" id="sc-note"></div>
<div class="card" style="margin-top:16px"><h3>검증 설계 20개: 대리모델 최적 N vs ODE 최적 N</h3>
  <p class="sub">SC-001: |ΔN| ≤ 2, SC-002: 대리모델이 고른 N의 ODE 총비용이 최적보다 1% 미만으로 큼</p>
  <div class="scroll"><table id="tbl-val"></table></div></div>

<footer id="foot"></footer>
</main>

<script id="data" type="application/json">__DATA__</script>
<script src="__CHART_JS__"></script>
<script>
// 미리 보기 서비스(htmlpreview 등)는 외부 Chart.js를 늦게 불러오므로, 준비될 때까지 기다렸다 그린다.
(function waitForChart(tries) {
  if (window.Chart) return main();
  if (tries === 20) {  // 1초가 지나도 없으면(미리 보기 서비스가 외부 스크립트를 건너뜀) 직접 불러온다
    const s = document.createElement('script'); s.src = '__CHART_JS__'; document.head.appendChild(s);
  }
  if (tries > 200) { document.getElementById('foot').textContent = '그래프 라이브러리(Chart.js)를 불러오지 못했습니다.'; return; }
  setTimeout(() => waitForChart(tries + 1), 50);
})(0);
function main() {
const D = JSON.parse(document.getElementById('data').textContent);
const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const fmt = (x, d = 0) => x == null ? '–' : Number(x).toLocaleString('ko-KR', {minimumFractionDigits: d, maximumFractionDigits: d});
const pct = x => x == null ? '–' : (x * 100).toFixed(2) + '%';
const el = id => document.getElementById(id);
const L = D.layers, V = D.verification, M = D.model, VS = D.validate.summary;

// ---------- 요약 타일 ----------
const tile = (k, v, s) => `<div class="tile"><div class="k">${k}</div><div class="v">${v}</div><div class="s">${s || ''}</div></div>`;
el('tiles').innerHTML = [
  tile('추천 적층수 (ODE 재검증)', `${V.n_recommended} 층`, `대리모델 ${L.n_opt} · ODE 최적 ${V.n_ode} · 근사식 ${fmt(V.n_analytic, 1)}`),
  tile('연간 총비용', `$${fmt(V.total_ode)}`, '/yr, ODE 최적점'),
  tile('평평한 구간 (+1%)', `${L.flat[0]}~${L.flat[1]} 층`, '총비용이 최소의 1% 이내'),
  tile('대리모델 계산 시간', `${fmt(L.elapsed_s * 1000, 1)} ms`, `적층수 111개, ODE 대비 ${fmt(M.speedup)}배 빠름`),
].join('');
el('cost-lead').textContent = `기본 설계(R ${D.design.R} m, L/D ${D.design.LD}, 충전율 ${D.design.fill})와 기본 경제 조건(c_layer ${D.cost.c_layer} $/(m²·layer), p_H2 ${D.cost.p_h2} $/kg, 수명 ${D.cost.life_years}년, 할인율 ${D.cost.discount}). MLI 비용은 적층수에 비례해 늘고 보일오프 비용은 줄어 총비용이 U자를 그린다.`;

// ---------- 공통 차트 설정 ----------
Chart.defaults.font.family = "'Malgun Gothic', '맑은 고딕', sans-serif";
Chart.defaults.color = css('--text-2');
Chart.defaults.borderColor = css('--grid');
Object.assign(Chart.defaults.plugins.legend.labels, {boxWidth: 14, boxHeight: 3});
const base = (xTitle, yTitle, extra = {}) => ({
  responsive: true, maintainAspectRatio: false, animation: false,
  interaction: {mode: 'nearest', intersect: false, axis: 'x'},
  plugins: {legend: {position: 'top'}, tooltip: {callbacks: {}}},
  scales: {x: {type: 'linear', title: {display: true, text: xTitle}, grid: {display: false}},
           y: {title: {display: true, text: yTitle}, grid: {color: css('--grid')}}},
  ...extra,
});
const line = (label, xs, ys, color, opt = {}) => ({label, data: xs.map((x, i) => ({x, y: ys[i]})),
  borderColor: color, backgroundColor: color, borderWidth: 2, pointRadius: 0, pointHoverRadius: 4, ...opt});
const S1 = css('--s1'), S2 = css('--s2'), S3 = css('--s3'), S4 = css('--s4'), MUTED = css('--muted');

// 1. 비용 분해
const feas = L.N.map((n, i) => L.feasible[i]);
const masked = arr => arr.map((v, i) => feas[i] ? v : null);
new Chart(el('chart-cost'), {type: 'line', data: {datasets: [
  line('MLI 비용', L.N, L.annual_mli, S1),
  line('보일오프 비용', L.N, masked(L.annual_boiloff), S2),
  line('총비용 (대리모델)', L.N, masked(L.annual_total), S3),
  line('총비용 (ODE)', V.scan.N, V.scan.annual_total.map((v, i) => V.scan.depleted[i] ? null : v), MUTED, {borderDash: [5, 4]}),
]}, options: base('적층수 N [layer]', '연간 비용 [$/yr]', {plugins: {legend: {position: 'top'},
  tooltip: {callbacks: {title: it => `N = ${it[0].parsed.x}`, label: c => `${c.dataset.label}: $${fmt(c.parsed.y)}/yr`}}}})});

// 잔량 곡선
const cc = [S1, S2, S3, S4];
new Chart(el('chart-curves'), {type: 'line', data: {datasets: Object.entries(L.curves).map(([n, ys], i) =>
  line(Number(n) === L.n_opt ? `N = ${n} (최적)` : `N = ${n}`, L.t, ys, cc[i % 4], Number(n) === L.n_opt ? {borderWidth: 3} : {}))},
  options: base('시간 [day]', '잔량비 [-]', {scales: {x: {type: 'linear', max: 365, title: {display: true, text: '시간 [day]'}, grid: {display: false}},
    y: {min: 0, max: 1, title: {display: true, text: '잔량비 [-]'}}},
    plugins: {tooltip: {callbacks: {title: it => `${fmt(it[0].parsed.x)}일`, label: c => `${c.dataset.label}: ${c.parsed.y.toFixed(3)}`}}}})});

// 후보 표
el('tbl-cand').innerHTML = '<tr><th>후보 N [layer]</th><th>ODE 총비용 [$/yr]</th><th>최적 대비</th></tr>' +
  V.candidates.map((n, i) => `<tr><td>${n}${n === V.n_recommended ? ' (추천)' : ''}</td><td>${fmt(V.candidate_totals_ode[i])}</td><td>+${pct(V.candidate_totals_ode[i] / V.total_ode - 1)}</td></tr>`).join('');

// 2. 민감도
function sens(id, param, xTitle) {
  const s = D.sensitivity.find(x => x.param === param); if (!s) return;
  const odeX = [], odeY = [];
  s.values.forEach((x, i) => { if (s.n_ode[i] != null) { odeX.push(x); odeY.push(s.n_ode[i]); } });
  new Chart(el(id), {type: 'line', data: {datasets: [
    line('대리모델 최적 N', s.values, s.n_sur, S1, {pointRadius: 3}),
    line('근사식 N*', s.values, s.n_analytic, MUTED, {borderDash: [5, 4]}),
    line('ODE 최적 N', odeX, odeY, S2, {showLine: false, pointRadius: 5, pointStyle: 'rectRot'}),
  ]}, options: base(xTitle, '최적 적층수 N* [layer]', {plugins: {tooltip: {callbacks: {
    title: it => `${xTitle.split(' ')[0]} = ${it[0].parsed.x}`, label: c => `${c.dataset.label}: ${fmt(c.parsed.y, 1)}`}}}})});
}
sens('chart-sens-p', 'p_h2', 'p_H2 [$/kg]');
sens('chart-sens-c', 'c_layer', 'c_layer [$/(m²·layer)]');

// 3. Pareto
const P = D.pareto, io = P.N.indexOf(P.n_cost_opt);
new Chart(el('chart-pareto'), {type: 'scatter', data: {datasets: [
  {label: '적층수 10~120', data: P.N.map((n, i) => ({x: P.capex[i], y: P.m_lost[i], n})), borderColor: S1, backgroundColor: S1, pointRadius: 3, showLine: true, borderWidth: 2},
  {label: `총비용 최적 N = ${P.n_cost_opt}`, data: io >= 0 ? [{x: P.capex[io], y: P.m_lost[io], n: P.n_cost_opt}] : [], backgroundColor: S2, borderColor: css('--surface'), borderWidth: 2, pointRadius: 8},
]}, options: base('MLI 초기 투자비 [$]', '연간 보일오프 [kg/yr]', {interaction: {mode: 'nearest', intersect: false},
  plugins: {tooltip: {callbacks: {label: c => `N ${c.raw.n}: 투자비 $${fmt(c.parsed.x)}, 손실 ${fmt(c.parsed.y)} kg/yr`}}}})});

// 체적 고정
const VO = D.volume;
if (VO) {
  el('ld-sub').textContent = `체적 ${VO.V} m³, 최대 직경 ${VO.D_max ?? '없음'} m. 각 L/D에서 적층수를 최적화한 총비용 [$/yr]`;
  el('shape-lead').textContent = `적층수를 늘리면 투자비가 늘고 손실 질량이 준다. 체적이 정해진 탱크는 구형(L/D = 0)에 가까울수록 표면적이 작지만, 최대 직경 ${VO.D_max} m 제약 때문에 L/D ${VO.ld_opt} (반경 ${VO.R_opt.toFixed(3)} m, 적층수 ${VO.n_opt})가 선택됐다.`;
  const ok = VO.LD.map((x, i) => VO.ld_feasible[i] ? VO.best_total[i] : null);
  const firstOk = VO.LD.find((x, i) => VO.ld_feasible[i]);
  if (firstOk != null && firstOk > VO.LD[0]) el('ld-sub').textContent += ` · L/D < ${firstOk.toFixed(2)}는 직경 제약 위반으로 계산 제외`;
  new Chart(el('chart-ld'), {type: 'line', data: {datasets: [
    line('직경 제약을 만족하는 L/D', VO.LD, ok, S1),
    {label: `최적 L/D = ${VO.ld_opt}`, data: [{x: VO.ld_opt, y: VO.total_opt}], backgroundColor: S2, borderColor: css('--surface'), borderWidth: 2, pointRadius: 8, showLine: false},
  ]}, options: base('L/D [-]', '최소 총비용 [$/yr]', {plugins: {tooltip: {callbacks: {
    title: it => `L/D = ${it[0].parsed.x.toFixed(2)} (R ${VO.R[VO.LD.indexOf(it[0].parsed.x)]?.toFixed(2) ?? '-'} m)`, label: c => `${c.dataset.label}: $${fmt(c.parsed.y)}/yr`}}}})});
}

// 4. 검증
el('val-lead').textContent = `학습 데이터 ${M.dataset} (은닉층 ${M.hidden.join('×')}), 테스트 세트 ${M.n_test}개와 별도 검증 설계 ${VS.n}개(시드 ${VS.seed}, 초기 질량 ${fmt(VS.m0_range_kg[0])}~${fmt(VS.m0_range_kg[1])} kg)로 평가했다.`;
const sc = (ok) => ok ? '<span class="pass">통과</span>' : '<span class="fail">미달</span>';
el('tiles-model').innerHTML = [
  tile('테스트 R²', M.test_r2.toFixed(3), `목표 ≥ 0.99 · ${M.sc_pass['SC-001'] ? '통과' : '미달'}`),
  tile('365일 잔량비 오차', `${M.ratio365_mae.toFixed(3)}`, `평균 (최대 ${M.ratio365_max.toFixed(3)}) · 목표 0.005 / 0.03`),
  tile('최적 N ±2층 이내', `${VS.sc001_pass}/${VS.n}`, `SC-001 · ${VS.sc001 ? '통과' : '미달'}`),
  tile('총비용 오차 1% 미만', `${VS.sc002_pass}/${VS.n}`, `SC-002 · 최대 ${pct(VS.rel_cost_err_max)}`),
].join('');
el('sc-note').innerHTML = `정확도 기준은 ${sc(false)}입니다. 데이터셋을 1만 개에서 500개로 줄여 학습했기 때문입니다(1만 개 모델은 R² 0.9996). 그래서 이 보고서의 최종 값은 모두 ODE로 재검증한 값을 씁니다. 대리모델 계산 1초 이내 기준은 ${VS.sc003_pass}/${VS.n} ${sc(VS.sc003)}.`;
el('tbl-val').innerHTML = '<tr><th>#</th><th>초기 질량 m0 [kg]</th><th>대리모델 N</th><th>ODE N</th><th>ΔN</th><th>근사식 N*</th><th>총비용 오차</th><th>SC-001</th><th>SC-002</th></tr>' +
  D.validate.designs.map((d, i) => `<tr><td>${i + 1}</td><td>${fmt(d.m0)}</td><td>${d.n_sur ?? '–'}</td><td>${d.n_ode ?? '–'}</td><td>${d.dN ?? '–'}</td><td>${fmt(d.n_analytic, 1)}</td><td>${pct(d.rel_cost_err)}</td><td>${sc(d.dN != null && Math.abs(d.dN) <= 2)}</td><td>${sc(d.rel_cost_err != null && d.rel_cost_err < 0.01)}</td></tr>`).join('');

el('foot').innerHTML = `생성 ${D.built} · 물리 모델 ${D.physics ? D.physics.version + ' (' + D.physics.sha256.slice(0, 8) + ')' : '-'} · 대리모델 <code>${M.name}</code> · <code>python -m report_site.build</code>`;
}
</script>
</body>
</html>
"""

if __name__ == "__main__":
    sys.exit(main())
