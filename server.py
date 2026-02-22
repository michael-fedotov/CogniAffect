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
from datetime import datetime, timezone
from flask import Flask, request, jsonify, send_from_directory, Response

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "annotations.db")

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

@app.route("/")
def index():
    return send_from_directory(BASE_DIR, "annotation_app.html")


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
</head>
<body class="bg-slate-50 min-h-screen">
  <div class="max-w-3xl mx-auto px-6 py-10">
    <div class="flex items-center justify-between mb-8">
      <div>
        <h1 class="text-2xl font-bold text-slate-800">BWS Annotation Admin</h1>
        <p class="text-slate-500 text-sm mt-1">Collected annotation data across all annotators</p>
      </div>
      <a href="/" class="text-sm text-indigo-600 hover:underline">Back to app</a>
    </div>

    <div id="status-card" class="bg-white rounded-2xl border border-slate-200 shadow-sm p-6 mb-6">
      <div class="animate-pulse h-20 bg-slate-100 rounded-xl"></div>
    </div>

    <div id="annotators-card" class="bg-white rounded-2xl border border-slate-200 shadow-sm p-6 mb-6">
      <div class="animate-pulse h-40 bg-slate-100 rounded-xl"></div>
    </div>

    <div class="flex flex-wrap gap-3">
      <a href="/api/export/csv"
         class="inline-flex items-center gap-2 bg-indigo-600 text-white px-5 py-2.5 rounded-xl font-semibold text-sm hover:bg-indigo-700 transition-all shadow-sm">
        <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
          <path stroke-linecap="round" stroke-linejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"/>
        </svg>
        Download All Annotations (CSV)
      </a>
      <a href="/api/status" target="_blank"
         class="inline-flex items-center gap-2 border-2 border-slate-200 text-slate-600 px-5 py-2.5 rounded-xl font-semibold text-sm hover:bg-slate-50 transition-all">
        Raw Status JSON
      </a>
    </div>
  </div>

  <script>
    fetch('/api/status').then(r => r.json()).then(d => {
      document.getElementById('status-card').innerHTML =
        '<h2 class="text-xs font-bold uppercase tracking-widest text-slate-500 mb-4">Overview</h2>' +
        '<div class="grid grid-cols-3 gap-4">' +
        stat(d.annotator_count, 'Annotators', 'indigo') +
        stat(d.complete_annotations, 'Complete Rows', 'emerald') +
        stat(d.total_annotations, 'Total Rows Saved', 'slate') +
        '</div>';
    }).catch(() => {
      document.getElementById('status-card').innerHTML =
        '<p class="text-red-500 text-sm">Server error loading status.</p>';
    });

    fetch('/api/annotators').then(r => r.json()).then(data => {
      if (!data.length) {
        document.getElementById('annotators-card').innerHTML =
          '<p class="text-slate-400 text-sm">No annotations have been submitted yet.</p>';
        return;
      }
      let html = '<h2 class="text-xs font-bold uppercase tracking-widest text-slate-500 mb-4">Annotators (' + data.length + ')</h2>';
      html += '<div class="divide-y divide-slate-100">';
      data.forEach(a => {
        const pct = a.total_annotations > 0
          ? Math.round((a.completed_annotations / a.total_annotations) * 100) : 0;
        const lastActive = a.last_active ? new Date(a.last_active).toLocaleString() : 'unknown';
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
          '</div>' +
          '</div>' +
          '<a href="/api/export/csv/' + encodeURIComponent(a.annotator_id) + '"' +
             ' class="flex-shrink-0 text-xs text-indigo-600 hover:underline font-medium">Download CSV</a>' +
          '</div>';
      });
      html += '</div>';
      document.getElementById('annotators-card').innerHTML = html;
    }).catch(() => {
      document.getElementById('annotators-card').innerHTML =
        '<p class="text-red-500 text-sm">Server error loading annotators.</p>';
    });

    function stat(val, label, color) {
      const colors = {
        indigo: 'bg-indigo-50 text-indigo-700 text-indigo-500',
        emerald: 'bg-emerald-50 text-emerald-700 text-emerald-500',
        slate: 'bg-slate-50 text-slate-700 text-slate-500',
      };
      const [bg, text, sub] = colors[color].split(' ');
      return '<div class="' + bg + ' rounded-xl p-4 text-center">' +
             '<p class="text-2xl font-bold ' + text + '">' + val + '</p>' +
             '<p class="text-xs ' + sub + ' mt-1">' + label + '</p></div>';
    }
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
