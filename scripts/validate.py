"""Stage 6 validation: run the full pipeline on several generator seeds and score it.

    python scripts/validate.py [--seeds 7 11 23 42 99] [--runs 200]

For each seed: generate synthetic CSEs -> ingest into a fresh DuckDB -> run the analysis ->
compare with the planted ground truth -> simulate manual random review vs the review queue.
Writes data/processed/validation/results.json, docs/validation/*.png and docs/validation_report.md.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from socassess import store  # noqa: E402
from socassess.analytics.engine import persist, run_analysis  # noqa: E402
from socassess.ingestion.pipeline import ingest_path  # noqa: E402
from socassess.validation import evaluate, random_review_curve, tool_review_curve  # noqa: E402

OUT = ROOT / "data" / "processed" / "validation"
DOCS = ROOT / "docs"
FIG = DOCS / "validation"
MIN_PER_RECORD = 5  # assumed analyst minutes to review one record, for the time comparison
BUDGETS = [12, 24, 36, 60, 96, 120, 180, 240, 360, 480, 720, 960, 1440, 1920, 2880, 3840]

# chart tokens (reference palette, light surface)
INK, INK2, MUTED, GRID, AXIS, SURF = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7", "#fcfcfb"
S1, S2, S3 = "#2a78d6", "#eb6834", "#1baf7a"


def run_seed(seed: int, runs: int) -> dict:
    d = OUT / f"seed_{seed}"
    raw, truth_path, db = d / "raw", d / "ground_truth.json", d / "store.duckdb"
    d.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    subprocess.run([sys.executable, str(ROOT / "scripts" / "generate_synthetic.py"), "--seed", str(seed),
                    "--out", str(raw), "--truth", str(truth_path)], check=True, stdout=subprocess.DEVNULL)
    t_gen = time.perf_counter() - t0
    if db.exists():
        db.unlink()
    con = store.connect(db)
    for p in sorted(raw.glob("CSE*")):
        ingest_path(con, p, source="synthetic")
    t_ing = time.perf_counter() - t0 - t_gen
    res = run_analysis(con)
    persist(con, res, trigger="validation")
    truth = json.loads(truth_path.read_text())
    findings = pd.DataFrame([f.to_dict() for f in res.findings])
    ev = evaluate(findings, res.scores, truth)
    cases = con.execute("SELECT case_id, entity_id FROM cases").df()
    con.close()
    curves = {
        "tool": tool_review_curve(res.queue, truth).to_dict("records"),
        "random_stratified": random_review_curve(cases, truth, BUDGETS, runs, True, seed).to_dict("records"),
        "random_uniform": random_review_curve(cases, truth, BUDGETS, runs, False, seed).to_dict("records"),
    }
    scores = res.scores[res.scores.entity_id.isin(truth["entities"])][["entity_id", "risk_score"]]
    scores["healthy"] = scores.entity_id.map(lambda e: truth["entities"][e]["healthy"])
    print(f"seed {seed}: weakness P={ev['weakness']['precision']:.2f} R={ev['weakness']['recall']:.2f} "
          f"evidence P={ev['evidence_micro']['precision']:.3f} R={ev['evidence_micro']['recall']:.3f} "
          f"AUC={ev['entities']['auc_risk_score']:.2f} healthy alarms={len(ev['entities']['healthy_false_alarms'])} "
          f"({time.perf_counter() - t0:.0f}s)", flush=True)
    return {"seed": seed, "run_id": res.run_id, "analysis_s": res.duration_s, "generate_s": round(t_gen, 1),
            "ingest_s": round(t_ing, 1), "eval": ev, "curves": curves, "scores": scores.to_dict("records")}


def _style(ax):
    ax.set_facecolor(SURF)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(AXIS)
    ax.tick_params(colors=MUTED, labelsize=9)
    ax.grid(axis="y", color=GRID, linewidth=1)
    ax.set_axisbelow(True)


def chart_curves(results: list[dict], path: Path) -> None:
    fig, ax = plt.subplots(figsize=(8, 4.6), dpi=150, facecolor=SURF)
    _style(ax)
    planted = results[0]["eval"]["weakness"]["planted"]
    # tool: one thin line per seed; random: mean with p10-p90 band (first seed's grid)
    for i, r in enumerate(results):
        t = pd.DataFrame(r["curves"]["tool"])
        ax.step(t.records_reviewed.clip(lower=1), t.recall * 100, where="post", color=S1, lw=2 if i == 0 else 1,
                alpha=1 if i == 0 else 0.45, label="Review queue (SOCAssess)" if i == 0 else None)
    for key, color, label in (("random_stratified", S2, "Random sample, equal per entity"),
                              ("random_uniform", S3, "Random sample, all cases")):
        m = pd.concat([pd.DataFrame(r["curves"][key]) for r in results]).groupby("records_reviewed").mean(numeric_only=True)
        ax.plot(m.index, m.recall_mean * 100, color=color, lw=2, label=label)
        if key == "random_stratified":
            ax.fill_between(m.index, m.confirmed_p10 / planted * 100, m.confirmed_p90 / planted * 100, color=color,
                            alpha=0.1, lw=0)
    ax.set_xscale("log")
    ax.set_xlim(1, 4000)
    ax.set_ylim(0, 105)
    ax.set_xlabel("Records reviewed by hand (log scale)", color=INK2, fontsize=9)
    ax.set_ylabel("Planted weaknesses confirmed (%)", color=INK2, fontsize=9)
    ax.set_title("Weaknesses confirmed per record reviewed", color=INK, fontsize=11, loc="left", pad=12)
    leg = ax.legend(frameon=False, fontsize=9, loc="upper left")
    for txt in leg.get_texts():
        txt.set_color(INK2)
    fig.tight_layout()
    fig.savefig(path, facecolor=SURF)
    plt.close(fig)


def chart_scores(results: list[dict], path: Path) -> None:
    fig, ax = plt.subplots(figsize=(8, 2.8), dpi=150, facecolor=SURF)
    _style(ax)
    ax.grid(axis="y", visible=False)
    ax.grid(axis="x", color=GRID, linewidth=1)
    n = len(results)
    for i, r in enumerate(results):
        s = pd.DataFrame(r["scores"])
        offset = (i - (n - 1) / 2) * 0.12  # one thin row per seed, so equal scores don't overprint
        for healthy, color, y in ((True, S3, 0), (False, S1, 1)):
            v = s[s.healthy == healthy].risk_score.to_numpy()
            ax.scatter(v, np.full(len(v), y + offset), s=30, color=color, edgecolor=SURF, linewidth=1.5, zorder=3)
    ax.set_yticks([0, 1], ["Healthy CSEs", "CSEs with planted\nweaknesses"], color=INK2, fontsize=9)
    ax.set_ylim(-0.6, 1.6)
    ax.set_xlabel("Entity risk score (one row per seed)", color=INK2, fontsize=9)
    ax.set_title("Risk score separates weak from healthy entities", color=INK, fontsize=11, loc="left", pad=10)
    fig.tight_layout()
    fig.savefig(path, facecolor=SURF)
    plt.close(fig)


def records_for_recall(curve: list[dict], key: str, target: float) -> float | None:
    df = pd.DataFrame(curve)
    col = "recall" if "recall" in df else "recall_mean"
    hit = df[df[col] >= target]
    return float(hit.records_reviewed.iloc[0]) if len(hit) else None


def write_report(results: list[dict]) -> None:
    def pct(x):
        return "–" if x is None else f"{100 * x:.1f}%"

    rows = []
    for r in results:
        e = r["eval"]
        rows.append(f"| {r['seed']} | {e['weakness']['tp']}/{e['weakness']['planted']} | {e['weakness']['fp']} | "
                    f"{pct(e['weakness']['precision'])} | {pct(e['weakness']['recall'])} | "
                    f"{pct(e['evidence_micro']['precision'])} | {pct(e['evidence_micro']['recall'])} | "
                    f"{e['entities']['auc_risk_score']:.2f} | {e['entities']['healthy_flagged']}/{e['entities']['healthy']} | "
                    f"{r['analysis_s']:.0f}s |")
    tp = sum(r["eval"]["weakness"]["tp"] for r in results)
    fp = sum(r["eval"]["weakness"]["fp"] for r in results)
    planted = sum(r["eval"]["weakness"]["planted"] for r in results)
    all_types = pd.concat([pd.DataFrame(r["eval"]["per_type"]) for r in results]).groupby("type").sum(numeric_only=True)
    type_rows = [f"| {t} | {int(x.planted)} | {int(x.detected)} | {int(x.false_positive)} | "
                 f"{pct(x.detected / (x.detected + x.false_positive) if x.detected + x.false_positive else None)} | "
                 f"{pct(x.detected / x.planted)} |" for t, x in all_types.iterrows()]
    ev = pd.concat([pd.DataFrame(r["eval"]["evidence"]) for r in results]).groupby("type").sum(numeric_only=True)
    ev_rows = [f"| {t} | {int(x.planted)} | {int(x.found)} | {int(x.overlap)} | {pct(x.overlap / x.found)} | "
               f"{pct(x.overlap / x.planted)} |" for t, x in ev.iterrows()]
    missed = [(r["seed"], m) for r in results for m in r["eval"]["weakness"]["missed"]]
    spurious = [(r["seed"], m) for r in results for m in r["eval"]["weakness"]["spurious"]]
    alarms = [(r["seed"], a) for r in results for a in r["eval"]["entities"]["healthy_false_alarms"]]

    # review effort comparison (averaged over seeds)
    def avg_records(key, target):
        vals = [records_for_recall(r["curves"][key], key, target) for r in results]
        return None if any(v is None for v in vals) else float(np.mean(vals))

    tool_full = avg_records("tool", 1.0)
    tool_conf = np.mean([pd.DataFrame(r["curves"]["tool"]).recall.iloc[-1] for r in results])
    queue_len = np.mean([pd.DataFrame(r["curves"]["tool"]).records_reviewed.iloc[-1] for r in results])

    def random_at(key, n):
        vals = []
        for r in results:
            df = pd.DataFrame(r["curves"][key])
            vals.append(float(np.interp(n, df.records_reviewed, df.recall_mean)))
        return float(np.mean(vals))

    def random_max(key):
        return float(np.mean([pd.DataFrame(r["curves"][key]).recall_mean.max() for r in results]))

    budget = tool_full or queue_len
    effort = [
        f"| Review queue (SOCAssess) | {budget:.0f} | {pct(tool_conf)} | {budget * MIN_PER_RECORD / 60:.1f} h |",
        f"| Random sample, equal per entity, same budget | {budget:.0f} | {pct(random_at('random_stratified', budget))} | "
        f"{budget * MIN_PER_RECORD / 60:.1f} h |",
        f"| Random sample, all cases, same budget | {budget:.0f} | {pct(random_at('random_uniform', budget))} | "
        f"{budget * MIN_PER_RECORD / 60:.1f} h |",
        f"| Random sample, equal per entity, {BUDGETS[-1]:,} records | {BUDGETS[-1]:,} | "
        f"{pct(random_max('random_stratified'))} | {BUDGETS[-1] * MIN_PER_RECORD / 60:.0f} h |",
    ]
    seeds = ", ".join(str(r["seed"]) for r in results)
    md = f"""# Validation report

Generated by `python scripts/validate.py` on {pd.Timestamp.now(tz="UTC"):%Y-%m-%d %H:%M} UTC.
Seeds: {seeds}. Each seed is a fresh synthetic world of 12 CSEs (4 healthy, 8 with 1–3 planted
weaknesses; {results[0]['eval']['weakness']['planted']} planted weaknesses per seed), run through the full pipeline:
generate → ingest (CSV/JSON/SQLite) → analyse with the **default parameters** (no per-seed tuning) → compare with
the ground truth. Seed 7 is the dataset the parameters were developed on; **the other seeds are held-out data.**

## Headline

| | Result (all {len(results)} seeds) |
|---|---|
| Planted weaknesses detected (recall) | **{tp}/{planted} = {pct(tp / planted)}** |
| Findings of a planted type that were wrong (precision) | **{tp}/{tp + fp} = {pct(tp / (tp + fp) if tp + fp else None)}** |
| Healthy entities with any finding (false alarms) | {sum(r['eval']['entities']['healthy_flagged'] for r in results)}/{sum(r['eval']['entities']['healthy'] for r in results)} |
| Risk-score ranking, weak vs healthy (AUC) | {np.mean([r['eval']['entities']['auc_risk_score'] for r in results]):.2f} |
| Records to review to confirm every weakness (queue) | {budget:.0f} on average (≈ {budget * MIN_PER_RECORD / 60:.1f} analyst-hours at {MIN_PER_RECORD} min/record) |

## Per seed

| Seed | Detected | Wrong-type FP | Precision | Recall | Evidence precision | Evidence recall | AUC | Healthy flagged | Analysis time |
|---|---|---|---|---|---|---|---|---|---|
{chr(10).join(rows)}

## Per weakness type (all seeds)

| Type | Planted | Detected | False positives | Precision | Recall |
|---|---|---|---|---|---|
{chr(10).join(type_rows)}

### Evidence quality (record level, detected weaknesses with record evidence)

`found` = records the finding cites, `planted` = records the generator planted, `overlap` = both.

| Type | Planted records | Found records | Overlap | Precision | Recall |
|---|---|---|---|---|---|
{chr(10).join(ev_rows)}

Evidence precision below 100% means the finding also cites records that meet the detector's rule but were
not planted. Healthy entities also contain some naturally fast closures and unescalated critical cases, so
these are true rule matches, not errors.

## Misses and false alarms

- Missed weaknesses: {", ".join(f"seed {s}: {e} {t}" for s, (e, t) in missed) or "none"}.
- Findings of a planted type on the wrong entity: {", ".join(f"seed {s}: {e} {t}" for s, (e, t) in spurious) or "none"}.
- Any finding on a healthy entity: {", ".join(f"seed {s}: {a['entity_id']} {a['type']}" for s, a in alarms) or "none"}.

## Tool vs manual sampling

![Weaknesses confirmed per record reviewed](validation/recall_vs_budget.png)

A supervisor who checks randomly sampled case records confirms a weakness only when one of the sampled
records is planted evidence. The review queue instead puts the strongest evidence for each finding
first. A weakness counts as confirmed only when the reviewed record really is planted evidence (or is a
finding-level item for something that is missing).

| Approach | Records reviewed | Weaknesses confirmed | Analyst time |
|---|---|---|---|
{chr(10).join(effort)}

Random case sampling has a ceiling: weaknesses that leave **no case record** (silent critical assets, missing
alert categories, abnormally low activity, alerts that never got a case) can never be found by sampling cases,
however many are reviewed. Those need the cross-entity, negative-space comparison the tool makes. The
time figures assume {MIN_PER_RECORD} minutes per record and leave out the tool's own runtime (under a minute, unattended).

![Risk scores](validation/risk_scores.png)

## Method notes and limits
- The data is synthetic and the planted weaknesses are deliberately clear-cut. Real SOC data is noisier, so
  these numbers are an upper bound on what to expect, not a field measurement.
- Healthy entities include realistic noise (some fast closures, unescalated true positives, SLA breaches,
  open cases), so the detectors cannot rely on clean baselines.
- Thresholds were set once on seed 7 and kept fixed. The other seeds measure how well they generalise.
- The random baseline is a Monte Carlo average ({RUNS} repetitions per budget); the shaded band in
  the chart is its 10th–90th percentile.
- Raw results: `data/processed/validation/results.json`.
"""
    (DOCS / "validation_report.md").write_text(md, encoding="utf-8")


RUNS = 200


def main() -> None:
    global RUNS
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, nargs="+", default=[7, 11, 23, 42, 99])
    ap.add_argument("--runs", type=int, default=200)
    args = ap.parse_args()
    RUNS = args.runs
    OUT.mkdir(parents=True, exist_ok=True)
    FIG.mkdir(parents=True, exist_ok=True)
    results = [run_seed(s, args.runs) for s in args.seeds]
    (OUT / "results.json").write_text(json.dumps(results, indent=1, default=str))
    chart_curves(results, FIG / "recall_vs_budget.png")
    chart_scores(results, FIG / "risk_scores.png")
    write_report(results)
    print(f"report -> {DOCS / 'validation_report.md'}")


if __name__ == "__main__":
    main()
