"""
Render interview report JSON as a simple paper-style HTML page.
"""

from __future__ import annotations

import html
from datetime import datetime
from typing import Any, Dict, List, Optional

_STOPPED_LABELS = {
    "none": "In progress",
    "completed_all_questions": "Completed all planned questions",
    "low_recent_average": "Ended early — rolling average below threshold",
    "abuse": "Ended — policy violation",
    "manual": "Ended manually",
}


def _esc(text: Any) -> str:
    return html.escape(str(text or ""), quote=True)


def _fmt_score(score: Optional[float]) -> str:
    if score is None:
        return "—"
    return f"{score:.1f}"


def _verdict_badge(score: int) -> str:
    if score >= 8:
        return '<span class="badge pass">Strong</span>'
    if score >= 6:
        return '<span class="badge mid">Adequate</span>'
    return '<span class="badge weak">Needs work</span>'


def render_not_completed_html(bot_id: str) -> str:
    """Friendly page when report is requested before interview ends."""
    bid = _esc(bot_id)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Report not ready</title>
  <style>
    body {{
      font-family: Georgia, "Times New Roman", serif;
      background: #f4f1ea;
      color: #2c2c2c;
      margin: 0;
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 2rem;
    }}
    .card {{
      background: #fff;
      border: 1px solid #d8d2c4;
      border-radius: 4px;
      max-width: 32rem;
      padding: 2rem 2.25rem;
      box-shadow: 0 2px 8px rgba(0,0,0,0.06);
    }}
    h1 {{ font-size: 1.35rem; margin: 0 0 0.75rem; }}
    p {{ line-height: 1.55; margin: 0 0 1rem; color: #444; }}
    .meta {{ font-size: 0.8rem; color: #777; word-break: break-all; }}
    .status {{ color: #9a6700; font-weight: bold; }}
  </style>
</head>
<body>
  <div class="card">
    <h1>Interview report not ready</h1>
    <p class="status">The interview is still in progress.</p>
    <p>
      The report card will be available after the AI delivers the closing message
      (e.g. &ldquo;Thank you for your time today&hellip;&rdquo;).
    </p>
    <p class="meta">Session: {bid}</p>
  </div>
</body>
</html>"""


def render_report_html(report: Dict[str, Any]) -> str:
    """Build a printable paper-style HTML report from build_report() output."""
    candidate = _esc(report.get("candidate_name") or "Candidate")
    bot_id = _esc(report.get("bot_id") or "")
    stopped = report.get("stopped_reason") or "none"
    stopped_label = _esc(_STOPPED_LABELS.get(stopped, stopped.replace("_", " ").title()))
    planned = report.get("questions_planned", 0)
    scored = report.get("questions_scored", 0)
    overall = report.get("overall_average")
    last4 = report.get("last_4_average")
    threshold = report.get("continue_threshold", 7.0)
    rolling_window = report.get("rolling_window", 4)
    abuse = report.get("abuse_warnings", 0)
    generated = datetime.now().strftime("%d %b %Y, %H:%M")

    per_q: List[dict] = report.get("per_question") or []
    develop: List[str] = report.get("summary_develop") or []
    fix_items: List[str] = report.get("summary_fix") or []
    planned_qs: List[dict] = report.get("planned_questions") or []
    transcript: List[str] = report.get("transcript") or []

    # Questions planned but not scored
    scored_ids = {r.get("question_id") for r in per_q}
    unreached_rows = ""
    for pq in planned_qs:
        if pq.get("id") in scored_ids:
            continue
        slot = pq.get("slot", "?")
        diff = _esc(pq.get("difficulty", ""))
        src = _esc(pq.get("source", ""))
        qtext = _esc(pq.get("question", ""))
        unreached_rows += (
            f"<tr><td>Q{slot}</td><td>{diff}</td><td>{src}</td>"
            f"<td class='muted'>{qtext}</td></tr>\n"
        )

    question_blocks = ""
    for r in per_q:
        idx = r.get("question_index", "?")
        diff = _esc(r.get("difficulty", ""))
        src = _esc(r.get("source", ""))
        score = int(r.get("score", 0))
        qtext = _esc(r.get("question_text", ""))
        atext = _esc(r.get("answer_text", ""))
        strengths = _esc(r.get("strengths", ""))
        develop_one = _esc(r.get("develop", ""))
        fix_one = _esc(r.get("fix", ""))
        confident = "Yes" if r.get("confident") else "No"
        relevant = "Yes" if r.get("relevant") else "No"

        question_blocks += f"""
        <section class="question-block">
          <div class="q-header">
            <h3>Question {idx} <span class="meta">[{diff} · {src}]</span></h3>
            <div class="score-line">Score: <strong>{score}/10</strong> {_verdict_badge(score)}</div>
          </div>
          <p class="label">Question</p>
          <p class="body">{qtext}</p>
          <p class="label">Candidate answer (excerpt)</p>
          <p class="body answer">{atext[:600]}{'…' if len(r.get('answer_text') or '') > 600 else ''}</p>
          <table class="mini-table">
            <tr><th>Confident</th><th>Relevant</th><th>Strengths</th></tr>
            <tr><td>{confident}</td><td>{relevant}</td><td>{strengths or '—'}</td></tr>
          </table>
          <div class="feedback-grid">
            <div><span class="label">Develop</span><p>{develop_one or '—'}</p></div>
            <div><span class="label">Improve</span><p>{fix_one or '—'}</p></div>
          </div>
        </section>
        """

    develop_list = "".join(f"<li>{_esc(d)}</li>" for d in develop) or "<li class='muted'>None noted</li>"
    fix_list = "".join(f"<li>{_esc(f)}</li>" for f in fix_items) or "<li class='muted'>None noted</li>"

    transcript_block = ""
    if transcript:
        lines = "".join(f"<div class='t-line'>{_esc(line)}</div>" for line in transcript[-40:])
        transcript_block = f"""
        <section class="section">
          <h2>Conversation transcript</h2>
          <div class="transcript">{lines}</div>
        </section>
        """

    unreached_section = ""
    if unreached_rows:
        unreached_section = f"""
        <section class="section">
          <h2>Questions not reached ({planned - scored})</h2>
          <table class="data-table">
            <thead><tr><th>#</th><th>Level</th><th>Source</th><th>Question</th></tr></thead>
            <tbody>{unreached_rows}</tbody>
          </table>
        </section>
        """

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Interview Report — {candidate}</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: Georgia, "Times New Roman", serif;
      background: #e8e8e8;
      color: #1a1a1a;
      line-height: 1.5;
      padding: 24px 12px;
    }}
    .page {{
      max-width: 800px;
      margin: 0 auto;
      background: #fff;
      padding: 48px 56px;
      box-shadow: 0 2px 12px rgba(0,0,0,.12);
    }}
    h1 {{
      font-size: 1.5rem;
      font-weight: normal;
      letter-spacing: 0.02em;
      border-bottom: 2px solid #1a1a1a;
      padding-bottom: 8px;
      margin-bottom: 4px;
    }}
    .subtitle {{ font-size: 0.9rem; color: #555; margin-bottom: 24px; }}
    h2 {{
      font-size: 1rem;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      border-bottom: 1px solid #ccc;
      padding-bottom: 4px;
      margin: 28px 0 12px;
    }}
    h3 {{ font-size: 1rem; font-weight: bold; margin-bottom: 4px; }}
    .meta {{ font-weight: normal; color: #666; font-size: 0.85rem; }}
    .summary-grid {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 12px 24px;
      margin: 16px 0;
      font-size: 0.95rem;
    }}
    .summary-grid dt {{ color: #555; }}
    .summary-grid dd {{ font-weight: bold; margin-bottom: 8px; }}
    .outcome {{
      border: 1px solid #1a1a1a;
      padding: 12px 16px;
      margin: 16px 0;
      font-size: 0.95rem;
    }}
    .question-block {{
      border: 1px solid #ddd;
      padding: 16px;
      margin-bottom: 16px;
      page-break-inside: avoid;
    }}
    .q-header {{
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      flex-wrap: wrap;
      gap: 8px;
      margin-bottom: 12px;
    }}
    .score-line {{ font-size: 0.95rem; }}
    .label {{
      font-size: 0.75rem;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: #666;
      margin-top: 8px;
    }}
    .body {{ font-size: 0.92rem; margin: 4px 0 8px; }}
    .answer {{ color: #333; font-style: italic; }}
    .mini-table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 0.85rem;
      margin: 8px 0;
    }}
    .mini-table th, .mini-table td {{
      border: 1px solid #ddd;
      padding: 6px 8px;
      text-align: left;
    }}
    .mini-table th {{ background: #f5f5f5; font-weight: normal; color: #555; }}
    .feedback-grid {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 12px;
      font-size: 0.88rem;
    }}
    .data-table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 0.85rem;
    }}
    .data-table th, .data-table td {{
      border: 1px solid #ddd;
      padding: 8px;
      text-align: left;
      vertical-align: top;
    }}
    .data-table th {{ background: #f5f5f5; }}
    ul {{ margin: 8px 0 8px 20px; font-size: 0.92rem; }}
    .badge {{
      display: inline-block;
      font-size: 0.7rem;
      padding: 2px 8px;
      border: 1px solid;
      margin-left: 6px;
      vertical-align: middle;
      font-family: sans-serif;
    }}
    .badge.pass {{ border-color: #2d6a2d; color: #2d6a2d; }}
    .badge.mid {{ border-color: #8a6d00; color: #8a6d00; }}
    .badge.weak {{ border-color: #a33; color: #a33; }}
    .muted {{ color: #888; }}
    .transcript {{
      font-family: "Courier New", monospace;
      font-size: 0.78rem;
      background: #fafafa;
      border: 1px solid #ddd;
      padding: 12px;
      max-height: 400px;
      overflow-y: auto;
    }}
    .t-line {{ margin-bottom: 4px; }}
    .footer {{
      margin-top: 32px;
      padding-top: 12px;
      border-top: 1px solid #ccc;
      font-size: 0.75rem;
      color: #888;
      text-align: center;
    }}
    @media print {{
      body {{ background: #fff; padding: 0; }}
      .page {{ box-shadow: none; padding: 24px; }}
    }}
  </style>
</head>
<body>
  <div class="page">
    <h1>Interview Report Card</h1>
    <p class="subtitle">Generated {generated}</p>

    <dl class="summary-grid">
      <dt>Candidate</dt><dd>{candidate}</dd>
      <dt>Session</dt><dd style="font-weight:normal;font-size:0.8rem;">{bot_id}</dd>
      <dt>Questions scored</dt><dd>{scored} / {planned}</dd>
      <dt>Overall average</dt><dd>{_fmt_score(overall)} / 10</dd>
      <dt>Last {rolling_window} average</dt><dd>{_fmt_score(last4)} / 10</dd>
      <dt>Continue threshold</dt><dd>{threshold}</dd>
      <dt>Abuse warnings</dt><dd>{abuse}</dd>
    </dl>

    <div class="outcome">
      <strong>Outcome:</strong> {stopped_label}
    </div>

    <section class="section">
      <h2>Question-by-question</h2>
      {question_blocks or '<p class="muted">No scored answers yet.</p>'}
    </section>

    {unreached_section}

    <section class="section">
      <h2>Key areas to develop</h2>
      <ul>{develop_list}</ul>
    </section>

    <section class="section">
      <h2>Key areas to improve</h2>
      <ul>{fix_list}</ul>
    </section>

    {transcript_block}

    <p class="footer">Speech Agent · Confidential interview assessment</p>
  </div>
</body>
</html>"""
