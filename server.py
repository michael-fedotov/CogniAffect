"""
BWS Empathy Annotation - Flask Backend

Serves the annotation app and stores annotations in PostgreSQL (e.g. Supabase).

Set DATABASE_URL to your connection string (append ?sslmode=require if needed).

Usage:
    python server.py

Then open http://localhost:5000 in a browser.
Admin dashboard: http://localhost:5000/admin
"""

import json
import csv
import io
import os
import argparse
import hashlib
from collections import defaultdict
from datetime import datetime, timezone

import psycopg2
from dotenv import load_dotenv
from psycopg2.extras import RealDictCursor, Json
from flask import Flask, request, jsonify, send_from_directory, Response
from flask_cors import CORS

load_dotenv()

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "https://michael-fedotov.github.io/CogniAffect/"}})

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

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


def _database_url():
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "DATABASE_URL is not set. Set it to your Supabase PostgreSQL connection string "
            "(append ?sslmode=require if not already present)."
        )
    return url


class _PgConn:
    """Thin wrapper so routes can keep using conn.execute(...).fetchall() / fetchone()."""

    def __init__(self, raw):
        self._raw = raw

    def execute(self, sql, params=None):
        cur = self._raw.cursor(cursor_factory=RealDictCursor)
        cur.execute(sql, params or ())
        return cur

    def commit(self):
        self._raw.commit()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            if exc_type is not None:
                self._raw.rollback()
            else:
                self._raw.commit()
        finally:
            self._raw.close()


def get_db():
    return _PgConn(psycopg2.connect(_database_url()))


def init_db():
    ddl = [
        """
            CREATE TABLE IF NOT EXISTS annotations (
                id                      SERIAL PRIMARY KEY,
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
                created_at              TEXT    DEFAULT (CURRENT_TIMESTAMP::text),
                updated_at              TEXT    DEFAULT (CURRENT_TIMESTAMP::text)
            )
        """,
        """
            CREATE TABLE IF NOT EXISTS sessions (
                annotator_id TEXT    PRIMARY KEY,
                session_data TEXT    NOT NULL,
                updated_at   TEXT    DEFAULT (CURRENT_TIMESTAMP::text)
            )
        """,
        """
            CREATE TABLE IF NOT EXISTS llm_annotations (
                id                       SERIAL PRIMARY KEY,
                annotation_id            TEXT    DEFAULT '',
                judge_model              TEXT    NOT NULL,
                scenario_id              TEXT    NOT NULL,
                context_snippet          TEXT    DEFAULT '',
                response_a_label         TEXT    DEFAULT '',
                response_b_label         TEXT    DEFAULT '',
                response_c_label         TEXT    DEFAULT '',
                cognitive_most           TEXT    DEFAULT '',
                cognitive_least          TEXT    DEFAULT '',
                cognitive_reasoning      TEXT    DEFAULT '',
                affective_most           TEXT    DEFAULT '',
                affective_least          TEXT    DEFAULT '',
                affective_reasoning      TEXT    DEFAULT '',
                timestamp                TEXT    DEFAULT '',
                session_duration_seconds TEXT    DEFAULT '',
                is_complete              INTEGER DEFAULT 0,
                created_at               TEXT    DEFAULT (CURRENT_TIMESTAMP::text),
                UNIQUE(judge_model, scenario_id)
            )
        """,
        """
            CREATE TABLE IF NOT EXISTS active_scenario_config (
                id INTEGER PRIMARY KEY DEFAULT 1,
                CONSTRAINT active_scenario_config_singleton CHECK (id = 1),
                payload JSONB,
                content_hash TEXT,
                label TEXT DEFAULT '',
                updated_at TEXT DEFAULT (CURRENT_TIMESTAMP::text)
            )
        """,
    ]
    with get_db() as conn:
        for stmt in ddl:
            conn.execute(stmt)
        conn.execute(
            """
            INSERT INTO active_scenario_config (id) VALUES (1)
            ON CONFLICT (id) DO NOTHING
            """
        )
        conn.commit()


init_db()


# ── Canonical scenarios (DB + optional repo file seed) ──────────────────────


def _load_repo_scenarios_file():
    path = os.path.join(BASE_DIR, "scenarios.json")
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def validate_scenarios_document(data):
    """Return a list of error strings; empty if valid."""
    errors = []
    if not isinstance(data, dict):
        return ["Root value must be a JSON object"]
    scenarios = data.get("scenarios")
    if not isinstance(scenarios, list) or len(scenarios) < 1:
        errors.append('Missing or empty "scenarios" array')
        return errors
    seen_ids = set()
    for i, s in enumerate(scenarios):
        pref = f"scenarios[{i}]"
        if not isinstance(s, dict):
            errors.append(f"{pref} must be an object")
            continue
        sid = s.get("scenario_id")
        if not sid or not isinstance(sid, str) or not sid.strip():
            errors.append(f"{pref}: scenario_id must be a non-empty string")
        else:
            sid = sid.strip()
            if sid in seen_ids:
                errors.append(f"Duplicate scenario_id: {sid!r}")
            else:
                seen_ids.add(sid)
        ctx = s.get("context")
        if not isinstance(ctx, str):
            errors.append(f"{pref}: context must be a string")
        responses = s.get("responses")
        if not isinstance(responses, list) or len(responses) != 3:
            errors.append(f"{pref}: responses must be an array of length 3")
        else:
            letters = []
            for j, r in enumerate(responses):
                if not isinstance(r, dict):
                    errors.append(f"{pref}.responses[{j}] must be an object")
                    continue
                rid = r.get("response_id")
                if rid not in ("A", "B", "C"):
                    errors.append(
                        f"{pref}.responses[{j}]: response_id must be A, B, or C"
                    )
                else:
                    letters.append(rid)
                if "text" not in r or not isinstance(r.get("text"), str):
                    errors.append(f"{pref}.responses[{j}]: text must be a string")
            if sorted(letters) != ["A", "B", "C"]:
                errors.append(f"{pref}: responses must include A, B, and C exactly once")
        gt = s.get("ground_truth_labels")
        if not isinstance(gt, dict):
            errors.append(f"{pref}: ground_truth_labels must be an object")
        else:
            for L in ("A", "B", "C"):
                if L not in gt:
                    errors.append(f"{pref}: ground_truth_labels missing key {L!r}")
                elif not isinstance(gt[L], str) or not str(gt[L]).strip():
                    errors.append(
                        f"{pref}: ground_truth_labels[{L!r}] must be a non-empty string"
                    )
    return errors


def _hash_scenarios_payload(data):
    """Stable hash for the scenarios array only."""
    blob = json.dumps(data["scenarios"], sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def _seed_scenarios_from_repo_file_if_empty():
    with get_db() as conn:
        row = conn.execute(
            "SELECT payload FROM active_scenario_config WHERE id = 1"
        ).fetchone()
        if row and row["payload"] is not None:
            return
        disk = _load_repo_scenarios_file()
        if not disk:
            return
        errs = validate_scenarios_document(disk)
        if errs:
            return
        h = _hash_scenarios_payload(disk)
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            """
            UPDATE active_scenario_config SET
                payload = %s,
                content_hash = %s,
                label = %s,
                updated_at = %s
            WHERE id = 1
            """,
            (Json(disk), h, "seeded from repo scenarios.json", now),
        )
        conn.commit()


_seed_scenarios_from_repo_file_if_empty()


def get_active_scenario_document():
    """Return the full scenario document dict, or None if unset."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT payload FROM active_scenario_config WHERE id = 1"
        ).fetchone()
    if not row or row["payload"] is None:
        return None
    p = row["payload"]
    return p if isinstance(p, dict) else json.loads(p)


def get_canonical_scenarios_list():
    """Ordered list of scenario dicts for sync and labeling; None if not configured."""
    doc = get_active_scenario_document()
    if not doc:
        return None
    scenarios = doc.get("scenarios")
    if not isinstance(scenarios, list):
        return None
    return scenarios


def _admin_auth_error():
    secret = (os.environ.get("ADMIN_SECRET") or "").strip()
    if not secret:
        return "ADMIN_SECRET is not set on the server", 503
    auth = request.headers.get("Authorization") or ""
    token = ""
    if auth.lower().startswith("bearer "):
        token = auth[7:].strip()
    if not token:
        token = (request.headers.get("X-Admin-Key") or "").strip()
    if token != secret:
        return "Unauthorized", 401
    return None

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
    doc = get_active_scenario_document()
    if doc is not None:
        return jsonify(doc)
    disk = _load_repo_scenarios_file()
    if disk is not None:
        return jsonify(disk)
    return jsonify({"error": "No scenario set configured"}), 404


@app.route("/api/scenarios", methods=["GET"])
def api_scenarios():
    doc = get_active_scenario_document()
    if doc is not None:
        return jsonify(doc)
    disk = _load_repo_scenarios_file()
    if disk is not None:
        return jsonify(disk)
    return jsonify({"error": "No scenario set configured"}), 404


@app.route("/api/admin/scenarios", methods=["GET"])
def admin_get_scenarios():
    err = _admin_auth_error()
    if err:
        msg, code = err
        return jsonify({"error": msg}), code
    full = (request.args.get("full") or "").strip() in ("1", "true", "yes")
    with get_db() as conn:
        row = conn.execute(
            """
            SELECT payload, content_hash, label, updated_at
            FROM active_scenario_config WHERE id = 1
            """
        ).fetchone()
    if not row:
        return jsonify({"error": "Config row missing"}), 500
    payload = row["payload"]
    if payload is None:
        out = {
            "has_payload": False,
            "scenario_count": 0,
            "scenario_ids": [],
            "content_hash": row["content_hash"],
            "label": row["label"],
            "updated_at": row["updated_at"],
        }
        return jsonify(out)
    doc = payload if isinstance(payload, dict) else json.loads(payload)
    scenarios = doc.get("scenarios") or []
    ids = [s.get("scenario_id") for s in scenarios if isinstance(s, dict)]
    out = {
        "has_payload": True,
        "scenario_count": len(scenarios),
        "scenario_ids": ids,
        "content_hash": row["content_hash"],
        "label": row["label"],
        "updated_at": row["updated_at"],
    }
    if full:
        out["payload"] = doc
    return jsonify(out)


@app.route("/api/admin/scenarios", methods=["POST"])
def admin_post_scenarios():
    err = _admin_auth_error()
    if err:
        msg, code = err
        return jsonify({"error": msg}), code
    data = request.get_json(force=True)
    if not data or not isinstance(data, dict):
        return jsonify({"error": "JSON body required"}), 400
    if not data.get("confirm"):
        return jsonify(
            {
                "error": "Missing confirm: true — replacing the scenario set is destructive for analysis. "
                "Read the warnings and submit again with confirm: true."
            }
        ), 400
    label = (data.get("label") or "").strip() or None
    # Allow { "confirm", "label", "scenarios": [...], ... } or nested only
    payload = {k: v for k, v in data.items() if k not in ("confirm", "label")}
    if "scenarios" not in payload:
        return jsonify({"error": 'Body must include a "scenarios" array (and confirm: true)'}), 400
    errs = validate_scenarios_document(payload)
    if errs:
        return jsonify({"error": "Validation failed", "details": errs[:30]}), 400
    h = _hash_scenarios_payload(payload)
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        conn.execute(
            """
            UPDATE active_scenario_config SET
                payload = %s,
                content_hash = %s,
                label = COALESCE(%s, label),
                updated_at = %s
            WHERE id = 1
            """,
            (Json(payload), h, label, now),
        )
        conn.commit()
    n = len(payload["scenarios"])
    ids = [s["scenario_id"] for s in payload["scenarios"]]
    return jsonify(
        {
            "status": "ok",
            "scenario_count": n,
            "scenario_ids": ids,
            "content_hash": h,
            "updated_at": now,
        }
    )


# ── Session API ───────────────────────────────────────────────────────────────

@app.route("/api/session/<annotator_id>", methods=["GET"])
def get_session(annotator_id):
    with get_db() as conn:
        row = conn.execute(
            "SELECT session_data FROM sessions WHERE annotator_id = %s",
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
    scenarios_list = get_canonical_scenarios_list()
    if scenarios_list is None:
        return jsonify(
            {"error": "No scenario set is configured on the server. Contact an administrator."}
        ), 503

    scenarios_map = {s["scenario_id"]: s for s in scenarios_list}
    now = datetime.now(timezone.utc).isoformat()

    with get_db() as conn:
        # Upsert full session blob (used for resume)
        conn.execute(
            """
            INSERT INTO sessions (annotator_id, session_data, updated_at) VALUES (%s, %s, %s)
            ON CONFLICT (annotator_id) DO UPDATE SET
                session_data = EXCLUDED.session_data,
                updated_at = EXCLUDED.updated_at
            """,
            (annotator_id, json.dumps(session_data), now),
        )

        annotations = session_data.get("annotations", {})
        shuffle_maps = session_data.get("shuffle_maps", {})
        original_ids = ["A", "B", "C"]

        for scenario_id, ann in annotations.items():
            if scenario_id not in scenarios_map:
                return jsonify(
                    {
                        "error": "scenario_id is not in the active scenario set",
                        "scenario_id": scenario_id,
                    }
                ), 400
            scenario = scenarios_map[scenario_id]

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
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (annotation_id) DO UPDATE SET
                    context_snippet          = EXCLUDED.context_snippet,
                    response_a_label         = EXCLUDED.response_a_label,
                    response_b_label         = EXCLUDED.response_b_label,
                    response_c_label         = EXCLUDED.response_c_label,
                    cognitive_most           = EXCLUDED.cognitive_most,
                    cognitive_least          = EXCLUDED.cognitive_least,
                    cognitive_reasoning      = EXCLUDED.cognitive_reasoning,
                    affective_most           = EXCLUDED.affective_most,
                    affective_least          = EXCLUDED.affective_least,
                    affective_reasoning      = EXCLUDED.affective_reasoning,
                    timestamp                = EXCLUDED.timestamp,
                    session_duration_seconds = EXCLUDED.session_duration_seconds,
                    is_complete              = EXCLUDED.is_complete,
                    updated_at               = EXCLUDED.updated_at
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
            f"SELECT {', '.join(CSV_COLUMNS)} FROM annotations WHERE annotator_id = %s ORDER BY scenario_id",
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
    # RealDictCursor returns dict rows — use aliases, not fetchone()[0]
    with get_db() as conn:
        total = conn.execute("SELECT COUNT(*) AS n FROM annotations").fetchone()
        complete = conn.execute(
            "SELECT COUNT(*) AS n FROM annotations WHERE is_complete = 1"
        ).fetchone()
        annotators = conn.execute(
            "SELECT COUNT(DISTINCT annotator_id) AS n FROM annotations"
        ).fetchone()
    total = total["n"] if total else 0
    complete = complete["n"] if complete else 0
    annotators = annotators["n"] if annotators else 0
    return jsonify(
        {
            "total_annotations": total,
            "complete_annotations": complete,
            "annotator_count": annotators,
            "database": "postgresql",
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


def _row_is_complete_bws(row):
    """Same completion rules as /api/sync for human annotations."""
    cog_most = (row.get("cognitive_most") or "").strip()
    cog_least = (row.get("cognitive_least") or "").strip()
    aff_most = (row.get("affective_most") or "").strip()
    aff_least = (row.get("affective_least") or "").strip()
    return bool(
        cog_most and cog_least and aff_most and aff_least
        and cog_most != cog_least
        and aff_most != aff_least
    )


def build_scores_payload(rows, count_key="annotator_id"):
    """Build /api/scores-shaped JSON from a list of annotation row dicts."""
    if not rows:
        return {
            "cognitive": {},
            "affective": {},
            "per_scenario": {},
            "meta": {"total_annotations": 0, "annotator_count": 0, "scenario_count": 0},
        }

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

    annotator_count = 0
    if rows and count_key in rows[0]:
        annotator_count = len(set(r[count_key] for r in rows if r.get(count_key)))

    return {
        "cognitive": cognitive_overall,
        "affective": affective_overall,
        "per_scenario": per_scenario,
        "meta": {
            "total_annotations": len(rows),
            "annotator_count": annotator_count,
            "scenario_count": len(scenario_ids),
        },
    }


def _diff_score_dict(human_d, llm_d):
    """Per-item differences human - LLM for keys present in both."""
    keys = set(human_d.keys()) & set(llm_d.keys())
    out = {}
    for k in sorted(keys):
        out[k] = round(human_d[k] - llm_d[k], 4)
    return out


def _mean_abs(d):
    if not d:
        return None
    vals = [abs(v) for v in d.values()]
    return round(sum(vals) / len(vals), 4)


@app.route("/api/scores")
def scores():
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM annotations WHERE is_complete = 1"
        ).fetchall()
    rows = [dict(r) for r in rows]
    payload = build_scores_payload(rows, count_key="annotator_id")
    return jsonify(payload)


# ── LLM-as-a-Judge API ────────────────────────────────────────────────────────


@app.route("/api/llm-judge/models", methods=["GET"])
def llm_judge_models():
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT judge_model,
                   COUNT(*) AS total_rows,
                   SUM(is_complete) AS completed_rows,
                   MAX(created_at) AS last_upload
            FROM llm_annotations
            GROUP BY judge_model
            ORDER BY judge_model
            """
        ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/llm-judge/upload", methods=["POST"])
def llm_judge_upload():
    """Accept CSV in the same format as /api/export/csv. annotator_id → judge_model."""
    if "file" not in request.files:
        return jsonify({"error": "Missing file field (use name 'file')"}), 400
    f = request.files["file"]
    if not f.filename:
        return jsonify({"error": "Empty filename"}), 400

    try:
        raw = f.read()
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return jsonify({"error": "File must be UTF-8 text CSV"}), 400

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        return jsonify({"error": "CSV has no header row"}), 400

    missing = [c for c in CSV_COLUMNS if c not in reader.fieldnames]
    if missing:
        return jsonify(
            {"error": "CSV missing columns: " + ", ".join(missing), "expected": CSV_COLUMNS}
        ), 400

    now = datetime.now(timezone.utc).isoformat()
    inserted = 0
    skipped = 0
    errors = []

    with get_db() as conn:
        for i, row in enumerate(reader, start=2):
            line_num = i
            judge_model = (row.get("annotator_id") or "").strip()
            scenario_id = (row.get("scenario_id") or "").strip()
            if not judge_model or not scenario_id:
                skipped += 1
                errors.append(f"Line {line_num}: missing annotator_id or scenario_id")
                continue

            is_complete = int(_row_is_complete_bws(row))

            conn.execute(
                """
                INSERT INTO llm_annotations (
                    annotation_id, judge_model, scenario_id, context_snippet,
                    response_a_label, response_b_label, response_c_label,
                    cognitive_most, cognitive_least, cognitive_reasoning,
                    affective_most, affective_least, affective_reasoning,
                    timestamp, session_duration_seconds, is_complete, created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (judge_model, scenario_id) DO UPDATE SET
                    annotation_id            = EXCLUDED.annotation_id,
                    context_snippet          = EXCLUDED.context_snippet,
                    response_a_label         = EXCLUDED.response_a_label,
                    response_b_label         = EXCLUDED.response_b_label,
                    response_c_label         = EXCLUDED.response_c_label,
                    cognitive_most           = EXCLUDED.cognitive_most,
                    cognitive_least          = EXCLUDED.cognitive_least,
                    cognitive_reasoning      = EXCLUDED.cognitive_reasoning,
                    affective_most           = EXCLUDED.affective_most,
                    affective_least          = EXCLUDED.affective_least,
                    affective_reasoning      = EXCLUDED.affective_reasoning,
                    timestamp                = EXCLUDED.timestamp,
                    session_duration_seconds = EXCLUDED.session_duration_seconds,
                    is_complete              = EXCLUDED.is_complete,
                    created_at               = EXCLUDED.created_at
                """,
                (
                    (row.get("annotation_id") or "").strip(),
                    judge_model,
                    scenario_id,
                    (row.get("context_snippet") or "").strip(),
                    (row.get("response_a_label") or "").strip(),
                    (row.get("response_b_label") or "").strip(),
                    (row.get("response_c_label") or "").strip(),
                    (row.get("cognitive_most") or "").strip(),
                    (row.get("cognitive_least") or "").strip(),
                    (row.get("cognitive_reasoning") or "").strip(),
                    (row.get("affective_most") or "").strip(),
                    (row.get("affective_least") or "").strip(),
                    (row.get("affective_reasoning") or "").strip(),
                    (row.get("timestamp") or "").strip(),
                    (row.get("session_duration_seconds") or "").strip(),
                    is_complete,
                    now,
                ),
            )
            inserted += 1

        conn.commit()

    return jsonify(
        {
            "status": "ok",
            "rows_processed": inserted,
            "rows_skipped": skipped,
            "errors": errors[:50],
            "error_count": len(errors),
            "uploaded_at": now,
        }
    )


@app.route("/api/llm-judge/scores", methods=["GET"])
def llm_judge_scores():
    model = (request.args.get("model") or "").strip()
    if not model:
        return jsonify({"error": "Query parameter 'model' is required"}), 400

    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM llm_annotations WHERE judge_model = %s AND is_complete = 1",
            (model,),
        ).fetchall()
    rows = [dict(r) for r in rows]
    payload = build_scores_payload(rows, count_key="judge_model")
    payload["meta"]["judge_model"] = model
    return jsonify(payload)


@app.route("/api/llm-judge/<path:model>", methods=["DELETE"])
def llm_judge_delete(model):
    """Remove all rows for one judge model."""
    if not model.strip():
        return jsonify({"error": "Invalid model"}), 400
    with get_db() as conn:
        cur = conn.execute("DELETE FROM llm_annotations WHERE judge_model = %s", (model,))
        conn.commit()
        deleted = cur.rowcount
    return jsonify({"status": "ok", "deleted_rows": deleted, "judge_model": model})


@app.route("/api/comparison", methods=["GET"])
def comparison():
    model = (request.args.get("model") or "").strip()
    if not model:
        return jsonify({"error": "Query parameter 'model' is required"}), 400

    with get_db() as conn:
        human_rows = conn.execute(
            "SELECT * FROM annotations WHERE is_complete = 1"
        ).fetchall()
        llm_rows = conn.execute(
            "SELECT * FROM llm_annotations WHERE judge_model = %s AND is_complete = 1",
            (model,),
        ).fetchall()

    human_rows = [dict(r) for r in human_rows]
    llm_rows = [dict(r) for r in llm_rows]

    human_payload = build_scores_payload(human_rows, count_key="annotator_id")
    llm_payload = build_scores_payload(llm_rows, count_key="judge_model")

    h_cog = human_payload["cognitive"]
    h_aff = human_payload["affective"]
    l_cog = llm_payload["cognitive"]
    l_aff = llm_payload["affective"]

    diff_cog = _diff_score_dict(h_cog, l_cog)
    diff_aff = _diff_score_dict(h_aff, l_aff)

    h_ps = human_payload["per_scenario"]
    l_ps = llm_payload["per_scenario"]
    all_sids = sorted(set(h_ps.keys()) | set(l_ps.keys()))

    per_scenario_diff = {}
    scenario_mae = []

    for sid in all_sids:
        hc = h_ps.get(sid, {}).get("cognitive", {})
        ha = h_ps.get(sid, {}).get("affective", {})
        lc = l_ps.get(sid, {}).get("cognitive", {})
        la = l_ps.get(sid, {}).get("affective", {})
        dc = _diff_score_dict(hc, lc)
        da = _diff_score_dict(ha, la)
        abs_vals = [abs(v) for v in dc.values()] + [abs(v) for v in da.values()]
        mae = sum(abs_vals) / len(abs_vals) if abs_vals else None
        if mae is not None:
            scenario_mae.append((sid, mae))
        per_scenario_diff[sid] = {
            "cognitive": dc,
            "affective": da,
            "human_n": h_ps.get(sid, {}).get("n"),
            "llm_n": l_ps.get(sid, {}).get("n"),
            "mean_abs_diff": round(mae, 4) if mae is not None else None,
        }

    worst_sid = None
    worst_mae = None
    if scenario_mae:
        worst_sid, worst_mae = max(scenario_mae, key=lambda x: x[1])

    # Simple correlation: Pearson r between paired per-scenario mean scores (human vs LLM)
    # across scenarios that exist in both, averaged over items present in both dims.
    def _pearson(xs, ys):
        n = len(xs)
        if n < 2:
            return None
        mx = sum(xs) / n
        my = sum(ys) / n
        num = sum((xs[i] - mx) * (ys[i] - my) for i in range(n))
        denx = sum((xs[i] - mx) ** 2 for i in range(n)) ** 0.5
        deny = sum((ys[i] - my) ** 2 for i in range(n)) ** 0.5
        if denx == 0 or deny == 0:
            return None
        return round(num / (denx * deny), 4)

    corr_cog = None
    corr_aff = None
    shared = [s for s in all_sids if s in h_ps and s in l_ps]
    if len(shared) >= 2:
        items_cog = sorted(set(h_cog.keys()) & set(l_cog.keys()))
        hx_c = []
        lx_c = []
        for sid in shared:
            hc = h_ps[sid]["cognitive"]
            lc = l_ps[sid]["cognitive"]
            pairs = [(hc[k], lc[k]) for k in items_cog if k in hc and k in lc]
            if len(pairs) == len(items_cog) and items_cog:
                hx_c.append(sum(p[0] for p in pairs) / len(pairs))
                lx_c.append(sum(p[1] for p in pairs) / len(pairs))
        if len(hx_c) >= 2:
            corr_cog = _pearson(hx_c, lx_c)

        items_aff = sorted(set(h_aff.keys()) & set(l_aff.keys()))
        hx_a = []
        lx_a = []
        for sid in shared:
            ha = h_ps[sid]["affective"]
            la = l_ps[sid]["affective"]
            pairs = [(ha[k], la[k]) for k in items_aff if k in ha and k in la]
            if len(pairs) == len(items_aff) and items_aff:
                hx_a.append(sum(p[0] for p in pairs) / len(pairs))
                lx_a.append(sum(p[1] for p in pairs) / len(pairs))
        if len(hx_a) >= 2:
            corr_aff = _pearson(hx_a, lx_a)

    return jsonify(
        {
            "human_scores": human_payload,
            "llm_scores": llm_payload,
            "differences": {
                "cognitive": diff_cog,
                "affective": diff_aff,
            },
            "per_scenario": per_scenario_diff,
            "summary": {
                "judge_model": model,
                "mean_abs_diff": {
                    "cognitive": _mean_abs(diff_cog),
                    "affective": _mean_abs(diff_aff),
                },
                "worst_scenario": worst_sid,
                "worst_scenario_mae": round(worst_mae, 4) if worst_mae is not None else None,
                "pearson_r": {
                    "cognitive_per_scenario_mean": corr_cog,
                    "affective_per_scenario_mean": corr_aff,
                },
            },
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
  <div class="max-w-6xl mx-auto px-6 py-10">

    <!-- Header -->
    <div class="flex items-center justify-between mb-6">
      <div>
        <h1 class="text-2xl font-bold text-slate-800">BWS Annotation Admin</h1>
        <p class="text-slate-500 text-sm mt-1">Collected annotation data across all annotators</p>
      </div>
      <a href="/" class="text-sm text-indigo-600 hover:underline">Back to app</a>
    </div>

    <!-- Tabs -->
    <div class="flex flex-wrap gap-2 mb-6 border-b border-slate-200 pb-3">
      <button type="button" onclick="switchTab('human')" id="tab-btn-human"
        class="tab-btn px-4 py-2 rounded-t-lg text-sm font-semibold bg-indigo-600 text-white shadow-sm">Human annotations</button>
      <button type="button" onclick="switchTab('llm')" id="tab-btn-llm"
        class="tab-btn px-4 py-2 rounded-t-lg text-sm font-semibold bg-slate-100 text-slate-600 hover:bg-slate-200">LLM-as-a-Judge</button>
      <button type="button" onclick="switchTab('compare')" id="tab-btn-compare"
        class="tab-btn px-4 py-2 rounded-t-lg text-sm font-semibold bg-slate-100 text-slate-600 hover:bg-slate-200">Comparison</button>
    </div>

    <div id="panel-human" class="tab-panel">

    <!-- Scenario set (admin upload) -->
    <div class="bg-white rounded-2xl border border-slate-200 shadow-sm p-6 mb-6">
      <h2 class="text-xs font-bold uppercase tracking-widest text-slate-500 mb-4">Active scenario set</h2>
      <p class="text-sm text-slate-600 mb-3">This JSON is served to annotators at <code class="bg-slate-100 px-1 rounded text-xs">/api/scenarios</code>. Set <code class="bg-slate-100 px-1 rounded text-xs">ADMIN_SECRET</code> in the server environment; paste it here to manage uploads.</p>
      <div class="flex flex-wrap items-end gap-3 mb-4">
        <div class="flex-1 min-w-[200px]">
          <label class="text-xs font-semibold text-slate-600 block mb-1">Admin secret</label>
          <input type="password" id="admin-secret-input" class="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm font-mono" placeholder="Same as ADMIN_SECRET" autocomplete="off" />
        </div>
        <button type="button" onclick="loadScenarioSummary()"
          class="inline-flex items-center gap-2 bg-slate-700 text-white px-4 py-2 rounded-xl font-semibold text-sm hover:bg-slate-800">Load current</button>
      </div>
      <div id="scenario-admin-summary" class="text-sm text-slate-600 mb-4 min-h-[3rem]"></div>
      <div class="flex flex-wrap items-end gap-3">
        <input type="file" id="scenario-json-file" accept=".json,application/json" class="text-sm block" />
        <button type="button" onclick="openScenarioUploadModal()"
          class="inline-flex items-center gap-2 bg-indigo-600 text-white px-4 py-2 rounded-xl font-semibold text-sm hover:bg-indigo-700">Review &amp; upload…</button>
      </div>
      <p id="scenario-upload-msg" class="text-sm mt-3 min-h-[1.25rem]"></p>
    </div>

    <div id="scenario-modal" class="hidden fixed inset-0 z-[100] flex items-center justify-center p-4 bg-black/40">
      <div class="bg-white rounded-2xl shadow-xl max-w-lg w-full p-6 border border-slate-200 max-h-[90vh] overflow-y-auto">
        <h3 class="text-lg font-bold text-slate-800 mb-2">Replace scenario set?</h3>
        <ul class="text-sm text-slate-600 list-disc pl-5 space-y-2 mb-4">
          <li>Existing annotation rows are <strong>not</strong> deleted, but mixed scenario sets can make aggregate scores misleading.</li>
          <li>Annotators with in-progress sessions may see sync errors until they start fresh if scenario IDs no longer match.</li>
        </ul>
        <div id="scenario-modal-preview" class="bg-slate-50 rounded-xl p-3 text-xs font-mono text-slate-700 mb-4 max-h-32 overflow-y-auto whitespace-pre-wrap"></div>
        <label class="flex items-start gap-2 text-sm text-slate-700 mb-4">
          <input type="checkbox" id="scenario-modal-confirm" class="mt-1" />
          <span>I understand that replacing the scenario set can affect ongoing annotation work.</span>
        </label>
        <div class="flex gap-2 justify-end">
          <button type="button" onclick="closeScenarioModal()" class="px-4 py-2 rounded-xl border border-slate-200 text-slate-700 text-sm font-semibold hover:bg-slate-50">Cancel</button>
          <button type="button" onclick="confirmScenarioUpload()" class="px-4 py-2 rounded-xl bg-amber-600 text-white text-sm font-semibold hover:bg-amber-700">Upload</button>
        </div>
      </div>
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

    </div><!-- /panel-human -->

    <div id="panel-llm" class="tab-panel hidden">
      <div class="bg-white rounded-2xl border border-slate-200 shadow-sm p-6 mb-6">
        <h2 class="text-xs font-bold uppercase tracking-widest text-slate-500 mb-4">Upload LLM-as-a-Judge CSV</h2>
        <p class="text-sm text-slate-600 mb-3">Use the same columns as <code class="bg-slate-100 px-1 rounded text-xs">/api/export/csv</code>.
          The <code class="bg-slate-100 px-1 rounded text-xs">annotator_id</code> column is stored as the judge model name.</p>
        <form id="llm-upload-form" class="flex flex-wrap items-end gap-3" onsubmit="return uploadLlmCsv(event)">
          <input type="file" name="file" id="llm-csv-file" accept=".csv,text/csv" required class="text-sm block" />
          <button type="submit" class="inline-flex items-center gap-2 bg-violet-600 text-white px-4 py-2.5 rounded-xl font-semibold text-sm hover:bg-violet-700">Upload CSV</button>
        </form>
        <p id="llm-upload-msg" class="text-sm mt-3 min-h-[1.25rem]"></p>
      </div>
      <div id="llm-models-card" class="bg-white rounded-2xl border border-slate-200 shadow-sm p-6 mb-6">
        <div class="animate-pulse h-16 bg-slate-100 rounded-xl"></div>
      </div>
      <div class="flex flex-wrap items-center gap-3 mb-4">
        <label class="text-sm font-semibold text-slate-700">Judge model</label>
        <select id="llm-model-select" class="border border-slate-200 rounded-lg px-3 py-2 text-sm font-mono min-w-[12rem]"></select>
        <button type="button" onclick="loadLlmScores()"
          class="inline-flex items-center gap-2 border-2 border-emerald-300 text-emerald-700 px-4 py-2 rounded-xl font-semibold text-sm hover:bg-emerald-50">Load LLM scores</button>
      </div>
      <div id="llm-scores-card" class="bg-white rounded-2xl border border-slate-200 shadow-sm p-6 mb-6">
        <p class="text-slate-400 text-sm">Select a judge model and click &ldquo;Load LLM scores&rdquo;.</p>
      </div>
      <div id="llm-scenario-card" class="bg-white rounded-2xl border border-slate-200 shadow-sm p-6 mb-6"></div>
    </div>

    <div id="panel-compare" class="tab-panel hidden">
      <div class="flex flex-wrap items-center gap-3 mb-4">
        <label class="text-sm font-semibold text-slate-700">LLM judge model</label>
        <select id="compare-model-select" class="border border-slate-200 rounded-lg px-3 py-2 text-sm font-mono min-w-[12rem]"></select>
        <button type="button" onclick="loadComparison()"
          class="inline-flex items-center gap-2 bg-amber-500 text-white px-4 py-2 rounded-xl font-semibold text-sm hover:bg-amber-600">Load comparison</button>
      </div>
      <div id="compare-summary-card" class="bg-white rounded-2xl border border-slate-200 shadow-sm p-6 mb-6"></div>
      <div id="compare-side-card" class="bg-white rounded-2xl border border-slate-200 shadow-sm p-6 mb-6"></div>
      <div id="compare-diff-overall-card" class="bg-white rounded-2xl border border-slate-200 shadow-sm p-6 mb-6"></div>
      <div id="compare-per-scenario-card" class="bg-white rounded-2xl border border-slate-200 shadow-sm p-6 mb-6"></div>
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

    function diffHeatColor(d) {
      var a = Math.abs(d);
      if (a <= 0.15) return 'background:#ECFDF5;color:#047857;';
      if (a <= 0.35) return 'background:#FEF9C3;color:#854D0E;';
      return 'background:#FEE2E2;color:#991B1B;';
    }

    function friendlyName(key) { return LABELS[key] || key; }

    function switchTab(name) {
      document.getElementById('panel-human').classList.toggle('hidden', name !== 'human');
      document.getElementById('panel-llm').classList.toggle('hidden', name !== 'llm');
      document.getElementById('panel-compare').classList.toggle('hidden', name !== 'compare');
      var active = 'bg-indigo-600 text-white shadow-sm';
      var idle = 'bg-slate-100 text-slate-600 hover:bg-slate-200';
      ['human','llm','compare'].forEach(function(t) {
        var el = document.getElementById('tab-btn-' + t);
        el.className = 'tab-btn px-4 py-2 rounded-t-lg text-sm font-semibold ' + (t === name ? active : idle);
      });
    }

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
        renderScores(d, 'scores-card', 'scenario-card', 'Human &mdash; BWS Scores');
        renderPerScenario(d, 'scenario-card');
      }).catch(function() {
        document.getElementById('scores-card').innerHTML = '<p class="text-red-500 text-sm">Error loading scores.</p>';
        document.getElementById('scenario-card').innerHTML = '';
      });
    }

    function renderScores(d, scoresCardId, scenarioCardId, titleHtml) {
      var meta = d.meta || {};
      if ((meta.total_annotations || 0) < 1) {
        document.getElementById(scoresCardId).innerHTML =
          '<h2 class="text-xs font-bold uppercase tracking-widest text-slate-500 mb-4">BWS Scores</h2>' +
          '<p class="text-slate-400 text-sm">Not enough completed annotations to compute scores. Need at least 1.</p>';
        if (scenarioCardId) document.getElementById(scenarioCardId).innerHTML = '';
        return;
      }

      var cog = d.cognitive;
      var aff = d.affective;
      var cogKeys = Object.keys(cog).sort(function(a, b) { return cog[b] - cog[a]; });
      var affKeys = Object.keys(aff).sort(function(a, b) { return aff[b] - aff[a]; });

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

      document.getElementById(scoresCardId).innerHTML =
        '<h2 class="text-xs font-bold uppercase tracking-widest text-slate-500 mb-4">' + titleHtml + '</h2>' +
        insight +
        '<div class="flex flex-wrap gap-8">' +
        scoreTable('Cognitive Empathy', 'indigo', cog) +
        scoreTable('Affective Empathy', 'violet', aff) +
        '</div>';
    }

    function renderPerScenario(d, scenarioCardId) {
      var ps = d.per_scenario;
      var sids = Object.keys(ps);
      if (sids.length < 1) {
        document.getElementById(scenarioCardId).innerHTML = '';
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

      document.getElementById(scenarioCardId).innerHTML =
        '<h2 class="text-xs font-bold uppercase tracking-widest text-slate-500 mb-4">Per-Scenario Breakdown</h2>' +
        '<div class="space-y-6">' +
        heatTable('Cognitive Empathy by Scenario', 'cognitive') +
        heatTable('Affective Empathy by Scenario', 'affective') +
        '</div>';
    }

    function loadLlmModels() {
      fetch('/api/llm-judge/models').then(r => r.json()).then(function(models) {
        var sel = document.getElementById('llm-model-select');
        var csel = document.getElementById('compare-model-select');
        sel.innerHTML = '';
        csel.innerHTML = '';
        models.forEach(function(m) {
          var label = m.judge_model + ' (' + (m.completed_rows || 0) + ' complete / ' + m.total_rows + ')';
          var opt1 = document.createElement('option');
          opt1.value = m.judge_model;
          opt1.textContent = label;
          sel.appendChild(opt1);
          var opt2 = document.createElement('option');
          opt2.value = m.judge_model;
          opt2.textContent = label;
          csel.appendChild(opt2);
        });
        if (!models.length) {
          sel.innerHTML = '<option value="">(no uploads yet)</option>';
          csel.innerHTML = '<option value="">(no uploads yet)</option>';
        }
        var html = '<h2 class="text-xs font-bold uppercase tracking-widest text-slate-500 mb-4">Uploaded judge models</h2>';
        if (!models.length) {
          html += '<p class="text-slate-400 text-sm">No LLM judge CSV has been uploaded yet.</p>';
        } else {
          html += '<div class="divide-y divide-slate-100">';
          models.forEach(function(m) {
            html += '<div class="py-2 flex items-center justify-between gap-4">' +
              '<div><p class="font-mono font-semibold text-slate-800 text-sm">' + escapeHtml(m.judge_model) + '</p>' +
              '<p class="text-xs text-slate-500">' + (m.completed_rows || 0) + ' complete / ' + m.total_rows + ' rows</p></div>' +
              '<button type="button" class="text-xs text-red-600 hover:underline font-medium" onclick="deleteLlmModel(' + JSON.stringify(m.judge_model) + ')">Delete</button></div>';
          });
          html += '</div>';
        }
        document.getElementById('llm-models-card').innerHTML = html;
      }).catch(function() {
        document.getElementById('llm-models-card').innerHTML = '<p class="text-red-500 text-sm">Error loading models.</p>';
      });
    }

    function escapeHtml(s) {
      if (!s) return '';
      return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
    }

    var pendingScenarioPayload = null;
    try {
      var _sec = sessionStorage.getItem('bws_admin_secret');
      if (_sec) document.getElementById('admin-secret-input').value = _sec;
    } catch (e) {}

    function loadScenarioSummary() {
      var inp = document.getElementById('admin-secret-input');
      var secret = inp.value.trim();
      if (secret) { try { sessionStorage.setItem('bws_admin_secret', secret); } catch (e) {} }
      var box = document.getElementById('scenario-admin-summary');
      box.innerHTML = 'Loading…';
      fetch('/api/admin/scenarios', { headers: { 'Authorization': 'Bearer ' + secret } })
        .then(function(r) { return r.json().then(function(j) { return { ok: r.ok, j: j }; }); })
        .then(function(res) {
          if (!res.ok) {
            box.innerHTML = '<p class="text-red-600">' + escapeHtml(res.j.error || JSON.stringify(res.j)) + '</p>';
            return;
          }
          var j = res.j;
          if (!j.has_payload) {
            box.innerHTML = '<p class="text-slate-600">No scenario set stored in the database yet. Upload a JSON file below, or add <code class="bg-slate-100 px-1 rounded text-xs">scenarios.json</code> at the repo root so the server can seed on startup.</p>';
            return;
          }
          var ids = (j.scenario_ids || []).slice(0, 12);
          var more = (j.scenario_ids || []).length > 12 ? ' (+ ' + ((j.scenario_ids || []).length - 12) + ' more)' : '';
          box.innerHTML = '<p class="text-slate-800"><strong>' + j.scenario_count + '</strong> scenarios &middot; hash <code class="bg-slate-100 px-1 rounded">' + escapeHtml(j.content_hash || '') + '</code></p>' +
            '<p class="text-xs text-slate-500 mt-1">Updated: ' + escapeHtml(j.updated_at || '') + (j.label ? ' &middot; ' + escapeHtml(j.label) : '') + '</p>' +
            '<p class="text-xs font-mono mt-2 break-all">' + escapeHtml(ids.join(', ')) + escapeHtml(more) + '</p>';
        }).catch(function() {
          box.innerHTML = '<p class="text-red-600">Request failed.</p>';
        });
    }

    function openScenarioUploadModal() {
      var fileInput = document.getElementById('scenario-json-file');
      if (!fileInput.files || !fileInput.files[0]) {
        alert('Choose a JSON file first.');
        return;
      }
      var secret = document.getElementById('admin-secret-input').value.trim();
      if (!secret) {
        alert('Enter the admin secret first.');
        return;
      }
      var reader = new FileReader();
      reader.onload = function(ev) {
        try {
          var obj = JSON.parse(ev.target.result);
          if (!obj.scenarios || !Array.isArray(obj.scenarios)) throw new Error('Missing scenarios array');
          pendingScenarioPayload = obj;
          var ids = obj.scenarios.map(function(s) { return s.scenario_id; }).filter(Boolean).slice(0, 24);
          document.getElementById('scenario-modal-preview').textContent =
            'Scenarios: ' + obj.scenarios.length + '\\nIDs (first 24): ' + ids.join(', ');
          document.getElementById('scenario-modal-confirm').checked = false;
          document.getElementById('scenario-modal').classList.remove('hidden');
        } catch (e) {
          alert('Invalid JSON: ' + e.message);
        }
      };
      reader.readAsText(fileInput.files[0], 'UTF-8');
    }

    function closeScenarioModal() {
      document.getElementById('scenario-modal').classList.add('hidden');
      pendingScenarioPayload = null;
    }

    function confirmScenarioUpload() {
      if (!document.getElementById('scenario-modal-confirm').checked) {
        alert('Confirm the checkbox to proceed.');
        return;
      }
      if (!pendingScenarioPayload) return;
      var secret = document.getElementById('admin-secret-input').value.trim();
      var msg = document.getElementById('scenario-upload-msg');
      msg.textContent = 'Uploading…';
      var body = JSON.parse(JSON.stringify(pendingScenarioPayload));
      body.confirm = true;
      fetch('/api/admin/scenarios', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer ' + secret
        },
        body: JSON.stringify(body)
      }).then(function(r) { return r.json().then(function(j) { return { ok: r.ok, j: j }; }); })
        .then(function(res) {
          closeScenarioModal();
          if (!res.ok) {
            msg.className = 'text-sm mt-3 text-red-600';
            var t = res.j.error || JSON.stringify(res.j);
            if (res.j.details && res.j.details.length) t += ' — ' + res.j.details.slice(0, 5).join('; ');
            msg.textContent = t;
            return;
          }
          msg.className = 'text-sm mt-3 text-emerald-700';
          msg.textContent = 'Saved ' + res.j.scenario_count + ' scenarios (hash ' + res.j.content_hash + ').';
          loadScenarioSummary();
        }).catch(function() {
          closeScenarioModal();
          msg.className = 'text-sm mt-3 text-red-600';
          msg.textContent = 'Upload failed.';
        });
    }

    function deleteLlmModel(model) {
      if (!confirm('Delete all rows for judge model: ' + model + '?')) return;
      fetch('/api/llm-judge/' + encodeURIComponent(model), { method: 'DELETE' })
        .then(r => r.json()).then(function() { loadLlmModels(); }).catch(function() { alert('Delete failed'); });
    }

    function uploadLlmCsv(ev) {
      ev.preventDefault();
      var msg = document.getElementById('llm-upload-msg');
      var input = document.getElementById('llm-csv-file');
      if (!input.files || !input.files[0]) return false;
      var fd = new FormData();
      fd.append('file', input.files[0]);
      msg.textContent = 'Uploading...';
      fetch('/api/llm-judge/upload', { method: 'POST', body: fd })
        .then(function(r) { return r.json().then(function(j) { return { ok: r.ok, j: j }; }); })
        .then(function(res) {
          if (!res.ok) {
            msg.className = 'text-sm mt-3 text-red-600';
            msg.textContent = res.j.error || JSON.stringify(res.j);
            return;
          }
          msg.className = 'text-sm mt-3 text-emerald-700';
          msg.textContent = 'Imported ' + res.j.rows_processed + ' row(s). Skipped: ' + res.j.rows_skipped + '.';
          if (res.j.errors && res.j.errors.length) {
            msg.textContent += ' First issues: ' + res.j.errors.slice(0, 3).join(' | ');
          }
          input.value = '';
          loadLlmModels();
        }).catch(function() {
          msg.className = 'text-sm mt-3 text-red-600';
          msg.textContent = 'Upload failed.';
        });
      return false;
    }

    function loadLlmScores() {
      var model = document.getElementById('llm-model-select').value;
      if (!model) {
        alert('Select a judge model first.');
        return;
      }
      document.getElementById('llm-scores-card').innerHTML = '<div class="animate-pulse h-40 bg-slate-100 rounded-xl"></div>';
      document.getElementById('llm-scenario-card').innerHTML = '<div class="animate-pulse h-40 bg-slate-100 rounded-xl"></div>';
      fetch('/api/llm-judge/scores?model=' + encodeURIComponent(model)).then(r => r.json()).then(function(d) {
        if (d.error) {
          document.getElementById('llm-scores-card').innerHTML = '<p class="text-red-500 text-sm">' + escapeHtml(d.error) + '</p>';
          document.getElementById('llm-scenario-card').innerHTML = '';
          return;
        }
        renderScores(d, 'llm-scores-card', 'llm-scenario-card', 'LLM judge &mdash; BWS Scores (' + escapeHtml(model) + ')');
        renderPerScenario(d, 'llm-scenario-card');
      }).catch(function() {
        document.getElementById('llm-scores-card').innerHTML = '<p class="text-red-500 text-sm">Error loading LLM scores.</p>';
        document.getElementById('llm-scenario-card').innerHTML = '';
      });
    }

    function loadComparison() {
      var model = document.getElementById('compare-model-select').value;
      if (!model) {
        alert('Select a judge model first.');
        return;
      }
      document.getElementById('compare-summary-card').innerHTML = '<div class="animate-pulse h-24 bg-slate-100 rounded-xl"></div>';
      document.getElementById('compare-side-card').innerHTML = '<div class="animate-pulse h-32 bg-slate-100 rounded-xl"></div>';
      document.getElementById('compare-diff-overall-card').innerHTML = '<div class="animate-pulse h-24 bg-slate-100 rounded-xl"></div>';
      document.getElementById('compare-per-scenario-card').innerHTML = '<div class="animate-pulse h-40 bg-slate-100 rounded-xl"></div>';
      fetch('/api/comparison?model=' + encodeURIComponent(model)).then(r => r.json()).then(function(d) {
        if (d.error) {
          document.getElementById('compare-summary-card').innerHTML = '<p class="text-red-500 text-sm">' + escapeHtml(d.error) + '</p>';
          return;
        }
        var s = d.summary;
        document.getElementById('compare-summary-card').innerHTML =
          '<h2 class="text-xs font-bold uppercase tracking-widest text-slate-500 mb-4">Summary (human &minus; LLM)</h2>' +
          '<div class="grid grid-cols-3 gap-4 text-sm">' +
          '<div class="bg-slate-50 rounded-xl p-3"><p class="text-xs text-slate-500">Mean |diff| cognitive</p><p class="text-lg font-bold text-slate-800">' + (s.mean_abs_diff.cognitive != null ? s.mean_abs_diff.cognitive : '—') + '</p></div>' +
          '<div class="bg-slate-50 rounded-xl p-3"><p class="text-xs text-slate-500">Mean |diff| affective</p><p class="text-lg font-bold text-slate-800">' + (s.mean_abs_diff.affective != null ? s.mean_abs_diff.affective : '—') + '</p></div>' +
          '<div class="bg-slate-50 rounded-xl p-3"><p class="text-xs text-slate-500">Largest per-scenario MAE</p><p class="text-lg font-bold text-slate-800">' + (s.worst_scenario_mae != null ? s.worst_scenario_mae : '—') + '</p><p class="text-xs font-mono text-slate-500 mt-1">' + (s.worst_scenario || '—') + '</p></div>' +
          '</div>' +
          '<p class="text-xs text-slate-500 mt-3">Pearson r (mean per-scenario scores): cognitive ' + (s.pearson_r.cognitive_per_scenario_mean != null ? s.pearson_r.cognitive_per_scenario_mean : '—') +
          ', affective ' + (s.pearson_r.affective_per_scenario_mean != null ? s.pearson_r.affective_per_scenario_mean : '—') + '</p>';

        var hu = d.human_scores;
        var ll = d.llm_scores;
        if (hu.meta.total_annotations < 1) {
          document.getElementById('compare-side-card').innerHTML = '<p class="text-amber-700 text-sm">No completed human annotations.</p>';
        } else if (ll.meta.total_annotations < 1) {
          document.getElementById('compare-side-card').innerHTML = '<p class="text-amber-700 text-sm">No completed rows for this LLM judge.</p>';
        } else {
          var sideHtml = '<h2 class="text-xs font-bold uppercase tracking-widest text-slate-500 mb-4">Overall scores side by side</h2>' +
            '<div class="overflow-x-auto"><table class="w-full text-sm border-collapse"><thead><tr class="text-left text-xs text-slate-500">' +
            '<th class="pb-2 pr-2">Item</th><th class="pb-2 pr-2">Human cog</th><th class="pb-2 pr-2">LLM cog</th><th class="pb-2 pr-2">&Delta;</th>' +
            '<th class="pb-2 pr-2">Human aff</th><th class="pb-2 pr-2">LLM aff</th><th class="pb-2">&Delta;</th></tr></thead><tbody>';
          var keys = new Set();
          Object.keys(hu.cognitive).forEach(function(k) { keys.add(k); });
          Object.keys(ll.cognitive).forEach(function(k) { keys.add(k); });
          Object.keys(hu.affective).forEach(function(k) { keys.add(k); });
          Object.keys(ll.affective).forEach(function(k) { keys.add(k); });
          Array.from(keys).sort().forEach(function(k) {
            var hc = hu.cognitive[k], lc = ll.cognitive[k], ha = hu.affective[k], la = ll.affective[k];
            var dc = (hc != null && lc != null) ? (hc - lc) : null;
            var da = (ha != null && la != null) ? (ha - la) : null;
            sideHtml += '<tr class="border-t border-slate-100"><td class="py-2 font-semibold text-slate-800">' + friendlyName(k) + '</td>' +
              '<td class="py-2 font-mono">' + (hc != null ? hc.toFixed(3) : '—') + '</td>' +
              '<td class="py-2 font-mono">' + (lc != null ? lc.toFixed(3) : '—') + '</td>' +
              '<td class="py-2 font-mono ' + (dc != null && Math.abs(dc) < 0.2 ? 'text-emerald-600' : 'text-amber-700') + '">' + (dc != null ? dc.toFixed(3) : '—') + '</td>' +
              '<td class="py-2 font-mono">' + (ha != null ? ha.toFixed(3) : '—') + '</td>' +
              '<td class="py-2 font-mono">' + (la != null ? la.toFixed(3) : '—') + '</td>' +
              '<td class="py-2 font-mono ' + (da != null && Math.abs(da) < 0.2 ? 'text-emerald-600' : 'text-amber-700') + '">' + (da != null ? da.toFixed(3) : '—') + '</td></tr>';
          });
          sideHtml += '</tbody></table></div>';
          document.getElementById('compare-side-card').innerHTML = sideHtml;
        }

        var dc = d.differences.cognitive;
        var da = d.differences.affective;
        var diffHtml = '<h2 class="text-xs font-bold uppercase tracking-widest text-slate-500 mb-4">Overall score difference (human &minus; LLM)</h2>' +
          '<div class="flex flex-wrap gap-8"><div class="flex-1 min-w-[260px]"><h3 class="text-sm font-bold text-indigo-700 mb-2">Cognitive</h3><ul class="space-y-1 text-sm">';
        Object.keys(dc).sort().forEach(function(k) {
          diffHtml += '<li class="flex justify-between gap-4"><span>' + friendlyName(k) + '</span><span class="font-mono font-bold">' + dc[k].toFixed(3) + '</span></li>';
        });
        diffHtml += '</ul></div><div class="flex-1 min-w-[260px]"><h3 class="text-sm font-bold text-violet-700 mb-2">Affective</h3><ul class="space-y-1 text-sm">';
        Object.keys(da).sort().forEach(function(k) {
          diffHtml += '<li class="flex justify-between gap-4"><span>' + friendlyName(k) + '</span><span class="font-mono font-bold">' + da[k].toFixed(3) + '</span></li>';
        });
        diffHtml += '</ul></div></div>';
        document.getElementById('compare-diff-overall-card').innerHTML = diffHtml;

        var ps = d.per_scenario;
        var sids = Object.keys(ps).sort();
        if (!sids.length) {
          document.getElementById('compare-per-scenario-card').innerHTML = '<p class="text-slate-400 text-sm">No overlapping scenarios.</p>';
          return;
        }
        var allItems = new Set();
        sids.forEach(function(sid) {
          Object.keys(ps[sid].cognitive || {}).forEach(function(k) { allItems.add(k); });
          Object.keys(ps[sid].affective || {}).forEach(function(k) { allItems.add(k); });
        });
        var items = Array.from(allItems).sort();
        function diffTable(title, dim, showMae) {
          var html = '<h3 class="text-sm font-bold text-slate-700 mb-2">' + title + '</h3>' +
            '<div class="overflow-x-auto"><table class="w-full text-left border-collapse text-xs">' +
            '<thead><tr><th class="text-slate-500 pb-2 pr-2">Scenario</th>';
          items.forEach(function(it) { html += '<th class="text-slate-500 pb-2 px-1 text-center">' + friendlyName(it) + '</th>'; });
          if (showMae) html += '<th class="text-slate-500 pb-2 pl-2 text-center" title="Mean abs diff (cog+aff)">MAE</th>';
          html += '</tr></thead><tbody>';
          sids.forEach(function(sid) {
            var row = ps[sid][dim] || {};
            var mae = ps[sid].mean_abs_diff;
            html += '<tr class="border-t border-slate-100"><td class="py-1.5 pr-2 font-mono text-slate-600">' + sid.replace('_', ' ') + '</td>';
            items.forEach(function(it) {
              var v = row[it];
              if (v === undefined) {
                html += '<td class="py-1.5 px-1"><div class="heatcell" style="background:#F8FAFC;color:#94A3B8;">-</div></td>';
              } else {
                html += '<td class="py-1.5 px-1"><div class="heatcell" style="' + diffHeatColor(v) + '">' + v.toFixed(2) + '</div></td>';
              }
            });
            if (showMae) {
              html += '<td class="py-1.5 pl-2 text-center text-slate-500">' + (mae != null ? mae.toFixed(2) : '-') + '</td>';
            }
            html += '</tr>';
          });
          html += '</tbody></table></div>';
          return html;
        }
        document.getElementById('compare-per-scenario-card').innerHTML =
          '<h2 class="text-xs font-bold uppercase tracking-widest text-slate-500 mb-4">Per-scenario difference (human &minus; LLM)</h2>' +
          '<div class="space-y-6">' + diffTable('Cognitive', 'cognitive', true) + diffTable('Affective', 'affective', false) + '</div>';
      }).catch(function() {
        document.getElementById('compare-summary-card').innerHTML = '<p class="text-red-500 text-sm">Error loading comparison.</p>';
      });
    }

    // Auto-load scores on page load
    loadScores();
    loadLlmModels();
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
    print("  Database: PostgreSQL (DATABASE_URL)")
    print()
    app.run(debug=args.debug, host=args.host, port=args.port)
