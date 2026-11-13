"""optimize/run.py CLI 테스트 (specs/003 T005, Phase 2 범위).

이 Phase에서는 report.md, results.json, cost_breakdown.png와 종료 코드까지 확인한다.
sensitivity.png·pareto.png(US2·US4)와 ld_tradeoff.png(--volume, US3)는 해당 Phase 구현 후 추가될 테스트로 남긴다.
"""
import json

import pytest

from optimize import run


@pytest.fixture(scope="session")
def tiny_model(small_dataset, tmp_path_factory):
    """001 small_dataset으로 아주 작게 학습한 002 모델 (정확도는 무관, 파이프라인 시험용)."""
    from surrogate import train
    out = tmp_path_factory.mktemp("tiny_model")
    rc = train.main(["--dataset", str(small_dataset), "--out", str(out), "--name", "tiny",
                     "--hidden", "8,8", "--max-epochs", "6", "--patience", "3", "--batch", "32", "--no-report"])
    assert rc == 0
    return out / "tiny"


def _args(model, out, *extra, name="o1"):
    return ["--model", str(model), "--out", str(out), "--name", name, *extra]


# ① 성공
def test_success_outputs_and_last_line(tiny_model, tmp_path, capsys):
    assert run.main(_args(tiny_model, tmp_path)) == 0
    out = capsys.readouterr().out
    d = tmp_path / "o1"
    for f in ("report.md", "results.json", "cost_breakdown.png"):
        assert (d / f).is_file() and (d / f).stat().st_size > 0, f
    assert not list(tmp_path.glob("*.partial"))
    assert out.strip().splitlines()[-1] == str(d)
    res = json.loads((d / "results.json").read_text(encoding="utf-8"))
    assert {"layers", "verification", "problem"} <= set(res)


def test_default_name(tiny_model, tmp_path):
    assert run.main(["--model", str(tiny_model), "--out", str(tmp_path)]) == 0
    assert (tmp_path / "opt_tiny" / "report.md").is_file()


# ② 이미 있음
def test_existing_exit_2_and_overwrite(tiny_model, tmp_path):
    assert run.main(_args(tiny_model, tmp_path)) == 0
    before = (tmp_path / "o1" / "results.json").read_bytes()
    assert run.main(_args(tiny_model, tmp_path)) == 2
    assert (tmp_path / "o1" / "results.json").read_bytes() == before
    assert run.main(_args(tiny_model, tmp_path, "--overwrite", "--p-h2", "9")) == 0
    assert (tmp_path / "o1" / "results.json").read_bytes() != before
    assert sorted(p.name for p in tmp_path.iterdir()) == ["o1"]


def test_existing_partial_exit_2(tiny_model, tmp_path):
    (tmp_path / "o1.partial").mkdir()
    assert run.main(_args(tiny_model, tmp_path)) == 2
    assert (tmp_path / "o1.partial").is_dir()


# ③ 인자 오류
@pytest.mark.parametrize("extra", [
    ["--life", "-5"], ["--life", "0"], ["--p-h2", "0"], ["--p-h2", "-1"], ["--c-layer", "0"],
    ["--c-fixed", "-1"], ["--discount", "-0.1"], ["--volume", "0"], ["--dmax", "-1"],
    ["--residual-day", "100"], ["--residual-min", "0.5"], ["--p-h2", "abc"], ["--bogus"],
])
def test_bad_args_exit_1(tiny_model, tmp_path, extra):
    assert run.main(_args(tiny_model, tmp_path, *extra)) == 1
    assert list(tmp_path.iterdir()) == []


def test_bad_name_and_missing_model_exit_1(tiny_model, tmp_path):
    assert run.main(_args(tiny_model, tmp_path, name="a b")) == 1
    assert run.main(_args(tmp_path / "없음", tmp_path)) == 1
    assert list(tmp_path.iterdir()) == []


def test_help_exit_0(capsys):
    assert run.main(["--help"]) == 0
    assert "--model" in capsys.readouterr().out


def test_discount_zero_ok(tiny_model, tmp_path):
    assert run.main(_args(tiny_model, tmp_path, "--discount", "0")) == 0


# ④ report.md 맨 위 표
def test_report_top_table(tiny_model, tmp_path):
    assert run.main(_args(tiny_model, tmp_path)) == 0
    lines = (tmp_path / "o1" / "report.md").read_text(encoding="utf-8").splitlines()
    head = "\n".join(lines[:25])
    for label in ("대리모델 최적 N", "ODE 최적 N", "근사식 N*", "총비용 [$/yr]", "연간 손실 질량 [kg/yr]"):
        assert label in head, label
    first_table = [i for i, ln in enumerate(lines) if ln.startswith("|")]
    assert first_table and first_table[0] < 12  # 표가 보고서 맨 위에 있다


def test_report_values_match_results_json(tiny_model, tmp_path):
    """표의 값이 results.json의 ODE 재검증 값과 같다 (보고 값은 ODE 값, 헌법 I)."""
    assert run.main(_args(tiny_model, tmp_path)) == 0
    res = json.loads((tmp_path / "o1" / "results.json").read_text(encoding="utf-8"))
    md = (tmp_path / "o1" / "report.md").read_text(encoding="utf-8")
    v, lay = res["verification"], res["layers"]
    if v["n_recommended"] is not None:
        assert f"{v['n_recommended']}" in md
    assert f"{v['n_analytic']:.1f}" in md
    assert res["problem"]["cost"]["p_h2"] == 5.0


def test_economics_passed_through(tiny_model, tmp_path):
    assert run.main(_args(tiny_model, tmp_path, "--p-h2", "8", "--c-layer", "12", "--c-fixed", "30",
                          "--life", "25", "--discount", "0.07")) == 0
    res = json.loads((tmp_path / "o1" / "results.json").read_text(encoding="utf-8"))
    assert res["problem"]["cost"] == {"c_layer": 12.0, "c_fixed": 30.0, "p_h2": 8.0, "life_years": 25.0,
                                      "discount": 0.07}


# 출처·설정 기록 (반려 보완)
def _check_provenance(res, md, model_name):
    from data.versioning import physics_fingerprint
    fp = physics_fingerprint()
    pv = res["provenance"]
    assert pv["physics"] == fp and {"version", "sha256"} <= set(pv["physics"])
    m = pv["model"]
    assert m["name"] == model_name and m["path"] and "dataset_physics" in m
    assert isinstance(m["physics_matches"], bool)
    assert fp["sha256"] in md and fp["version"] in md and "physics_matches" in md


def test_run_records_provenance_and_config(tiny_model, tmp_path):
    assert run.main(_args(tiny_model, tmp_path, "--p-h2", "7")) == 0
    d = tmp_path / "o1"
    res = json.loads((d / "results.json").read_text(encoding="utf-8"))
    _check_provenance(res, (d / "report.md").read_text(encoding="utf-8"), "tiny")
    assert res["problem"]["cost"]["p_h2"] == 7.0 and "R" in res["problem"]["design"]


# ⑤ 그림 (T005 나머지: US2·US3·US4 구현 후)
def test_all_figures(tiny_model, tmp_path):
    assert run.main(_args(tiny_model, tmp_path)) == 0
    d = tmp_path / "o1"
    for f in ("sensitivity.png", "pareto.png"):
        assert (d / f).is_file() and (d / f).stat().st_size > 0, f
    assert not (d / "ld_tradeoff.png").exists()
    res = json.loads((d / "results.json").read_text(encoding="utf-8"))
    assert {"sensitivity", "pareto"} <= set(res)
    assert {s["param"] for s in res["sensitivity"]} == {"p_h2", "c_layer"}


def test_volume_figure(tiny_model, tmp_path):
    assert run.main(_args(tiny_model, tmp_path, "--volume", "30", "--dmax", "3.0")) == 0
    d = tmp_path / "o1"
    assert (d / "ld_tradeoff.png").stat().st_size > 0
    res = json.loads((d / "results.json").read_text(encoding="utf-8"))
    assert res["volume"]["V"] == 30.0 and res["volume"]["D_max"] == 3.0
    assert "ld_tradeoff" in (d / "report.md").read_text(encoding="utf-8")


def test_dmax_without_volume_and_residual_pair(tiny_model, tmp_path):
    assert run.main(_args(tiny_model, tmp_path, "--dmax", "3")) == 1
    assert run.main(_args(tiny_model, tmp_path, "--residual-day", "180", "--residual-min", "0.3")) == 0
    res = json.loads((tmp_path / "o1" / "results.json").read_text(encoding="utf-8"))
    assert res["problem"]["residual"] == [180.0, 0.3]


# ---------------- validate (T013) ----------------

def test_validate_small(tiny_model, tmp_path, capsys):
    from optimize import validate
    assert validate.main(["--model", str(tiny_model), "--out", str(tmp_path), "--n", "3"]) == 0
    d = tmp_path / "opt_validate_tiny"
    assert capsys.readouterr().out.strip().splitlines()[-1] == str(d)
    res = json.loads((d / "results.json").read_text(encoding="utf-8"))
    assert len(res["designs"]) == 3 and (d / "report.md").is_file()
    for x in res["designs"]:
        for k in ("n_sur", "n_ode", "dN", "rel_cost_err", "elapsed_s", "sc001", "sc002", "sc003"):
            assert k in x, k
        assert "design" in x
        # 작은 모델은 실행 가능한 N이 없을 수 있다(dN None) -> 판정은 False
        assert x["sc001"] == (x["dN"] is not None and abs(x["dN"]) <= 2)
        assert x["sc002"] == (x["rel_cost_err"] is not None and x["rel_cost_err"] < 0.01)
        assert x["sc003"] == (x["elapsed_s"] < 1.0)
    _check_provenance(res, (d / "report.md").read_text(encoding="utf-8"), "tiny")
    assert res["config"]["seed"] == 2026 and res["config"]["cost"]["p_h2"] == 5.0
    assert {"sc001", "sc002", "sc003", "seed", "n"} <= set(res["summary"])
    assert res["summary"]["seed"] == 2026
    assert not list(tmp_path.glob("*.partial"))


def test_validate_exit_codes(tiny_model, tmp_path):
    from optimize import validate
    a = ["--model", str(tiny_model), "--out", str(tmp_path), "--n", "2"]
    assert validate.main(a) == 0
    assert validate.main(a) == 2
    assert validate.main([*a, "--overwrite"]) == 0
    assert validate.main(["--model", str(tiny_model), "--out", str(tmp_path), "--n", "0"]) == 1
    assert validate.main(["--bogus"]) == 1
    assert validate.main(["--help"]) == 0


def test_validate_reproducible_designs(tiny_model, tmp_path):
    from optimize import validate
    for o in ("a", "b"):
        assert validate.main(["--model", str(tiny_model), "--out", str(tmp_path / o), "--n", "2", "--seed", "7"]) == 0
    ra = json.loads((tmp_path / "a" / "opt_validate_tiny" / "results.json").read_text(encoding="utf-8"))
    rb = json.loads((tmp_path / "b" / "opt_validate_tiny" / "results.json").read_text(encoding="utf-8"))
    assert [x["design"] for x in ra["designs"]] == [x["design"] for x in rb["designs"]]


def test_failure_exit_3_nothing_left(tiny_model, tmp_path, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("x")
    monkeypatch.setattr("optimize.run.verify_with_ode", boom)
    assert run.main(_args(tiny_model, tmp_path)) == 3
    assert list(tmp_path.iterdir()) == []
