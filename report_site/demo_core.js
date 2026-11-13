/* 브라우저 시연 계산 코어 (DOM 없음). 발표 자료(docs/presentation.html)에 그대로 들어가고, node로 테스트한다.
 *
 * - predict: 학습된 MLP 대리모델 (특성 11개 → 99점, 후처리: [0,1] 자르기·맨 앞 1·누적 최솟값)
 * - simulate: physics.BoiloffModel과 같은 식을 RK4로 푼 1년 잔량 곡선 (기준값, 헌법 I)
 * - costs / optimize: physics.cost와 optimize.optimize_layers와 같은 식 (경제 변수는 후처리, 헌법 IV)
 * 상수·가중치·w 표는 report_site/export_demo.py가 Python에서 내보낸 값을 쓴다.
 */
(function (root) {
  'use strict';

  function b64f32(s) {
    const bin = atob(s);
    const u = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) u[i] = bin.charCodeAt(i);
    return new Float32Array(u.buffer);
  }

  function interp(x, xs, ys) {           // np.interp (xs 오름차순)
    const n = xs.length;
    if (x <= xs[0]) return ys[0];
    if (x >= xs[n - 1]) return ys[n - 1];
    let lo = 0, hi = n - 1;
    while (hi - lo > 1) { const m = (lo + hi) >> 1; if (xs[m] <= x) lo = m; else hi = m; }
    const a = (x - xs[lo]) / (xs[hi] - xs[lo]);
    return ys[lo] + a * (ys[hi] - ys[lo]);
  }

  function create(D) {
    const C = D.physics, M = D.model, O = D.optimize;
    const names = M.input_names, logs = new Set(M.log_inputs), Th = M.Th;
    const layers = M.layers.map(L => ({ nin: L.nin, nout: L.nout, W: b64f32(L.W), b: b64f32(L.b) }));
    const wt = b64f32(D.wtable.values);
    const [f0, f1, nf] = D.wtable.fill, [d0, d1, nd] = D.wtable.ld;
    const t = M.t.slice();

    function vec(design) { return names.map(k => Number(design[k])); }

    function checkRange(design) {
      names.forEach((k, j) => {
        const v = Number(design[k]);
        if (!Number.isFinite(v) || v < M.lo[j] || v > M.hi[j]) {
          throw new RangeError(`${k}=${v}이(가) 학습 범위 [${M.lo[j]}, ${M.hi[j]}] 밖`);
        }
      });
    }

    function heatFlux(N, Nbar, eps, Ppa, Tc) {   // physics.heat.mli_heat_flux [W/m²]
      const Tm = 0.5 * (Th + Tc), P = Ppa * C.PA_TO_TORR;
      const qs = C.C_S * Math.pow(Nbar, C.EXP_S) * Tm * (Th - Tc);
      const qr = C.C_R * eps * (Math.pow(Th, 4.67) - Math.pow(Tc, 4.67));
      const qg = C.C_G * P * (Math.pow(Th, 0.52) - Math.pow(Tc, 0.52));
      return (qs + qr + qg) / N;
    }

    function wettedFraction(fill, ld) {          // surrogate.features.wetted_fraction (2차원 선형 보간)
      const df = (f1 - f0) / (nf - 1), dd = (d1 - d0) / (nd - 1);
      const f = Math.min(Math.max(fill, f0), f1), d = Math.min(Math.max(ld, d0), d1);
      const fx = (f - f0) / df, dx = (d - d0) / dd;
      const i = Math.min(Math.floor(fx), nf - 2), j = Math.min(Math.floor(dx), nd - 2);
      const a = fx - i, b = dx - j, T = (r, c) => wt[r * nd + c];
      return (1 - a) * (1 - b) * T(i, j) + a * (1 - b) * T(i + 1, j) + (1 - a) * b * T(i, j + 1) + a * b * T(i + 1, j + 1);
    }

    function geometry(design) {
      const R = design.R, L = 2 * R * design.LD;
      const A = 2 * Math.PI * R * L + 4 * Math.PI * R * R;
      const V = Math.PI * R * R * L + 4 / 3 * Math.PI * R * R * R;
      return { R, L, A, V, m0: design.fill * C.RHO_L * V };
    }

    function features(design) {
      const g = geometry(design);
      const w = wettedFraction(design.fill, design.LD);
      const q = heatFlux(design.N, design.Nbar, design.eps, design.Pv0, C.T_C);
      const Q0 = q * g.A * (w + C.ETA * (1 - w)) + design.G_sup * (Th - C.T_C);
      const k = Q0 / (C.H_FG * g.m0) * C.DAY;
      const z = vec(design).map((v, j) => logs.has(names[j]) ? Math.log10(v) : v);
      z.push(Math.log10(k));
      return { z, Q0, k, m0: g.m0, A: g.A };
    }

    function forward(z) {
      let x = z.map((v, j) => (v - M.scaler_mean[j]) / M.scaler_scale[j]);
      layers.forEach((L, li) => {
        const y = new Float64Array(L.nout);
        for (let o = 0; o < L.nout; o++) y[o] = L.b[o];
        for (let i = 0; i < L.nin; i++) {
          const xi = x[i]; if (xi === 0) continue;
          const row = i * L.nout;
          for (let o = 0; o < L.nout; o++) y[o] += xi * L.W[row + o];
        }
        if (li < layers.length - 1) for (let o = 0; o < L.nout; o++) if (y[o] < 0) y[o] = 0;
        x = y;
      });
      const curve = [1];
      let prev = 1;
      for (let o = 0; o < x.length; o++) { prev = Math.min(prev, Math.min(1, Math.max(0, x[o]))); curve.push(prev); }
      return curve;
    }

    function predict(design) {
      checkRange(design);
      const f = features(design);
      return { t, curve: forward(f.z), Q0: f.Q0, k: f.k, m0: f.m0, A: f.A };
    }

    // ---------------- ODE (physics.model.BoiloffModel과 같은 식, RK4) ----------------
    function simulate(design, substeps = 40) {
      checkRange(design);
      const g = geometry(design), R = g.R, Lc = g.L;
      const NG = 2001, hg = new Float64Array(NG), Vg = new Float64Array(NG);
      const theta = h => Math.acos(Math.min(1, Math.max(-1, (R - h) / R)));
      for (let i = 0; i < NG; i++) {
        const h = 2 * R * i / (NG - 1);
        const seg = R * R * theta(h) - (R - h) * Math.sqrt(Math.max(2 * R * h - h * h, 0));
        hg[i] = h; Vg[i] = Lc * seg + Math.PI * h * h * (3 * R - h) / 3;
      }
      const Vvac = g.A * (design.N / design.Nbar / 100 + C.GAP_EXTRA);
      const Peq = design.G_out / design.S;
      const Q = (ts, m) => {
        const h = interp(Math.max(m, 0) / C.RHO_L, Vg, hg);
        const hh = Math.min(Math.max(h, 0), 2 * R);
        const Aw = 2 * R * Lc * theta(hh) + 2 * Math.PI * R * hh;
        const Pv = Peq + (design.Pv0 - Peq) * Math.exp(-design.S * ts / Vvac);
        const q = heatFlux(design.N, design.Nbar, design.eps, Pv, C.T_C);
        return q * (Aw + C.ETA * (g.A - Aw)) + design.G_sup * (Th - C.T_C);
      };
      const f = (ts, m) => -Q(ts, m) / C.H_FG;
      const ratio = [1];
      let m = g.m0, ts = 0, tEmpty = null;
      for (let k = 1; k < t.length; k++) {
        const tEnd = t[k] * C.DAY, dt = (tEnd - ts) / substeps;
        for (let s = 0; s < substeps && tEmpty === null; s++) {
          const k1 = f(ts, m), k2 = f(ts + dt / 2, m + dt / 2 * k1), k3 = f(ts + dt / 2, m + dt / 2 * k2), k4 = f(ts + dt, m + dt * k3);
          const mn = m + dt / 6 * (k1 + 2 * k2 + 2 * k3 + k4);
          if (mn <= 0) { tEmpty = (ts + dt * m / (m - mn)) / C.DAY; m = 0; }
          else m = mn;
          ts += dt;
        }
        ts = tEnd;
        ratio.push(tEmpty === null ? Math.min(1, Math.max(0, m / g.m0)) : 0);
      }
      return { t, ratio, tEmpty, m0: g.m0 };
    }

    // ---------------- 비용과 적층수 최적화 ----------------
    function crf(e) {
      if (e.discount === 0) return 1 / e.life_years;
      const gg = Math.pow(1 + e.discount, e.life_years);
      return e.discount * gg / (gg - 1);
    }

    function costs(design, econ, N, r365) {     // physics.cost (mli_capex·crf, p_h2·m0·(1−r))
      const g = geometry(design);
      const capex = (econ.c_layer * N + econ.c_fixed) * g.A;
      const annual_mli = capex * crf(econ);
      const m_lost = g.m0 * (1 - r365);
      const annual_boiloff = econ.p_h2 * m_lost;
      return { capex, annual_mli, annual_boiloff, annual_total: annual_mli + annual_boiloff, m_lost };
    }

    function optimize(design, econ) {           // optimize.optimize_layers (잔량 제약 없음)
      const [n0, n1] = O.N_RANGE, Ns = [], rows = [];
      for (let n = n0; n <= n1; n++) {
        const d = Object.assign({}, design, { N: n });
        const p = predict(d), r365 = p.curve[p.curve.length - 1];
        const c = costs(d, econ, n, r365);
        Ns.push(n); rows.push(Object.assign({ N: n, r365, curve: p.curve, depleted: !(r365 >= O.DEPLETION_TOL) }, c));
      }
      const feas = rows.filter(r => !r.depleted && Number.isFinite(r.annual_total));
      let best = null;
      feas.forEach(r => { if (!best || r.annual_total < best.annual_total) best = r; });
      const res = { N: Ns, rows, depleted: rows.map(r => r.depleted), n_opt: null, total_opt: null, flat: null, warnings: [] };
      const nDep = rows.filter(r => r.depleted).length;
      if (nDep) res.warnings.push(`365일 잔량비 < ${O.DEPLETION_TOL}인 N ${nDep}개를 후보에서 제외(소진)`);
      if (!best) { res.warnings.push('실행 가능한 적층수가 없음'); return res; }
      const near = feas.filter(r => r.annual_total <= best.annual_total * (1 + O.FLAT_TOL)).map(r => r.N);
      Object.assign(res, { n_opt: best.N, total_opt: best.annual_total, best, flat: [Math.min(...near), Math.max(...near)] });
      if (best.N === n1) res.warnings.push(`최적 N이 범위 상한 ${n1}: 범위 확장 검토`);
      if (best.N === n0) res.warnings.push(`최적 N이 범위 하한 ${n0}: 범위 확장 검토`);
      return res;
    }

    // optimize.verify_with_ode: 대리모델 상위 후보 topK개 + N 전 범위를 ODE로 다시 계산한다(헌법 I)
    function verifyOde(design, econ, opt, topK = 5) {
      const scan = opt.N.map(n => {
        const d = Object.assign({}, design, { N: n }), s = simulate(d), r = s.ratio[s.ratio.length - 1];
        return Object.assign({ N: n, depleted: s.tEmpty !== null || r <= 0, ratio: s.ratio }, costs(d, econ, n, r));
      });
      const byN = n => scan[n - opt.N[0]];
      const candidates = opt.rows.filter(r => !r.depleted).slice().sort((a, b) => a.annual_total - b.annual_total)
        .slice(0, topK).map(r => r.N);
      const candidate_totals_ode = candidates.map(n => byN(n).annual_total);
      const live = candidates.filter(n => !byN(n).depleted);
      const n_recommended = live.length ? live.reduce((a, b) => byN(b).annual_total < byN(a).annual_total ? b : a) : null;
      const ok = scan.filter(r => !r.depleted);
      const best = ok.length ? ok.reduce((a, b) => b.annual_total < a.annual_total ? b : a) : null;
      const res = { scan, candidates, candidate_totals_ode, n_recommended, n_sur: opt.n_opt,
        n_ode: best ? best.N : null, total_ode: best ? best.annual_total : null, total_ode_at_sur: null, rel_cost_err: null, dN: null };
      if (opt.n_opt != null && best) {
        res.total_ode_at_sur = byN(opt.n_opt).annual_total;
        res.rel_cost_err = (res.total_ode_at_sur - best.annual_total) / best.annual_total;
        res.dN = opt.n_opt - best.N;
      }
      return res;
    }

    return { names, lo: M.lo, hi: M.hi, log: names.map(k => logs.has(k)), t, predict, simulate, costs, optimize, verifyOde, checkRange,
      constants: { H_FG: C.H_FG, DAY: C.DAY, DEPLETION_TOL: O.DEPLETION_TOL }, meta: D.meta };
  }

  const api = { create };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.LH2 = api;
})(typeof globalThis !== 'undefined' ? globalThis : this);
