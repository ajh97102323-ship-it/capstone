"""surrogate/train.py CLI 테스트 (specs/002 T008, contracts/model-format.md)."""
import json
import shutil

import pytest

from data.io import load_dataset
from surrogate import load_surrogate
from surrogate import train as tr

FAST = ["--hidden", "8,8", "--max-epochs", "6", "--patience", "3", "--batch", "32"]


def _args(small_dataset, out, *extra, name="m1"):
    return ["--dataset", str(small_dataset), "--out", str(out), "--name", name, *FAST, *extra]


# ---------- ① 성공 ----------

def test_success_layout_and_last_line(small_dataset, tmp_path, capsys):
    assert tr.main(_args(small_dataset, tmp_path)) == 0
    out = capsys.readouterr().out
    d = tmp_path / "m1"
    assert (d / "model.joblib").is_file() and (d / "meta.json").is_file()
    for f in ("report.md", "metrics.json", "loss_history.png", "worst_curves.png",
              "error_by_input.png", "cost_error.png"):
        assert (d / "report" / f).is_file()
    assert not list(tmp_path.glob("*.partial"))
    assert out.strip().splitlines()[-1] == str(d)
    load_surrogate(d)  # 불러올 수 있다


def test_default_name(small_dataset, tmp_path):
    assert tr.main(["--dataset", str(small_dataset), "--out", str(tmp_path), "--seed", "3", *FAST,
                    "--no-report"]) == 0
    assert (tmp_path / f"mlp_{small_dataset.name}_seed3" / "model.joblib").is_file()


def test_no_report_flag(small_dataset, tmp_path):
    assert tr.main(_args(small_dataset, tmp_path, "--no-report")) == 0
    assert (tmp_path / "m1" / "model.joblib").is_file()
    assert not (tmp_path / "m1" / "report").exists()


# ---------- ② 이미 있음 ----------

def test_existing_name_exit_2_and_overwrite(small_dataset, tmp_path):
    assert tr.main(_args(small_dataset, tmp_path, "--no-report")) == 0
    before = (tmp_path / "m1" / "model.joblib").read_bytes()
    assert tr.main(_args(small_dataset, tmp_path, "--no-report")) == 2
    assert (tmp_path / "m1" / "model.joblib").read_bytes() == before
    assert tr.main(_args(small_dataset, tmp_path, "--overwrite", "--no-report", "--seed", "5")) == 0
    assert (tmp_path / "m1" / "model.joblib").read_bytes() != before
    assert sorted(p.name for p in tmp_path.iterdir()) == ["m1"]


def test_existing_work_dir_exit_2_and_untouched(small_dataset, tmp_path):
    (tmp_path / "m1.partial").mkdir()
    assert tr.main(_args(small_dataset, tmp_path, "--no-report")) == 2
    assert (tmp_path / "m1.partial").is_dir()


# ---------- ③ 인자 오류 ----------

@pytest.mark.parametrize("extra", [
    ["--hidden", "abc"], ["--hidden", "8,0"], ["--hidden", ""], ["--lr", "-1"], ["--lr", "0"],
    ["--batch", "0"], ["--alpha", "-1"], ["--max-epochs", "0"], ["--patience", "0"],
    ["--seed", "x"], ["--seed", "-1"], ["--bogus"],
])
def test_bad_args_exit_1(small_dataset, tmp_path, extra):
    assert tr.main(["--dataset", str(small_dataset), "--out", str(tmp_path), "--name", "m1", *extra]) == 1
    assert list(tmp_path.iterdir()) == []


def test_bad_name_and_missing_dataset_exit_1(small_dataset, tmp_path):
    assert tr.main(_args(small_dataset, tmp_path, name="a b")) == 1
    assert tr.main(_args(small_dataset, tmp_path, name="x.partial")) == 1
    assert tr.main(["--dataset", str(tmp_path / "없음"), "--out", str(tmp_path), *FAST]) == 1
    assert list(tmp_path.iterdir()) == []


def test_help_exit_0(capsys):
    assert tr.main(["--help"]) == 0
    assert "--dataset" in capsys.readouterr().out


# ---------- ④ 중단 ----------

def test_keyboard_interrupt_during_fit_exit_3_nothing_left(small_dataset, tmp_path, monkeypatch):
    def boom(self, *a, **k):
        raise KeyboardInterrupt
    monkeypatch.setattr("surrogate.model.Surrogate.fit", boom)
    assert tr.main(_args(small_dataset, tmp_path)) == 3
    assert list(tmp_path.iterdir()) == []


def test_keyboard_interrupt_during_report_exit_3_nothing_left(small_dataset, tmp_path, monkeypatch):
    def boom(*a, **k):
        raise KeyboardInterrupt
    monkeypatch.setattr("surrogate.evaluate.write_report", boom)
    assert tr.main(_args(small_dataset, tmp_path)) == 3
    assert list(tmp_path.iterdir()) == []


def test_interrupt_with_overwrite_keeps_old_model(small_dataset, tmp_path, monkeypatch):
    assert tr.main(_args(small_dataset, tmp_path, "--no-report")) == 0
    before = (tmp_path / "m1" / "model.joblib").read_bytes()

    def boom(*a, **k):
        raise KeyboardInterrupt
    monkeypatch.setattr("surrogate.evaluate.write_report", boom)
    assert tr.main(_args(small_dataset, tmp_path, "--overwrite")) == 3
    assert sorted(p.name for p in tmp_path.iterdir()) == ["m1"]
    assert (tmp_path / "m1" / "model.joblib").read_bytes() == before


def test_unexpected_error_exit_3(small_dataset, tmp_path, monkeypatch):
    def boom(self, *a, **k):
        raise RuntimeError("x")
    monkeypatch.setattr("surrogate.model.Surrogate.fit", boom)
    assert tr.main(_args(small_dataset, tmp_path)) == 3
    assert list(tmp_path.iterdir()) == []


# ---------- ⑤ meta.json ----------

def _walk_keys(o):
    if isinstance(o, dict):
        for k, v in o.items():
            yield k
            yield from _walk_keys(v)
    elif isinstance(o, list):
        for v in o:
            yield from _walk_keys(v)


def test_meta_contents(small_dataset, tmp_path):
    ds = load_dataset(small_dataset)
    assert tr.main(_args(small_dataset, tmp_path, "--seed", "7", "--lr", "0.002", "--alpha", "0.001")) == 0
    meta = json.loads((tmp_path / "m1" / "meta.json").read_text(encoding="utf-8"))
    assert meta["format_version"] == 1 and meta["name"] == "m1" and meta["created_at"]
    assert meta["dataset"]["physics"] == ds.config["physics"]
    assert meta["dataset"]["path"] == str(small_dataset)
    t = meta["training"]
    assert (t["hidden"], t["learning_rate"], t["batch_size"], t["alpha"], t["max_epochs"], t["patience"],
            t["seed"]) == ([8, 8], 0.002, 32, 0.001, 6, 3, 7)
    assert 1 <= t["best_epoch"] <= 6
    assert meta["features"]["names"] == list(ds.input_names) + ["log10_k"]
    assert meta["features"]["log_inputs"] == ["G_sup", "Pv0", "G_out", "S"]
    assert meta["features"]["Th"] == 300.0
    assert meta["train_range"]["names"] == list(ds.input_names)
    assert meta["train_range"]["lo"] == ds.input_lo.tolist() and meta["train_range"]["hi"] == ds.input_hi.tolist()
    assert meta["t_days"] == ds.t.tolist()
    assert {"python", "numpy", "sklearn"} <= set(meta["versions"])
    assert {"test_r2", "ratio365_mae", "ratio365_max", "speedup", "sc_pass"} <= set(meta["metrics"])
    banned = ("cost", "c_layer", "c_fixed", "p_h2", "price", "discount", "life")
    for k in _walk_keys(meta):
        assert not any(b in k.lower() for b in banned), k


# ---------- ⑥ 물리 지문 불일치 ----------

def test_physics_mismatch_warns(small_dataset, tmp_path, capsys):
    bad_ds = tmp_path / "ds" / small_dataset.name
    shutil.copytree(small_dataset, bad_ds)
    cfg_path = bad_ds / "config.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    cfg["physics"]["sha256"] = "0" * 64
    cfg_path.write_text(json.dumps(cfg), encoding="utf-8")

    out = tmp_path / "models"
    assert tr.main(_args(bad_ds, out, "--no-report")) == 0
    err = capsys.readouterr().err
    assert "WARNING [PHYSICS_MISMATCH]" in err
    meta = json.loads((out / "m1" / "meta.json").read_text(encoding="utf-8"))
    assert meta["dataset"]["physics"]["sha256"] == "0" * 64
    assert load_surrogate(out / "m1").physics_matches() is False


def test_no_warning_when_physics_matches(small_dataset, tmp_path, capsys):
    assert tr.main(_args(small_dataset, tmp_path, "--no-report")) == 0
    assert "PHYSICS_MISMATCH" not in capsys.readouterr().err
