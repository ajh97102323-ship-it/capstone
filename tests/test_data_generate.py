"""데이터셋 생성 파이프라인 테스트 (specs/001 T014): generate(cfg, out_dir), main(argv).

모든 출력은 tmp_path(임시 디렉터리)에 쓴다. n=300.
"""
import csv
import json

import numpy as np
import pytest

import data.generate as gen
from data.config import DEFAULT_INPUTS, GenerationConfig
from data.generate import generate, main
from data.simulate import Rejection
from physics import BoiloffModel, DesignParams

N = 300
NAMES = [s.name for s in DEFAULT_INPUTS]
NPZ_KEYS = {"X", "Y", "t", "aux", "depleted", "split", "sample_id", "input_names", "input_scales",
            "input_lo", "input_hi", "aux_names"}
FILES = ("dataset.npz", "config.json", "summary.json", "rejected.csv")


@pytest.fixture(scope="module")
def ds_dir(tmp_path_factory):
    out = tmp_path_factory.mktemp("gen")
    return generate(GenerationConfig(n_requested=N, seed=1), out)


def _load(path):
    with np.load(path / "dataset.npz", allow_pickle=False) as z:
        return {k: z[k] for k in z.files}


def _no_partial(out):
    return not any(p.name.endswith(".partial") for p in out.iterdir())


# ---------------------------------------------------------------- ① 파일

def test_files_created(ds_dir):
    assert ds_dir.name == "lhs_n300_seed1"
    for f in FILES:
        assert (ds_dir / f).is_file(), f
    assert _no_partial(ds_dir.parent)
    with open(ds_dir / "rejected.csv", newline="", encoding="utf-8") as fh:
        header = next(csv.reader(fh))
    assert header == ["sample_id", *NAMES, "reason", "detail"]


# ---------------------------------------------------------------- ② 키와 dtype

def test_npz_keys_and_no_cost(ds_dir):
    a = _load(ds_dir)
    assert set(a) == NPZ_KEYS
    for k in a:
        low = k.lower()
        for bad in ("cost", "price", "p_h2", "c_layer"):
            assert bad not in low
    n = a["X"].shape[0]
    assert a["X"].dtype == np.float64 and a["X"].shape == (n, 10)
    assert a["Y"].dtype == np.float64 and a["Y"].shape == (n, 100)
    assert a["t"].dtype == np.float64 and a["t"].shape == (100,)
    assert np.array_equal(a["t"], np.linspace(0, 365.0, 100))
    assert a["aux"].dtype == np.float64 and a["aux"].shape == (n, 5)
    assert a["depleted"].dtype == np.bool_ and a["depleted"].shape == (n,)
    assert a["split"].dtype == np.int8 and a["split"].shape == (n,)
    assert a["sample_id"].dtype == np.int64 and a["sample_id"].shape == (n,)
    assert a["input_names"].tolist() == NAMES
    assert a["input_names"].dtype.kind == "U"
    assert a["input_scales"].tolist() == [s.scale for s in DEFAULT_INPUTS]
    assert a["input_lo"].tolist() == [s.lo for s in DEFAULT_INPUTS]
    assert a["input_hi"].tolist() == [s.hi for s in DEFAULT_INPUTS]
    assert a["aux_names"].tolist() == ["Q0", "m0", "m_lost", "A_mli", "t_empty"]
    assert np.array_equal(a["depleted"], np.isfinite(a["aux"][:, 4]))
    # config.json·summary.json에도 비용 관련 키가 없다
    for f in ("config.json", "summary.json"):
        text = (ds_dir / f).read_text(encoding="utf-8").lower()
        for bad in ("cost", "price", "p_h2", "c_layer"):
            assert bad not in text, (f, bad)


# ---------------------------------------------------------------- ③ 범위와 곡선 규칙

def test_ranges_and_curve_rules(ds_dir):
    a = _load(ds_dir)
    X, Y = a["X"], a["Y"]
    for j, s in enumerate(DEFAULT_INPUTS):
        assert np.all((X[:, j] >= s.lo) & (X[:, j] <= s.hi)), s.name
    assert np.all(X[:, 0] == np.floor(X[:, 0]))
    assert np.all(Y[:, 0] == 1.0)
    assert np.all((Y >= 0) & (Y <= 1))
    assert np.all(np.diff(Y, axis=1) <= 1e-9)
    # 소진 샘플: 소진 이후 0, m_lost == m0
    t = a["t"]
    for i in np.nonzero(a["depleted"])[0]:
        assert np.all(Y[i, t > a["aux"][i, 4]] == 0.0)
        assert a["aux"][i, 2] == a["aux"][i, 1]
    assert np.all(np.diff(a["sample_id"]) > 0)


# ---------------------------------------------------------------- ④ 재현성

def test_reproducible(tmp_path):
    p1 = generate(GenerationConfig(n_requested=N, seed=1, name="repro_a"), tmp_path)
    p2 = generate(GenerationConfig(n_requested=N, seed=1, name="repro_b"), tmp_path)
    a, b = _load(p1), _load(p2)
    assert set(a) == set(b)
    for k in a:
        assert np.array_equal(a[k], b[k]), k
    p3 = generate(GenerationConfig(n_requested=N, seed=2, name="repro_c"), tmp_path)
    assert not np.array_equal(a["X"], _load(p3)["X"])


# ---------------------------------------------------------------- ⑤ 재계산 일치

def test_resimulate_matches(ds_dir):
    a = _load(ds_dir)
    cfg = json.loads((ds_dir / "config.json").read_text(encoding="utf-8"))
    names = a["input_names"].tolist()
    rows = np.random.default_rng(2026).choice(a["X"].shape[0], size=20, replace=False)
    for i in rows:
        p = DesignParams(**dict(zip(names, a["X"][i])), **cfg["fixed"])
        model = BoiloffModel(p)
        _, ratio, t_empty = model.simulate_detailed(cfg["days"], cfg["n_points"])
        assert np.max(np.abs(a["Y"][i] - ratio)) <= 1e-6, i
        expected = [model.heat_to_liquid(0.0, model.m0), model.m0, model.m0 * (1 - ratio[-1]),
                    model.tank.A_tot]
        assert np.allclose(a["aux"][i, :4], expected, rtol=1e-9, atol=0.0), i
        if np.isinf(t_empty):
            assert np.isinf(a["aux"][i, 4]), i
        else:
            assert np.isclose(a["aux"][i, 4], t_empty, rtol=1e-9, atol=0.0), i


# ---------------------------------------------------------------- ⑥ summary

def test_summary_matches_arrays(ds_dir):
    a = _load(ds_dir)
    s = json.loads((ds_dir / "summary.json").read_text(encoding="utf-8"))
    cfg = json.loads((ds_dir / "config.json").read_text(encoding="utf-8"))
    n = a["X"].shape[0]
    assert s["n_requested"] == N
    assert s["n_valid"] == n
    assert s["n_rejected"] == N - n
    assert s["split_counts"] == {name: int((a["split"] == k).sum())
                                 for k, name in enumerate(("train", "val", "test"))}
    assert s["depleted_rate"] == pytest.approx(a["depleted"].mean(), abs=0, rel=1e-12)
    for k, name in enumerate(("train", "val", "test")):
        m = a["split"] == k
        assert s["depleted_rate_by_split"][name] == pytest.approx(a["depleted"][m].mean(), rel=1e-12)
    for key in ("reject_rate", "rejected_by_reason", "elapsed_sec", "warnings"):
        assert key in s
    assert cfg["n_valid"] == n and cfg["n_requested"] == N and cfg["seed"] == 1
    assert cfg["format_version"] == 1
    assert cfg["physics"]["version"] == "0.1.0" and len(cfg["physics"]["sha256"]) == 64
    assert cfg["defaults_modified"] == []
    assert cfg["created_at"] and "T" in cfg["created_at"]


# ---------------------------------------------------------------- ⑦ 덮어쓰기 보호

def test_overwrite_protection(tmp_path, capsys):
    out = str(tmp_path)
    assert main(["--n", str(N), "--seed", "1", "--out", out, "--name", "dup"]) == 0
    target = tmp_path / "dup"
    before = {f: (target / f).read_bytes() for f in FILES}
    (target / "marker.txt").write_text("old")
    capsys.readouterr()

    assert main(["--n", str(N), "--seed", "2", "--out", out, "--name", "dup"]) == 2
    assert {f: (target / f).read_bytes() for f in FILES} == before
    assert (target / "marker.txt").exists()

    assert main(["--n", str(N), "--seed", "2", "--out", out, "--name", "dup", "--overwrite"]) == 0
    assert (target / "dataset.npz").read_bytes() != before["dataset.npz"]
    assert not (target / "marker.txt").exists()
    assert json.loads((target / "config.json").read_text(encoding="utf-8"))["seed"] == 2
    assert sorted(p.name for p in tmp_path.iterdir()) == ["dup"]   # .partial, .old가 남지 않음
    lines = capsys.readouterr().out.strip().splitlines()
    assert lines[-1].strip() == str(target)                         # 마지막 줄 = 결과 경로


# ---------------------------------------------------------------- ⑧ 중단

def test_interrupt_leaves_nothing(tmp_path, monkeypatch):
    real = gen.run_sample
    calls = {"n": 0}

    def flaky(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 50:
            raise KeyboardInterrupt
        return real(*args, **kwargs)
    monkeypatch.setattr(gen, "run_sample", flaky)
    code = main(["--n", str(N), "--seed", "1", "--out", str(tmp_path), "--name", "intr"])
    assert code == 3
    assert calls["n"] == 50
    assert list(tmp_path.iterdir()) == []


def test_failure_during_write_leaves_nothing(tmp_path, monkeypatch):
    """저장 도중 실패해도 .partial과 최종 디렉터리가 남지 않는다(FR-017)."""
    import data.io as dio

    def bad_savez(*a, **k):
        raise OSError("disk full")
    monkeypatch.setattr(dio.np, "savez", bad_savez)
    code = main(["--n", "20", "--seed", "1", "--out", str(tmp_path), "--name", "wfail"])
    assert code == 3
    assert list(tmp_path.iterdir()) == []


# ---------------------------------------------------------------- ⑨ 제외 기록과 경고

def test_rejections_recorded_and_warned(tmp_path, monkeypatch, capsys):
    real = gen.run_sample
    calls = {"n": 0}

    def sometimes_reject(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] % 50 == 1:                     # 300개 중 6개 = 2%
            return Rejection("solver_error", "fake failure")
        return real(*args, **kwargs)
    monkeypatch.setattr(gen, "run_sample", sometimes_reject)
    path = generate(GenerationConfig(n_requested=N, seed=1, name="rej"), tmp_path)
    captured = capsys.readouterr()

    s = json.loads((path / "summary.json").read_text(encoding="utf-8"))
    assert s["n_rejected"] == 6
    assert s["n_valid"] == s["n_requested"] - s["n_rejected"] == 294
    assert s["reject_rate"] == pytest.approx(0.02)
    assert s["rejected_by_reason"] == {"solver_error": 6}
    assert any(w["code"] == "REJECT_HIGH" for w in s["warnings"])
    assert "WARNING [REJECT_HIGH]" in captured.err
    assert "rejected 6 (solver_error 6)" in captured.out

    a = _load(path)
    assert a["X"].shape[0] == 294
    with open(path / "rejected.csv", newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == 6
    expected_ids = [i for i in range(N) if i % 50 == 0]
    assert [int(r["sample_id"]) for r in rows] == expected_ids
    assert set(a["sample_id"].tolist()).isdisjoint(expected_ids)
    assert all(r["reason"] == "solver_error" and r["detail"] == "fake failure" for r in rows)
    # 입력 10개가 원래 LHS 샘플 값 그대로 기록된다
    from data.sampling import sample_inputs
    lhs_seed = np.random.SeedSequence(1).spawn(3)[0]
    X_all = sample_inputs(DEFAULT_INPUTS, N, np.random.default_rng(lhs_seed))
    for r in rows:
        i = int(r["sample_id"])
        assert [float(r[n]) for n in NAMES] == X_all[i].tolist()
    assert np.array_equal(a["X"], X_all[a["sample_id"]])


def test_no_warning_without_rejections(ds_dir):
    s = json.loads((ds_dir / "summary.json").read_text(encoding="utf-8"))
    assert s["n_rejected"] == 0
    assert s["rejected_by_reason"] == {}
    assert not any(w["code"] == "REJECT_HIGH" for w in s["warnings"])


# ---------------------------------------------------------------- 설정 오류

@pytest.mark.parametrize("argv", [
    ["--n", "0"], ["--seed", "-1"], ["--name", "../evil"], ["--name", "x.partial"],
])
def test_config_error_exit_1(tmp_path, argv):
    assert main([*argv, "--out", str(tmp_path)]) == 1
    assert list(tmp_path.iterdir()) == []


# ---------------------------------------------------------------- load_dataset (T018 ②③)

def test_load_dataset_and_part(ds_dir):
    from data.io import load_dataset
    ds = load_dataset(ds_dir)
    a = _load(ds_dir)
    for k in ("X", "Y", "t", "aux", "depleted", "split", "sample_id", "input_lo", "input_hi"):
        assert np.array_equal(getattr(ds, k), a[k]), k
    assert ds.input_names == NAMES
    assert ds.input_scales == [s.scale for s in DEFAULT_INPUTS]
    assert ds.aux_names == ["Q0", "m0", "m_lost", "A_mli", "t_empty"]
    assert ds.config["name"] == "lhs_n300_seed1" and ds.summary["n_requested"] == N
    total = 0
    for k, name in enumerate(("train", "val", "test")):
        X, Y, aux = ds.part(name)
        m = a["split"] == k
        assert np.array_equal(X, a["X"][m]) and np.array_equal(Y, a["Y"][m])
        assert np.array_equal(aux, a["aux"][m])
        total += X.shape[0]
    assert total == a["X"].shape[0]
    with pytest.raises(ValueError):
        ds.part("bogus")


def test_load_dataset_rejects_partial_and_unknown_version(ds_dir, tmp_path):
    import shutil
    from data.io import load_dataset
    partial = tmp_path / "copy.partial"
    shutil.copytree(ds_dir, partial)
    with pytest.raises(ValueError):
        load_dataset(partial)
    other = tmp_path / "copy_v2"
    shutil.copytree(ds_dir, other)
    cfg = json.loads((other / "config.json").read_text(encoding="utf-8"))
    cfg["format_version"] = 2
    (other / "config.json").write_text(json.dumps(cfg), encoding="utf-8")
    with pytest.raises(ValueError):
        load_dataset(other)


def test_small_dataset_fixture(small_dataset):
    """T020: session fixture가 tmp 아래 lhs_n300_seed1 데이터셋을 만든다."""
    from data.io import load_dataset
    assert small_dataset.name == "lhs_n300_seed1"
    ds = load_dataset(small_dataset)
    assert ds.config["n_requested"] == 300 and ds.config["seed"] == 1
    assert "pytest" in str(small_dataset).lower() or "tmp" in str(small_dataset).lower()


def test_overwrite_interrupted_keeps_existing(tmp_path, monkeypatch):
    """--overwrite라도 새 데이터셋이 완성되기 전에 중단되면 기존 데이터셋이 그대로다(research R10)."""
    out = str(tmp_path)
    assert main(["--n", "30", "--seed", "1", "--out", out, "--name", "keep"]) == 0
    target = tmp_path / "keep"
    before = {f: (target / f).read_bytes() for f in FILES}

    real = gen.run_sample
    calls = {"n": 0}

    def flaky(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 10:
            raise KeyboardInterrupt
        return real(*args, **kwargs)
    monkeypatch.setattr(gen, "run_sample", flaky)
    assert main(["--n", "30", "--seed", "2", "--out", out, "--name", "keep", "--overwrite"]) == 3
    assert {f: (target / f).read_bytes() for f in FILES} == before
    assert sorted(p.name for p in tmp_path.iterdir()) == ["keep"]


def test_overwrite_write_failure_keeps_existing(tmp_path, monkeypatch):
    """--overwrite에서 저장 단계가 실패해도 기존 데이터셋이 그대로다(research R10, FR-016·017)."""
    import data.io as dio
    out = str(tmp_path)
    assert main(["--n", "20", "--seed", "1", "--out", out, "--name", "keep2"]) == 0
    target = tmp_path / "keep2"
    before = {f: (target / f).read_bytes() for f in FILES}

    def bad_savez(*a, **k):
        raise OSError("disk full")
    monkeypatch.setattr(dio.np, "savez", bad_savez)
    assert main(["--n", "20", "--seed", "2", "--out", out, "--name", "keep2", "--overwrite"]) == 3
    assert {f: (target / f).read_bytes() for f in FILES} == before
    assert sorted(p.name for p in tmp_path.iterdir()) == ["keep2"]


# ---------------------------------------------------------------- ⑨ 경고 경계

@pytest.mark.parametrize("n_reject, warned", [(3, False), (4, True)])
def test_reject_warning_boundary(tmp_path, monkeypatch, capsys, n_reject, warned):
    """300개 중 정확히 3개(1%) 제외면 경고 없음, 4개면 경고(reject_rate > 0.01)."""
    real = gen.run_sample
    calls = {"n": 0}

    def reject_first_k(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] <= n_reject:
            return Rejection("solver_error", "fake")
        return real(*args, **kwargs)
    monkeypatch.setattr(gen, "run_sample", reject_first_k)
    path = generate(GenerationConfig(n_requested=N, seed=1, name=f"b{n_reject}"), tmp_path)
    err = capsys.readouterr().err
    s = json.loads((path / "summary.json").read_text(encoding="utf-8"))
    assert s["n_rejected"] == n_reject
    assert any(w["code"] == "REJECT_HIGH" for w in s["warnings"]) is warned
    assert ("WARNING [REJECT_HIGH]" in err) is warned


# ---------------------------------------------------------------- ⑩ 기록 정확성

def test_config_records_fingerprint_time_and_split_seed(ds_dir):
    from datetime import datetime
    from data.split import split_labels
    from data.versioning import physics_fingerprint
    cfg = json.loads((ds_dir / "config.json").read_text(encoding="utf-8"))
    assert cfg["physics"] == physics_fingerprint()
    assert datetime.fromisoformat(cfg["created_at"]).tzinfo is not None
    a = _load(ds_dir)
    n_valid = a["X"].shape[0]
    ss = np.random.SeedSequence(cfg["seed"]).spawn(3)
    expected = split_labels(n_valid, tuple(cfg["split"]), np.random.default_rng(ss[1]))
    assert np.array_equal(a["split"], expected)
    # LHS 시드(spawn[0])로 분할했다면 달라야 한다(서로 다른 spawn을 씀)
    wrong = split_labels(n_valid, tuple(cfg["split"]), np.random.default_rng(ss[0]))
    assert not np.array_equal(a["split"], wrong)


# ---------------------------------------------------------------- ⑪ 이름 대소문자

@pytest.mark.parametrize("name", ["foo.PARTIAL", "bar.Old", "x.Partial", "y.OLD"])
def test_reserved_suffix_case_insensitive_rejected(tmp_path, name):
    assert main(["--n", "10", "--out", str(tmp_path), "--name", name]) == 1
    assert list(tmp_path.iterdir()) == []


def test_existing_uppercase_partial_dir_preserved(tmp_path):
    keep = tmp_path / "foo.PARTIAL"
    keep.mkdir()
    (keep / "important.txt").write_text("user data", encoding="utf-8")
    main(["--n", "10", "--seed", "1", "--out", str(tmp_path), "--name", "foo"])
    assert keep.is_dir()
    assert (keep / "important.txt").read_text(encoding="utf-8") == "user data"
    assert {p.name for p in tmp_path.iterdir()} <= {"foo.PARTIAL", "foo"}


def test_existing_uppercase_old_dir_preserved_on_overwrite(tmp_path):
    out = str(tmp_path)
    assert main(["--n", "10", "--seed", "1", "--out", out, "--name", "foo"]) == 0
    keep = tmp_path / "foo.OLD"
    keep.mkdir()
    (keep / "important.txt").write_text("user data", encoding="utf-8")
    main(["--n", "10", "--seed", "2", "--out", out, "--name", "foo", "--overwrite"])
    assert (keep / "important.txt").read_text(encoding="utf-8") == "user data"
    assert (tmp_path / "foo" / "dataset.npz").is_file()


def test_load_dataset_rejects_partial_any_case(ds_dir, tmp_path):
    import shutil
    from data.io import load_dataset
    for nm in ("x.Partial", "y.PARTIAL"):
        d = tmp_path / nm
        shutil.copytree(ds_dir, d)
        with pytest.raises(ValueError):
            load_dataset(d)


# ---------------------------------------------------------------- ⑫ --help

def test_help_returns_zero(capsys):
    assert main(["--help"]) == 0
    assert "--overwrite" in capsys.readouterr().out
