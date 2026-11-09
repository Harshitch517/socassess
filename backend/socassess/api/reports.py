"""PDF and CSV report exports (reportlab, offline)."""

from __future__ import annotations

import io
import json
from datetime import UTC, datetime

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

SEV_COLOURS = {"critical": "#b42318", "high": "#c4320a", "medium": "#b54708", "low": "#475467"}
_styles = getSampleStyleSheet()
H1, H2, BODY = _styles["Title"], _styles["Heading2"], _styles["BodyText"]
SMALL = ParagraphStyle("small", parent=BODY, fontSize=8, leading=10)


def _esc(s) -> str:
    return (str(s) if s is not None else "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _table(rows: list[list], widths: list[float]) -> Table:
    data = [[Paragraph(_esc(c), SMALL) for c in r] for r in rows]
    t = Table(data, colWidths=[w * mm for w in widths], repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eaecf0")),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#d0d5dd")),
        ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    return t


def _footer(run: dict):
    def draw(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.drawString(15 * mm, 10 * mm,
                          f"SOCAssess | run {run.get('run_id')} | input {str(run.get('input_hash'))[:12]} "
                          f"| code {run.get('code_version')} | page {doc.page}")
        canvas.restoreState()
    return draw


def _finding_block(f: dict) -> list:
    col = SEV_COLOURS.get(f["severity"], "#475467")
    return [Paragraph(f"<font color='{col}'><b>[{f['severity'].upper()}]</b></font> <b>{_esc(f['title'])}</b> "
                      f"<font size=8 color='#667085'>({_esc(f['type'])}, {f['n_evidence']} evidence records, "
                      f"{f['points']:.1f} pts)</font>", BODY),
            Paragraph(_esc(f["rationale"]), SMALL), Spacer(1, 3 * mm)]


def summary_pdf(run: dict, scores: list[dict], findings: list[dict]) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=15 * mm,
                            bottomMargin=18 * mm, title="SOCAssess supervisory report")
    story = [Paragraph("SOCAssess supervisory report", H1),
             Paragraph(f"Generated {datetime.now(UTC):%Y-%m-%d %H:%M} UTC from analysis run {run['run_id']} "
                       f"({run['started_at'][:19]}). {len(scores)} entities, {len(findings)} findings.", BODY),
             Spacer(1, 4 * mm), Paragraph("Entity risk ranking", H2)]
    rows = [["#", "Entity", "Sector / size", "Score", "Band", "Findings", "Top driver"]]
    for s in scores:
        top = s["breakdown"][0]["title"] if s["breakdown"] else ""
        rows.append([s["rank"], f"{s['entity_id']} {s['name']}", f"{s['sector']} / {s['size']}",
                     f"{s['risk_score']:.1f}", s["band"], s["n_findings"], top])
    story.append(_table(rows, [8, 48, 28, 14, 16, 15, 51]))
    story += [PageBreak(), Paragraph("Findings by entity", H2)]
    by_entity: dict[str, list] = {}
    for f in findings:
        by_entity.setdefault(f["entity_id"], []).append(f)
    for s in scores:
        fs = by_entity.get(s["entity_id"])
        if not fs:
            continue
        story.append(Paragraph(f"{_esc(s['entity_id'])} {_esc(s['name'])}: score {s['risk_score']:.1f} ({s['band']})",
                               _styles["Heading3"]))
        for f in sorted(fs, key=lambda f: -f["points"]):
            story += _finding_block(f)
    doc.build(story, onFirstPage=_footer(run), onLaterPages=_footer(run))
    return buf.getvalue()


def entity_pdf(run: dict, entity: dict, score: dict, findings: list[dict], benchmarks: list[dict],
               queue: list[dict]) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=15 * mm,
                            bottomMargin=18 * mm, title=f"SOCAssess {entity['entity_id']}")
    story = [Paragraph(f"{_esc(entity['entity_id'])}: {_esc(entity['name'])}", H1),
             Paragraph(f"Sector {entity['sector']}, size {entity['size']}. Risk score <b>{score['risk_score']:.1f}</b> "
                       f"({score['band']}), rank {score['rank']}. Run {run['run_id']}.", BODY),
             Spacer(1, 3 * mm), Paragraph("Score breakdown", H2)]
    rows = [["Finding", "Type", "Severity", "Weight", "x", "Points"]]
    rows += [[b["title"], b["type"], b["severity"], b["weight"], b["multiplier"], f"{b['points']:.2f}"]
             for b in score["breakdown"]] or [["No findings", "", "", "", "", "0"]]
    story += [_table(rows, [70, 40, 20, 15, 10, 15]), Paragraph("Findings", H2)]
    for f in sorted(findings, key=lambda f: -f["points"]):
        story += _finding_block(f)
    story.append(Paragraph("Peer comparison", H2))
    rows = [["Metric", "Value", "Peer median (all)", "Peer median (size)", "Percentile", "z"]]
    for b in benchmarks:
        rows.append([b["description"], _num(b["value"]), _num(b["peer_median_all"]), _num(b["peer_median_size"]),
                     _num(b["percentile"]), _num(b["z"])])
    story += [_table(rows, [66, 20, 26, 26, 20, 12]), Paragraph("Records to review", H2)]
    rows = [["#", "Type", "Record", "Reason"]] + [[q["rank"], q["record_type"], q["record_id"], q["reason"]]
                                                  for q in queue[:30]]
    story.append(_table(rows, [10, 18, 45, 107]))
    doc.build(story, onFirstPage=_footer(run), onLaterPages=_footer(run))
    return buf.getvalue()


def _num(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    return f"{v:.3g}" if isinstance(v, float) else str(v)


def to_csv(rows: list[dict]) -> str:
    df = pd.DataFrame(rows)
    for c in df.columns:
        if df[c].map(lambda v: isinstance(v, (list, dict))).any():
            df[c] = df[c].map(lambda v: v if not isinstance(v, (list, dict)) else json.dumps(v))
    return df.to_csv(index=False)
