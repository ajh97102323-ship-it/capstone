"""정적 결과 보고서 HTML(GitHub Pages용) 생성 테스트."""
import json
import re

from report_site import build

REPORT = "reports/opt_vol30"
VALIDATE = "reports/opt_validate_mlp_lhs_n500_seed42_seed0_tuned"
MODEL = "models/mlp_lhs_n500_seed42_seed0_tuned"


def _data(html):
    m = re.search(r'<script id="data" type="application/json">(.*?)</script>', html, re.S)
    assert m
    return json.loads(m.group(1))


def test_build_writes_self_contained_page(tmp_path):
    out = build.main(["--out", str(tmp_path), "--report", REPORT, "--validate", VALIDATE, "--model", MODEL])
    assert out == 0
    html = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert "<title>" in html and "Malgun Gothic" in html
    # 외부 스크립트는 버전 고정된 CDN 하나만
    srcs = re.findall(r'<script[^>]*src="([^"]+)"', html)
    assert srcs and all(s.startswith("https://cdn.jsdelivr.net/npm/chart.js@4.") for s in srcs)
    d = _data(html)
    src = json.loads(open(f"{REPORT}/results.json", encoding="utf-8").read())
    assert d["layers"]["n_opt"] == src["layers"]["n_opt"]
    assert d["verification"]["n_ode"] == src["verification"]["n_ode"]
    assert len(d["validate"]["designs"]) == 20
    assert d["model"]["test_r2"] > 0
    for chart_id in ["chart-cost", "chart-curves", "chart-sens-p", "chart-sens-c", "chart-pareto", "chart-ld"]:
        assert f'id="{chart_id}"' in html
    # SC 미달을 숨기지 않는다
    assert "미달" in html
    # 데이터에 NaN/Infinity 문자열이 없어야 JSON.parse가 된다
    assert "NaN" not in re.search(r'<script id="data".*?</script>', html, re.S).group(0)


def test_missing_input_returns_1(tmp_path):
    assert build.main(["--out", str(tmp_path), "--report", str(tmp_path / "none")]) == 1
