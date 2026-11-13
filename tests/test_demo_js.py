"""발표 자료 안의 브라우저 시연(report_site/demo_core.js)이 Python 대리모델·ODE·비용·최적화와 같은 값을 내는지.

브라우저용 JS가 물리·모델을 따로 구현하므로, 같은 입력에 대해 Python(기준)과 비교해 어긋나면 실패한다.
node가 없으면 건너뛴다(시연 HTML 자체는 브라우저만 있으면 된다).
"""
import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

from optimize import DEFAULT_MODEL, Problem, optimize_layers
from optimize.problem import cost_arrays
from physics import CostParams, DesignParams, simulate
from report_site import export_demo
from surrogate import load_surrogate

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "report_site" / "demo_core.js"
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node 없음")

RUNNER = r"""
const fs = require('fs');
const LH2 = require(process.argv[2]);
const data = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
const cases = JSON.parse(fs.readFileSync(process.argv[4], 'utf8'));
const m = LH2.create(data);
const out = cases.designs.map(d => ({curve: m.predict(d).curve, ode: m.simulate(d).ratio}));
const costs = cases.costs.map(c => m.costs(c.design, c.econ, c.N, c.r365));
const opt = cases.opts.map(c => { const r = m.optimize(c.design, c.econ); return {n_opt: r.n_opt, flat: r.flat, depleted: r.depleted}; });
let err = null; try { m.predict(cases.bad); } catch (e) { err = e.name + ':' + e.message; }
console.log(JSON.stringify({out, costs, opt, err, t: m.t}));
"""


@pytest.fixture(scope="module")
def sur():
    return load_surrogate(ROOT / DEFAULT_MODEL)


@pytest.fixture(scope="module")
def run_js(tmp_path_factory, sur):
    tmp = tmp_path_factory.mktemp("demo")
    data = tmp / "data.json"
    data.write_text(json.dumps(export_demo.payload(ROOT / DEFAULT_MODEL)), encoding="utf-8")
    runner = tmp / "run.js"
    runner.write_text(RUNNER, encoding="utf-8")

    def run(cases):
        cf = tmp / "cases.json"
        cf.write_text(json.dumps(cases), encoding="utf-8")
        p = subprocess.run([NODE, str(runner), str(CORE), str(data), str(cf)], capture_output=True, text=True,
                           encoding="utf-8", timeout=120)
        assert p.returncode == 0, p.stderr
        return json.loads(p.stdout)
    return run


def _designs(sur, n=30, seed=7):
    rng = np.random.default_rng(seed)
    tr = sur.train_range
    out = [{k: getattr(DesignParams(), k) for k in tr["names"]}]
    for _ in range(n):
        d = {}
        for name, lo, hi in zip(tr["names"], tr["lo"], tr["hi"]):
            if name in ("G_sup", "Pv0", "G_out", "S"):
                d[name] = float(10 ** rng.uniform(np.log10(lo), np.log10(hi)))
            else:
                d[name] = float(rng.uniform(lo, hi))
        d["N"] = float(round(d["N"]))
        out.append(d)
    return out


ECON = {"c_layer": 10.0, "c_fixed": 50.0, "p_h2": 5.0, "life_years": 20.0, "discount": 0.05}


def test_js_matches_python(sur, run_js):
    designs = _designs(sur)
    names = sur.train_range["names"]
    X = np.array([[d[k] for k in names] for d in designs])
    py_curves = sur.predict(X)
    py_ode = np.array([simulate(DesignParams(**d))[1] for d in designs])

    cost_cases = []
    for d, r in zip(designs[:10], py_curves[:10, -1]):
        cost_cases.append({"design": d, "econ": ECON, "N": d["N"], "r365": float(r)})
    opt_cases = [{"design": designs[0], "econ": ECON},
                 {"design": designs[0], "econ": dict(ECON, p_h2=10.0)},
                 {"design": designs[0], "econ": dict(ECON, c_layer=25.0)},
                 {"design": dict(designs[0], R=2.5), "econ": ECON}]
    bad = dict(designs[0], N=200.0)
    res = run_js({"designs": designs, "costs": cost_cases, "opts": opt_cases, "bad": bad})

    js_curves = np.array([o["curve"] for o in res["out"]])
    js_ode = np.array([o["ode"] for o in res["out"]])
    np.testing.assert_allclose(res["t"], sur.t, atol=1e-9)
    # 대리모델: float32 가중치라 작은 차이만 허용
    assert np.max(np.abs(js_curves - py_curves)) < 2e-4
    # 0~1, 단조 비증가, 첫 값 1
    assert np.all(js_curves[:, 0] == 1) and np.all(np.diff(js_curves, axis=1) <= 1e-12)
    # ODE: 같은 식을 RK4로 푼 값이 LSODA와 1e-3 이내
    assert np.max(np.abs(js_ode - py_ode)) < 1e-3

    for c, js in zip(cost_cases, res["costs"]):
        prob = Problem(design=c["design"], cost=CostParams(**ECON))
        py = cost_arrays(prob, [c["N"]], [c["r365"]])
        for k in ("annual_mli", "annual_boiloff", "annual_total"):
            assert js[k] == pytest.approx(float(py[k][0]), rel=1e-9), k

    for c, js in zip(opt_cases, res["opt"]):
        prob = Problem(design=c["design"], cost=CostParams(**c["econ"]))
        py = optimize_layers(sur, prob)
        assert js["n_opt"] == py.n_opt, (c["econ"], js, py.n_opt)
        assert tuple(js["flat"]) == tuple(py.flat)
        assert js["depleted"] == [bool(x) for x in (np.asarray(py.ratio365) < export_demo.DEPLETION_TOL)]

    assert res["err"] and res["err"].startswith("RangeError") and "N" in res["err"]


def test_payload_has_no_cost_inputs_and_records_model(sur):
    p = export_demo.payload(ROOT / DEFAULT_MODEL)
    assert p["model"]["input_names"] == list(sur.train_range["names"])
    assert p["model"]["lo"] == list(sur.train_range["lo"]) and p["model"]["hi"] == list(sur.train_range["hi"])
    assert p["meta"]["name"] == Path(DEFAULT_MODEL).name and "physics" in p["meta"]
    # 경제 변수는 모델 데이터에 없다(헌법 IV): 비용은 화면에서 후처리
    assert not any(k in json.dumps(p["model"]) for k in ("p_h2", "c_layer"))
