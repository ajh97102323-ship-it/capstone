"""대리모델 평가 (specs/002 T007, research R9, data-model 4절).

    python -m surrogate.evaluate MODEL_DIR     # 보고서(report/)와 meta.json의 지표를 다시 만든다

지표는 데이터셋 **테스트 세트**의 ODE 곡선과 비교해 계산한다. 곡선 R²는 모든 시점·샘플을 한 덩어리로 본다
(`1 − Σ(y−ŷ)² / Σ(y−ȳ)²`, ȳ는 전체 평균). 경제 변수는 쓰지 않는다. 다만 비용 환산 오차는 오차의 크기를 가늠하는
보고용 값이므로 기본 p_H2([$/kg])로만 계산하고 모델에는 저장하지 않는다(헌법 원칙 IV).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

from physics import CostParams, DesignParams, simulate

P_H2_REPORT = CostParams().p_h2  # 보고용 액화수소 가격 [$/kg] (기본 5)
SC_TARGETS = {"r2": 0.99, "mae": 0.005, "max": 0.03, "speedup": 100.0}
N_WORST = 12
NEAR_DEPLETION_DAYS = 10.0   # 소진 시점 ± [day]
SPEED_BATCH = 1000           # 대리모델 배치 크기 (research R9)
SPEED_ODE = 200              # ODE로 실제로 푸는 개수 (결과를 배치 크기로 환산)
COST_BINS = 4                # m0 분위 구간 수


def r2_curves(Y, P) -> float:
    """곡선 전체(모든 시점·샘플) 결정계수."""
    Y, P = np.asarray(Y, dtype=np.float64), np.asarray(P, dtype=np.float64)
    return float(1.0 - np.sum((Y - P) ** 2) / np.sum((Y - Y.mean()) ** 2))


def cost_error_usd(m0, delta, p_h2: float = P_H2_REPORT) -> np.ndarray:
    """365일 잔량비 오차 δ가 만드는 연간 보일오프 비용 환산 오차 `p_H2·m0·|δ|` [$/yr]."""
    return p_h2 * np.asarray(m0, dtype=np.float64) * np.abs(np.asarray(delta, dtype=np.float64))


def sc_pass(m: dict) -> dict:
    """SC-001~004 통과 여부. 경계값은 통과(이상/이하)다."""
    return {
        "SC-001": bool(m["test_r2"] >= SC_TARGETS["r2"]),
        "SC-002": bool(m["ratio365_mae"] <= SC_TARGETS["mae"] and m["ratio365_max"] <= SC_TARGETS["max"]),
        "SC-003": bool(m["speedup"] >= SC_TARGETS["speedup"]),
        "SC-004": bool(m["monotonic_violations"] == 0 and m["range_violations"] == 0),
    }


def _measure_speed(sur, X, ds_fixed_th: float) -> dict:
    """테스트 세트 앞 SPEED_BATCH개 배치 예측 시간과, 같은 입력 앞 SPEED_ODE개를 ODE로 푼 시간(배치 크기로 환산)."""
    n_batch = min(SPEED_BATCH, len(X))
    n_ode = min(SPEED_ODE, n_batch)
    Xb = X[:n_batch]
    sur.predict(Xb)  # 예열
    t_sur = min(_timed(lambda: sur.predict(Xb)) for _ in range(3))
    days, n_points = float(sur.t[-1]), len(sur.t)

    def run_ode():
        for x in Xb[:n_ode]:
            simulate(DesignParams(**dict(zip(sur.input_names, x)), Th=ds_fixed_th), days, n_points)

    t_ode = _timed(run_ode) * n_batch / n_ode
    return {"n_batch": n_batch, "n_ode": n_ode, "t_surrogate_s": t_sur, "t_ode_s": t_ode,
            "speedup": t_ode / t_sur}


def _timed(fn) -> float:
    t0 = time.perf_counter()
    fn()
    return time.perf_counter() - t0


def evaluate_model(sur, ds) -> dict:
    """테스트 세트 지표 (파일을 쓰지 않는다)."""
    X, Y, aux = ds.part("test")
    if len(X) == 0:
        raise ValueError("테스트 세트가 비어 있음")
    P = sur.predict(X)
    err = np.abs(Y[:, -1] - P[:, -1])
    names = list(ds.aux_names)
    m0 = aux[:, names.index("m0")]
    t_empty = aux[:, names.index("t_empty")]

    near = []
    for i in np.nonzero(np.isfinite(t_empty))[0]:
        sel = np.abs(ds.t - t_empty[i]) <= NEAR_DEPLETION_DAYS
        near.extend(np.abs(Y[i, sel] - P[i, sel]).tolist())

    speed = _measure_speed(sur, X, float(ds.config.get("fixed", {}).get("Th", 300.0)))
    m = {
        "n_test": int(len(X)),
        "test_r2": r2_curves(Y, P),
        "test_rmse": float(np.sqrt(np.mean((Y - P) ** 2))),
        "ratio365_mae": float(err.mean()),
        "ratio365_max": float(err.max()),
        "near_depletion_mae": float(np.mean(near)) if near else None,
        "speedup": float(speed["speedup"]),
        "speed": speed,
        "monotonic_violations": int(np.sum(np.any(np.diff(P, axis=1) > 0, axis=1))),
        "range_violations": int(np.sum(~np.all((P >= 0.0) & (P <= 1.0), axis=1))),
    }
    m["sc_pass"] = sc_pass(m)

    order = np.argsort(-err, kind="stable")[:N_WORST]
    ids = np.asarray(ds.sample_id)[ds.split == 2]
    m["worst"] = [{"sample_id": int(ids[i]), "error": float(err[i]), "m0": float(m0[i]),
                   "inputs": {n: float(v) for n, v in zip(ds.input_names, X[i])}} for i in order]

    cost = cost_error_usd(m0, Y[:, -1] - P[:, -1])
    edges = np.quantile(m0, np.linspace(0.0, 1.0, COST_BINS + 1))
    idx = np.clip(np.searchsorted(edges, m0, side="right") - 1, 0, COST_BINS - 1)
    bins = []
    for b in range(COST_BINS):
        sel = idx == b
        if sel.any():
            bins.append({"m0_lo": float(m0[sel].min()), "m0_hi": float(m0[sel].max()), "n": int(sel.sum()),
                         "mean": float(cost[sel].mean()), "max": float(cost[sel].max())})
    m["cost_error"] = {"p_h2_usd_per_kg": float(P_H2_REPORT), "mean": float(cost.mean()),
                       "max": float(cost.max()), "bins": bins}
    return m


def meta_metrics(m: dict) -> dict:
    """meta.json에 넣는 요약 지표."""
    keys = ("test_r2", "test_rmse", "ratio365_mae", "ratio365_max", "near_depletion_mae", "speedup",
            "monotonic_violations", "range_violations", "sc_pass")
    return {k: m[k] for k in keys}


# ---------- 보고서 ----------

def _fmt(v, spec=".4g"):
    return "n/a" if v is None else format(v, spec)


def _write_figures(sur, ds, m, out: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    X, Y, aux = ds.part("test")
    P = sur.predict(X)
    err = Y[:, -1] - P[:, -1]

    fig, ax = plt.subplots(figsize=(6, 4))
    ax.plot(range(1, len(sur.history["train_mse"]) + 1), sur.history["train_mse"], label="train")
    ax.plot(range(1, len(sur.history["val_mse"]) + 1), sur.history["val_mse"], label="val")
    ax.axvline(sur.best_epoch, color="gray", ls=":", label=f"best epoch {sur.best_epoch}")
    ax.set_yscale("log")
    ax.set_xlabel("epoch")
    ax.set_ylabel("MSE (t=1..99) [-]")
    ax.legend()
    fig.tight_layout()
    fig.savefig(out / "loss_history.png", dpi=110)
    plt.close(fig)

    id_to_row = {int(s): i for i, s in enumerate(np.asarray(ds.sample_id)[ds.split == 2])}
    rows = [id_to_row[w["sample_id"]] for w in m["worst"]]
    fig, axes = plt.subplots(3, 4, figsize=(14, 8), sharex=True, sharey=True, squeeze=False)
    for ax, r, w in zip(axes.ravel(), rows, m["worst"]):
        ax.plot(ds.t, Y[r], "k-", label="ODE")
        ax.plot(ds.t, P[r], "r--", label="surrogate")
        ax.set_title(f"id {w['sample_id']}  err365={w['error']:.3f}", fontsize=9)
    for ax in axes.ravel()[len(rows):]:
        ax.axis("off")
    axes[0, 0].legend(fontsize=8)
    fig.supxlabel("t [day]")
    fig.supylabel("m / m0 [-]")
    fig.tight_layout()
    fig.savefig(out / "worst_curves.png", dpi=110)
    plt.close(fig)

    fig, axes = plt.subplots(2, 5, figsize=(16, 6), squeeze=False)
    for j, (ax, nm) in enumerate(zip(axes.ravel(), ds.input_names)):
        ax.scatter(X[:, j], np.abs(err), s=6, alpha=0.5)
        if ds.input_scales[j] == "log":
            ax.set_xscale("log")
        ax.set_xlabel(nm)
        ax.set_ylabel("|err365| [-]")
    fig.tight_layout()
    fig.savefig(out / "error_by_input.png", dpi=110)
    plt.close(fig)

    m0 = aux[:, list(ds.aux_names).index("m0")]
    cost = cost_error_usd(m0, err)
    bins = m["cost_error"]["bins"]
    edges = [bins[0]["m0_lo"], *[b["m0_hi"] for b in bins]]
    idx = np.clip(np.searchsorted(edges[1:-1], m0, side="left"), 0, len(bins) - 1)  # 구간 상한(m0_hi)은 그 구간에 포함
    groups = [cost[idx == b] for b in range(len(bins))]
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.boxplot([g for g in groups if g.size], showfliers=True)
    ax.set_xticklabels([f"{b['m0_lo']:.3g}-{b['m0_hi']:.3g}" for b, g in zip(bins, groups) if g.size],
                       fontsize=8)
    ax.set_xlabel("m0 bin [kg]")
    ax.set_ylabel(f"p_H2*m0*|err| [$/yr] (p_H2={P_H2_REPORT:g} $/kg)")
    fig.tight_layout()
    fig.savefig(out / "cost_error.png", dpi=110)
    plt.close(fig)


def _write_markdown(sur, m, out: Path) -> None:
    sc = m["sc_pass"]
    head = " · ".join(f"{k} {'PASS' if v else 'FAIL'}" for k, v in sc.items())
    rows = [
        ("SC-001", f"테스트 R² ≥ {SC_TARGETS['r2']}", f"{m['test_r2']:.5f}"),
        ("SC-002", f"365일 잔량비 평균 오차 ≤ {SC_TARGETS['mae']}, 최대 ≤ {SC_TARGETS['max']}",
         f"평균 {m['ratio365_mae']:.4f}, 최대 {m['ratio365_max']:.4f}"),
        ("SC-003", f"ODE 대비 속도 ≥ {SC_TARGETS['speedup']:g}배", f"{m['speedup']:.0f}배"),
        ("SC-004", "0~1 위반 0건, 단조 증가 위반 0건",
         f"범위 {m['range_violations']}건, 단조 {m['monotonic_violations']}건"),
    ]
    lines = [f"# 평가 보고서: {head}", "", "| 기준 | 목표 | 측정 | 판정 |", "|---|---|---|---|"]
    lines += [f"| {k} | {goal} | {val} | {'PASS' if sc[k] else 'FAIL'} |" for k, goal, val in rows]
    lines += [
        "", "## 지표 (테스트 세트)", "",
        f"- 테스트 샘플 수: {m['n_test']}",
        f"- R² (모든 시점·샘플을 한 덩어리로): {m['test_r2']:.5f}, RMSE: {m['test_rmse']:.5f} [-]",
        f"- 365일 잔량비 오차: 평균 {m['ratio365_mae']:.5f}, 최대 {m['ratio365_max']:.5f} [-]",
        f"- 소진 시점 ±{NEAR_DEPLETION_DAYS:g}일 구간 평균 오차: {_fmt(m['near_depletion_mae'])} [-]",
        f"- 속도: 대리모델 {m['speed']['n_batch']}개 {m['speed']['t_surrogate_s'] * 1e3:.2f} ms, "
        f"ODE {m['speed']['n_ode']}개 측정 후 {m['speed']['n_batch']}개로 환산 {m['speed']['t_ode_s'] * 1e3:.0f} ms "
        f"→ {m['speedup']:.0f}배",
        f"- 학습: 최선 epoch {sur.best_epoch} / 실행 epoch {len(sur.history['val_mse'])}, "
        f"최소 검증 MSE {min(sur.history['val_mse']):.3e}",
        "", f"## 오차 상위 {len(m['worst'])}개 샘플 (365일 잔량비)", "",
        "| sample_id | 오차 | m0 [kg] | " + " | ".join(sur.input_names) + " |",
        "|---|---|---|" + "---|" * len(sur.input_names),
    ]
    for w in m["worst"]:
        lines.append(f"| {w['sample_id']} | {w['error']:.4f} | {w['m0']:.4g} | "
                     + " | ".join(f"{w['inputs'][n]:.4g}" for n in sur.input_names) + " |")
    ce = m["cost_error"]
    lines += ["", f"## 보일오프 비용 환산 오차 (p_H2 = {ce['p_h2_usd_per_kg']:g} $/kg, `p_H2·m0·|오차|` [$/yr])", "",
              f"전체 평균 {ce['mean']:.4g}, 최대 {ce['max']:.4g} $/yr", "",
              "| m0 구간 [kg] | n | 평균 [$/yr] | 최대 [$/yr] |", "|---|---|---|---|"]
    for b in ce["bins"]:
        lines.append(f"| {b['m0_lo']:.4g} ~ {b['m0_hi']:.4g} | {b['n']} | {b['mean']:.4g} | {b['max']:.4g} |")
    lines += ["", "## 그림", "", "- loss_history.png, worst_curves.png, error_by_input.png, cost_error.png", ""]
    (out / "report.md").write_text("\n".join(lines), encoding="utf-8", newline="\n")


def write_report(sur, ds, metrics: dict, out_dir) -> Path:
    """`out_dir`에 report.md, metrics.json, 그림 4개를 쓴다. 반환: out_dir."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    _write_figures(sur, ds, metrics, out)
    _write_markdown(sur, metrics, out)
    with open(out / "metrics.json", "w", encoding="utf-8", newline="\n") as fh:
        json.dump(metrics, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    return out


# ---------- CLI ----------

def main(argv=None) -> int:
    from data.io import load_dataset
    from surrogate.model import load_surrogate

    parser = argparse.ArgumentParser(prog="python -m surrogate.evaluate",
                                     description="저장된 대리모델의 평가 보고서를 다시 만든다 (specs/002)")
    parser.add_argument("model_dir", help="models/<name> 디렉터리")
    try:
        args = parser.parse_args(argv)
    except SystemExit as e:
        return 0 if e.code == 0 else 1
    model_dir = Path(args.model_dir)
    try:
        sur = load_surrogate(model_dir)
        ds_path = sur.dataset_info.get("path")
        if not ds_path:
            raise ValueError("모델에 데이터셋 경로가 기록돼 있지 않음")
        ds = load_dataset(ds_path)
        m = evaluate_model(sur, ds)
        write_report(sur, ds, m, model_dir / "report")
        meta_path = model_dir / "meta.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta["metrics"] = meta_metrics(m)
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
                             newline="\n")
    except Exception as e:  # noqa: BLE001
        print(f"ERROR 평가 실패: {type(e).__name__}: {e}", file=sys.stderr)
        return 1
    print(model_dir / "report")
    return 0


if __name__ == "__main__":
    sys.exit(main())
