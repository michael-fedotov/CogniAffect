"""
BWS Empathy Annotation - Flask Backend

Serves the annotation app and collects annotations in a SQLite database.

Usage:
    python server.py

Then open http://localhost:5000 in a browser.
Admin dashboard: http://localhost:5000/admin
"""

import sqlite3
import json
import csv
import io
import os
import argparse
from collections import defaultdict
from datetime import datetime, timezone
from flask import Flask, request, jsonify, send_from_directory, Response
from flask_cors import CORS

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "https://michael-fedotov.github.io/CogniAffect/"}})

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "annotations.db")

# Vite production build output lives at <project-root>/dist/
# Fall back to serving the legacy index.html if dist/ hasn't been built yet.
DIST_DIR = os.path.join(BASE_DIR, "dist")

CSV_COLUMNS = [
    "annotation_id", "annotator_id", "scenario_id", "context_snippet",
    "response_a_label", "response_b_label", "response_c_label",
    "cognitive_most", "cognitive_least", "cognitive_reasoning",
    "affective_most", "affective_least", "affective_reasoning",
    "timestamp", "session_duration_seconds",
]

# ── Database ──────────────────────────────────────────────────────────────────

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS annotations (
                id                      INTEGER PRIMARY KEY AUTOINCREMENT,
                annotation_id           TEXT    UNIQUE NOT NULL,
                annotator_id            TEXT    NOT NULL,
                scenario_id             TEXT    NOT NULL,
                context_snippet         TEXT    DEFAULT '',
                response_a_label        TEXT    DEFAULT '',
                response_b_label        TEXT    DEFAULT '',
                response_c_label        TEXT    DEFAULT '',
                cognitive_most          TEXT    DEFAULT '',
                cognitive_least         TEXT    DEFAULT '',
                cognitive_reasoning     TEXT    DEFAULT '',
                affective_most          TEXT    DEFAULT '',
                affective_least         TEXT    DEFAULT '',
                affective_reasoning     TEXT    DEFAULT '',
                timestamp               TEXT    DEFAULT '',
                session_duration_seconds TEXT   DEFAULT '',
                is_complete             INTEGER DEFAULT 0,
                created_at              TEXT    DEFAULT CURRENT_TIMESTAMP,
                updated_at              TEXT    DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS sessions (
                annotator_id TEXT    PRIMARY KEY,
                session_data TEXT    NOT NULL,
                updated_at   TEXT    DEFAULT CURRENT_TIMESTAMP
            );
        """)


init_db()

# ── Static files ──────────────────────────────────────────────────────────────

def _dist_built():
    """Return True when the Vite build output exists."""
    return os.path.isfile(os.path.join(DIST_DIR, "index.html"))


@app.route("/")
def index():
    if _dist_built():
        return send_from_directory(DIST_DIR, "index.html")
    # Legacy fallback: serve the original single-file app
    return send_from_directory(BASE_DIR, "index.html")


@app.route("/assets/<path:filename>")
def vite_assets(filename):
    """Serve Vite-hashed JS/CSS bundles from dist/assets/."""
    return send_from_directory(os.path.join(DIST_DIR, "assets"), filename)


@app.route("/scenarios.json")
def scenarios_json():
    return send_from_directory(BASE_DIR, "scenarios.json")


# ── Session API ───────────────────────────────────────────────────────────────

@app.route("/api/session/<annotator_id>", methods=["GET"])
def get_session(annotator_id):
    with get_db() as conn:
        row = conn.execute(
            "SELECT session_data FROM sessions WHERE annotator_id = ?",
            (annotator_id,),
        ).fetchone()
    if not row:
        return jsonify(None), 404
    try:
        return jsonify(json.loads(row["session_data"]))
    except Exception:
        return jsonify(None), 500


# ── Sync API ──────────────────────────────────────────────────────────────────

@app.route("/api/sync", methods=["POST"])
def sync():
    data = request.get_json(force=True)
    if not data or "annotator_id" not in data:
        return jsonify({"error": "Missing annotator_id"}), 400

    annotator_id = data["annotator_id"]
    session_data = data.get("session_data", {})
    scenarios_list = data.get("scenarios", [])

    scenarios_map = {s["scenario_id"]: s for s in scenarios_list}
    now = datetime.now(timezone.utc).isoformat()

    with get_db() as conn:
        # Upsert full session blob (used for resume)
        conn.execute(
            "INSERT OR REPLACE INTO sessions (annotator_id, session_data, updated_at) VALUES (?, ?, ?)",
            (annotator_id, json.dumps(session_data), now),
        )

        annotations = session_data.get("annotations", {})
        shuffle_maps = session_data.get("shuffle_maps", {})
        original_ids = ["A", "B", "C"]

        for scenario_id, ann in annotations.items():
            scenario = scenarios_map.get(scenario_id, {})

            # Compute annotation_id using scenario's position in the ordered list
            idx = next(
                (i for i, s in enumerate(scenarios_list) if s["scenario_id"] == scenario_id),
                0,
            )
            annotation_id = f"{annotator_id}_S{str(idx + 1).zfill(2)}"

            # Map display positions back to ground-truth labels
            shuffle_map = shuffle_maps.get(scenario_id, [0, 1, 2])
            ground_truth = scenario.get("ground_truth_labels", {})

            def label_at(display_pos):
                orig_idx = shuffle_map[display_pos] if display_pos < len(shuffle_map) else display_pos
                orig_id = original_ids[orig_idx] if orig_idx < len(original_ids) else ""
                return ground_truth.get(orig_id, "")

            a_label = label_at(0)
            b_label = label_at(1)
            c_label = label_at(2)

            context_snippet = scenario.get("context", "")[:100].replace("\n", " ")

            start_time = ann.get("startTime")
            end_time = ann.get("endTime")
            duration = str(round((end_time - start_time) / 1000)) if start_time and end_time else ""
            timestamp = (
                datetime.fromtimestamp(end_time / 1000, tz=timezone.utc).isoformat()
                if end_time
                else ""
            )

            cog_most = ann.get("cognitiveMost", "")
            cog_least = ann.get("cognitiveLeast", "")
            aff_most = ann.get("affectiveMost", "")
            aff_least = ann.get("affectiveLeast", "")
            is_complete = int(
                bool(cog_most) and bool(cog_least)
                and bool(aff_most) and bool(aff_least)
                and cog_most != cog_least
                and aff_most != aff_least
            )

            conn.execute(
                """
                INSERT INTO annotations
                    (annotation_id, annotator_id, scenario_id, context_snippet,
                     response_a_label, response_b_label, response_c_label,
                     cognitive_most, cognitive_least, cognitive_reasoning,
                     affective_most, affective_least, affective_reasoning,
                     timestamp, session_duration_seconds, is_complete, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(annotation_id) DO UPDATE SET
                    context_snippet          = excluded.context_snippet,
                    response_a_label         = excluded.response_a_label,
                    response_b_label         = excluded.response_b_label,
                    response_c_label         = excluded.response_c_label,
                    cognitive_most           = excluded.cognitive_most,
                    cognitive_least          = excluded.cognitive_least,
                    cognitive_reasoning      = excluded.cognitive_reasoning,
                    affective_most           = excluded.affective_most,
                    affective_least          = excluded.affective_least,
                    affective_reasoning      = excluded.affective_reasoning,
                    timestamp                = excluded.timestamp,
                    session_duration_seconds = excluded.session_duration_seconds,
                    is_complete              = excluded.is_complete,
                    updated_at               = excluded.updated_at
                """,
                (
                    annotation_id, annotator_id, scenario_id, context_snippet,
                    a_label, b_label, c_label,
                    cog_most, cog_least, ann.get("cognitiveReasoning", ""),
                    aff_most, aff_least, ann.get("affectiveReasoning", ""),
                    timestamp, duration, is_complete, now,
                ),
            )

        conn.commit()

    return jsonify({"status": "ok", "synced_at": now})


# ── Export API ────────────────────────────────────────────────────────────────

def rows_to_csv_string(rows):
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow(dict(row))
    return output.getvalue()


@app.route("/api/export/csv")
def export_all_csv():
    with get_db() as conn:
        rows = conn.execute(
            f"SELECT {', '.join(CSV_COLUMNS)} FROM annotations ORDER BY annotator_id, scenario_id"
        ).fetchall()
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"all_annotations_{ts}.csv"
    return Response(
        rows_to_csv_string(rows),
        mimetype="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.route("/api/export/csv/<annotator_id>")
def export_annotator_csv(annotator_id):
    with get_db() as conn:
        rows = conn.execute(
            f"SELECT {', '.join(CSV_COLUMNS)} FROM annotations WHERE annotator_id = ? ORDER BY scenario_id",
            (annotator_id,),
        ).fetchall()
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"annotations_{annotator_id}_{ts}.csv"
    return Response(
        rows_to_csv_string(rows),
        mimetype="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── Admin API ─────────────────────────────────────────────────────────────────

@app.route("/api/annotators")
def list_annotators():
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT annotator_id,
                   COUNT(*) AS total_annotations,
                   SUM(is_complete) AS completed_annotations,
                   MAX(updated_at) AS last_active
            FROM annotations
            GROUP BY annotator_id
            ORDER BY last_active DESC
            """
        ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/status")
def status():
    with get_db() as conn:
        total = conn.execute("SELECT COUNT(*) FROM annotations").fetchone()[0]
        complete = conn.execute(
            "SELECT COUNT(*) FROM annotations WHERE is_complete = 1"
        ).fetchone()[0]
        annotators = conn.execute(
            "SELECT COUNT(DISTINCT annotator_id) FROM annotations"
        ).fetchone()[0]
    return jsonify(
        {
            "total_annotations": total,
            "complete_annotations": complete,
            "annotator_count": annotators,
            "db_path": DB_PATH,
        }
    )


# ── BWS Scoring ───────────────────────────────────────────────────────────────

def compute_bws_scores(rows, dimension):
    """Port of get-scores-from-BWS-annotations-counting.pl (Kiritchenko & Turney).

    For each completed annotation row, the 3-tuple items are the ground-truth
    labels at display positions A, B, C.  BestItem / WorstItem are resolved by
    mapping the display letter the annotator chose back to its ground-truth label.

    Returns dict { item_label: score } sorted by score descending.
    Score = (times_chosen_best - times_chosen_worst) / times_appeared.
    """
    count_item = defaultdict(int)
    count_best = defaultdict(int)
    count_worst = defaultdict(int)

    most_col = f"{dimension}_most"
    least_col = f"{dimension}_least"

    for row in rows:
        items = [row["response_a_label"], row["response_b_label"], row["response_c_label"]]
        for item in items:
            if item:
                count_item[item] += 1

        best_letter = (row[most_col] or "").strip().upper()
        worst_letter = (row[least_col] or "").strip().upper()
        if not best_letter or not worst_letter:
            continue

        best_item = row.get(f"response_{best_letter.lower()}_label", "")
        worst_item = row.get(f"response_{worst_letter.lower()}_label", "")
        if best_item:
            count_best[best_item] += 1
        if worst_item:
            count_worst[worst_item] += 1

    scores = {}
    for item in count_item:
        if count_item[item] == 0:
            continue
        scores[item] = round(
            (count_best.get(item, 0) - count_worst.get(item, 0)) / count_item[item],
            4,
        )
    return dict(sorted(scores.items(), key=lambda x: -x[1]))


@app.route("/api/scores")
def scores():
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM annotations WHERE is_complete = 1"
        ).fetchall()
    rows = [dict(r) for r in rows]

    if not rows:
        return jsonify({
            "cognitive": {},
            "affective": {},
            "per_scenario": {},
            "meta": {"total_annotations": 0, "annotator_count": 0, "scenario_count": 0},
        })

    cognitive_overall = compute_bws_scores(rows, "cognitive")
    affective_overall = compute_bws_scores(rows, "affective")

    scenario_ids = sorted(set(r["scenario_id"] for r in rows))
    per_scenario = {}
    for sid in scenario_ids:
        scenario_rows = [r for r in rows if r["scenario_id"] == sid]
        per_scenario[sid] = {
            "cognitive": compute_bws_scores(scenario_rows, "cognitive"),
            "affective": compute_bws_scores(scenario_rows, "affective"),
            "n": len(scenario_rows),
        }

    return jsonify({
        "cognitive": cognitive_overall,
        "affective": affective_overall,
        "per_scenario": per_scenario,
        "meta": {
            "total_annotations": len(rows),
            "annotator_count": len(set(r["annotator_id"] for r in rows)),
            "scenario_count": len(scenario_ids),
        },
    })


# ── Admin Dashboard ───────────────────────────────────────────────────────────

@app.route("/admin")
def admin():
    return """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>BWS Annotation Admin</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <style>
    .bar-pos { background: #10B981; }
    .bar-neg { background: #EF4444; }
    .bar-wrap { position: relative; height: 1.25rem; background: #F1F5F9; border-radius: 6px; overflow: hidden; }
    .bar-center { position: absolute; left: 50%; top: 0; bottom: 0; width: 1px; background: #94A3B8; z-index: 1; }
    .bar-fill { position: absolute; top: 2px; bottom: 2px; border-radius: 4px; z-index: 2; transition: width 0.4s; }
    .heatcell { min-width: 3.5rem; text-align: center; font-size: 0.75rem; font-weight: 600; border-radius: 6px; padding: 4px 6px; }
  </style>
</head>
<body class="bg-slate-50 min-h-screen">
  <div class="max-w-4xl mx-auto px-6 py-10">

    <!-- Header -->
    <div class="flex items-center justify-between mb-8">
      <div>
        <h1 class="text-2xl font-bold text-slate-800">BWS Annotation Admin</h1>
        <p class="text-slate-500 text-sm mt-1">Collected annotation data across all annotators</p>
      </div>
      <a href="/" class="text-sm text-indigo-600 hover:underline">Back to app</a>
    </div>

    <!-- Status overview -->
    <div id="status-card" class="bg-white rounded-2xl border border-slate-200 shadow-sm p-6 mb-6">
      <div class="animate-pulse h-20 bg-slate-100 rounded-xl"></div>
    </div>

    <!-- Annotators -->
    <div id="annotators-card" class="bg-white rounded-2xl border border-slate-200 shadow-sm p-6 mb-6">
      <div class="animate-pulse h-40 bg-slate-100 rounded-xl"></div>
    </div>

    <!-- BWS Scores -->
    <div id="scores-card" class="bg-white rounded-2xl border border-slate-200 shadow-sm p-6 mb-6">
      <div class="animate-pulse h-40 bg-slate-100 rounded-xl"></div>
    </div>

    <!-- Per-scenario breakdown -->
    <div id="scenario-card" class="bg-white rounded-2xl border border-slate-200 shadow-sm p-6 mb-6">
      <div class="animate-pulse h-40 bg-slate-100 rounded-xl"></div>
    </div>

    <!-- Actions -->
    <div class="flex flex-wrap gap-3 mb-10">
      <a href="/api/export/csv"
         class="inline-flex items-center gap-2 bg-indigo-600 text-white px-5 py-2.5 rounded-xl font-semibold text-sm hover:bg-indigo-700 transition-all shadow-sm">
        <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
          <path stroke-linecap="round" stroke-linejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"/>
        </svg>
        Download All Annotations (CSV)
      </a>
      <a href="/api/scores" target="_blank"
         class="inline-flex items-center gap-2 border-2 border-slate-200 text-slate-600 px-5 py-2.5 rounded-xl font-semibold text-sm hover:bg-slate-50 transition-all">
        Raw Scores JSON
      </a>
      <button onclick="loadScores()" id="refresh-btn"
         class="inline-flex items-center gap-2 border-2 border-emerald-300 text-emerald-700 px-5 py-2.5 rounded-xl font-semibold text-sm hover:bg-emerald-50 transition-all">
        <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
          <path stroke-linecap="round" stroke-linejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/>
        </svg>
        Recalculate Scores
      </button>
    </div>
  </div>

  <script>
    // ── Helpers ───────────────────────────────────────────────────────────────
    const LABELS = { HUMAN: 'Human', LLM_COGNITIVE: 'LLM Cognitive', LLM_AFFECTIVE: 'LLM Affective' };
    const LABEL_COLORS = { HUMAN: 'indigo', LLM_COGNITIVE: 'sky', LLM_AFFECTIVE: 'violet' };

    function stat(val, label, color) {
      const bg = 'bg-' + color + '-50';
      const tx = 'text-' + color + '-700';
      const sub = 'text-' + color + '-500';
      return '<div class="' + bg + ' rounded-xl p-4 text-center">' +
             '<p class="text-2xl font-bold ' + tx + '">' + val + '</p>' +
             '<p class="text-xs ' + sub + ' mt-1">' + label + '</p></div>';
    }

    function scoreBar(score) {
      var pct = Math.abs(score) * 50;
      var cls = score >= 0 ? 'bar-pos' : 'bar-neg';
      var left = score >= 0 ? '50%' : (50 - pct) + '%';
      return '<div class="bar-wrap">' +
             '<div class="bar-center"></div>' +
             '<div class="bar-fill ' + cls + '" style="left:' + left + ';width:' + pct + '%;"></div>' +
             '</div>';
    }

    function rankLabel(rank) {
      if (rank === 1) return '<span class="text-emerald-600 font-bold">#1</span>';
      if (rank === 2) return '<span class="text-amber-500 font-bold">#2</span>';
      return '<span class="text-slate-400 font-bold">#' + rank + '</span>';
    }

    function heatColor(score) {
      if (score > 0.3) return 'background:#D1FAE5;color:#065F46;';
      if (score > 0) return 'background:#ECFDF5;color:#047857;';
      if (score > -0.3) return 'background:#FEF2F2;color:#991B1B;';
      return 'background:#FEE2E2;color:#7F1D1D;';
    }

    function friendlyName(key) { return LABELS[key] || key; }

    // ── Status ───────────────────────────────────────────────────────────────
    fetch('/api/status').then(r => r.json()).then(d => {
      document.getElementById('status-card').innerHTML =
        '<h2 class="text-xs font-bold uppercase tracking-widest text-slate-500 mb-4">Overview</h2>' +
        '<div class="grid grid-cols-3 gap-4">' +
        stat(d.annotator_count, 'Annotators', 'indigo') +
        stat(d.complete_annotations, 'Complete Rows', 'emerald') +
        stat(d.total_annotations, 'Total Rows Saved', 'slate') +
        '</div>';
    }).catch(() => {
      document.getElementById('status-card').innerHTML = '<p class="text-red-500 text-sm">Error loading status.</p>';
    });

    // ── Annotators ───────────────────────────────────────────────────────────
    fetch('/api/annotators').then(r => r.json()).then(data => {
      if (!data.length) {
        document.getElementById('annotators-card').innerHTML =
          '<p class="text-slate-400 text-sm">No annotations have been submitted yet.</p>';
        return;
      }
      var html = '<h2 class="text-xs font-bold uppercase tracking-widest text-slate-500 mb-4">Annotators (' + data.length + ')</h2>';
      html += '<div class="divide-y divide-slate-100">';
      data.forEach(function(a) {
        var pct = a.total_annotations > 0 ? Math.round((a.completed_annotations / a.total_annotations) * 100) : 0;
        var lastActive = a.last_active ? new Date(a.last_active).toLocaleString() : 'unknown';
        html += '<div class="py-3 flex items-center justify-between gap-4">' +
          '<div class="min-w-0">' +
          '<p class="font-mono font-semibold text-slate-800 text-sm">' + a.annotator_id + '</p>' +
          '<p class="text-xs text-slate-500 mt-0.5">' +
            a.completed_annotations + ' complete / ' + a.total_annotations + ' saved' +
            ' &middot; Last active: ' + lastActive +
          '</p>' +
          '<div class="flex items-center gap-2 mt-1.5">' +
            '<div class="w-24 h-1.5 bg-slate-100 rounded-full"><div class="h-1.5 bg-emerald-500 rounded-full" style="width:' + pct + '%"></div></div>' +
            '<span class="text-xs text-slate-400">' + pct + '%</span>' +
          '</div></div>' +
          '<a href="/api/export/csv/' + encodeURIComponent(a.annotator_id) + '"' +
             ' class="flex-shrink-0 text-xs text-indigo-600 hover:underline font-medium">Download CSV</a></div>';
      });
      html += '</div>';
      document.getElementById('annotators-card').innerHTML = html;
    }).catch(function() {
      document.getElementById('annotators-card').innerHTML = '<p class="text-red-500 text-sm">Error loading annotators.</p>';
    });

    // ── BWS Scores ───────────────────────────────────────────────────────────
    function loadScores() {
      document.getElementById('scores-card').innerHTML = '<div class="animate-pulse h-40 bg-slate-100 rounded-xl"></div>';
      document.getElementById('scenario-card').innerHTML = '<div class="animate-pulse h-40 bg-slate-100 rounded-xl"></div>';

      fetch('/api/scores').then(r => r.json()).then(function(d) {
        renderScores(d);
        renderPerScenario(d);
      }).catch(function() {
        document.getElementById('scores-card').innerHTML = '<p class="text-red-500 text-sm">Error loading scores.</p>';
        document.getElementById('scenario-card').innerHTML = '';
      });
    }

    function renderScores(d) {
      var meta = d.meta;
      if (meta.total_annotations < 1) {
        document.getElementById('scores-card').innerHTML =
          '<h2 class="text-xs font-bold uppercase tracking-widest text-slate-500 mb-4">BWS Scores</h2>' +
          '<p class="text-slate-400 text-sm">Not enough completed annotations to compute scores. Need at least 1.</p>';
        return;
      }

      var cog = d.cognitive;
      var aff = d.affective;
      var cogKeys = Object.keys(cog).sort(function(a, b) { return cog[b] - cog[a]; });
      var affKeys = Object.keys(aff).sort(function(a, b) { return aff[b] - aff[a]; });

      // Insight callout
      var insight = '';
      if (cogKeys.length > 0 && affKeys.length > 0) {
        var cogTop = cogKeys[0];
        var affTop = affKeys[0];
        insight = '<div class="bg-indigo-50 rounded-xl p-4 mb-5">' +
          '<p class="text-sm text-indigo-900">' +
          '<span class="font-bold">' + friendlyName(cogTop) + '</span> ranks <span class="font-bold text-emerald-700">#1</span> on cognitive empathy (score: ' + cog[cogTop].toFixed(3) + '). ' +
          '<span class="font-bold">' + friendlyName(affTop) + '</span> ranks <span class="font-bold text-emerald-700">#1</span> on affective empathy (score: ' + aff[affTop].toFixed(3) + ').' +
          '</p>' +
          '<p class="text-xs text-indigo-600 mt-1">Based on ' + meta.total_annotations + ' completed annotations from ' + meta.annotator_count + ' annotator' + (meta.annotator_count !== 1 ? 's' : '') + ' across ' + meta.scenario_count + ' scenario' + (meta.scenario_count !== 1 ? 's' : '') + '.</p>' +
          '</div>';
      }

      // Score tables
      function scoreTable(title, color, items) {
        var keys = Object.keys(items).sort(function(a, b) { return items[b] - items[a]; });
        var html = '<div class="flex-1 min-w-[260px]">' +
          '<h3 class="text-sm font-bold text-' + color + '-700 mb-3">' + title + '</h3>' +
          '<div class="space-y-3">';
        keys.forEach(function(key, i) {
          var sc = items[key];
          html += '<div>' +
            '<div class="flex items-center justify-between mb-1">' +
            '<div class="flex items-center gap-2">' + rankLabel(i + 1) +
            ' <span class="text-sm font-semibold text-slate-800">' + friendlyName(key) + '</span></div>' +
            '<span class="text-sm font-mono font-bold ' + (sc >= 0 ? 'text-emerald-600' : 'text-red-500') + '">' + sc.toFixed(3) + '</span>' +
            '</div>' + scoreBar(sc) + '</div>';
        });
        html += '</div></div>';
        return html;
      }

      document.getElementById('scores-card').innerHTML =
        '<h2 class="text-xs font-bold uppercase tracking-widest text-slate-500 mb-4">BWS Scores &mdash; Overall Rankings</h2>' +
        insight +
        '<div class="flex flex-wrap gap-8">' +
        scoreTable('Cognitive Empathy', 'indigo', cog) +
        scoreTable('Affective Empathy', 'violet', aff) +
        '</div>';
    }

    function renderPerScenario(d) {
      var ps = d.per_scenario;
      var sids = Object.keys(ps);
      if (sids.length < 1) {
        document.getElementById('scenario-card').innerHTML = '';
        return;
      }

      var allItems = new Set();
      sids.forEach(function(sid) {
        Object.keys(ps[sid].cognitive).forEach(function(k) { allItems.add(k); });
        Object.keys(ps[sid].affective).forEach(function(k) { allItems.add(k); });
      });
      var items = Array.from(allItems).sort();

      function heatTable(title, dimension) {
        var html = '<h3 class="text-sm font-bold text-slate-700 mb-2">' + title + '</h3>' +
          '<div class="overflow-x-auto"><table class="w-full text-left border-collapse">' +
          '<thead><tr><th class="text-xs font-bold text-slate-500 pb-2 pr-3">Scenario</th>';
        items.forEach(function(item) {
          html += '<th class="text-xs font-bold text-slate-500 pb-2 px-1 text-center">' + friendlyName(item) + '</th>';
        });
        html += '<th class="text-xs font-bold text-slate-500 pb-2 pl-3 text-center">n</th></tr></thead><tbody>';

        sids.forEach(function(sid) {
          var scores = ps[sid][dimension];
          html += '<tr class="border-t border-slate-100"><td class="py-1.5 pr-3 text-xs font-mono text-slate-600">' + sid.replace('_', ' ') + '</td>';
          items.forEach(function(item) {
            var sc = scores[item];
            if (sc === undefined) {
              html += '<td class="py-1.5 px-1"><div class="heatcell" style="background:#F8FAFC;color:#94A3B8;">-</div></td>';
            } else {
              html += '<td class="py-1.5 px-1"><div class="heatcell" style="' + heatColor(sc) + '">' + sc.toFixed(2) + '</div></td>';
            }
          });
          html += '<td class="py-1.5 pl-3 text-xs text-slate-400 text-center">' + ps[sid].n + '</td></tr>';
        });

        html += '</tbody></table></div>';
        return html;
      }

      document.getElementById('scenario-card').innerHTML =
        '<h2 class="text-xs font-bold uppercase tracking-widest text-slate-500 mb-4">Per-Scenario Breakdown</h2>' +
        '<div class="space-y-6">' +
        heatTable('Cognitive Empathy by Scenario', 'cognitive') +
        heatTable('Affective Empathy by Scenario', 'affective') +
        '</div>';
    }

    // Auto-load scores on page load
    loadScores();
  </script>
</body>
</html>"""


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="BWS Empathy Annotation Server")
    parser.add_argument(
        "--port", "-p",
        type=int,
        default=int(os.environ.get("PORT", 5000)),
        help="Port to listen on (default: 5000, or $PORT env var)",
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host to bind to (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable Flask debug mode with auto-reload",
    )
    args = parser.parse_args()

    print()
    print("  BWS Empathy Annotation Server")
    print("  ─────────────────────────────────────────")
    print(f"  App:      http://localhost:{args.port}")
    print(f"  Admin:    http://localhost:{args.port}/admin")
    print(f"  Export:   http://localhost:{args.port}/api/export/csv")
    print(f"  Database: {DB_PATH}")
    print()
    app.run(debug=args.debug, host=args.host, port=args.port)
