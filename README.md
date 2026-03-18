# CogniAffect — BWS Empathy Annotation Tool

An interactive **Best-Worst Scaling (BWS)** annotation tool for evaluating cognitive and affective empathy in therapeutic dialogue responses. Annotators compare three candidate responses to a therapy excerpt and select which is **most** and **least** empathic across two dimensions (cognitive and affective). All responses are stored centrally in a SQLite database and can be exported as CSV for analysis.

---

## Project Structure

```
/
├── server.py             # Flask backend — API, database, admin dashboard
├── scenarios.json        # Study stimuli: therapy scenarios + 3 responses each
├── annotations.db        # SQLite database (auto-created on first run)
├── requirements.txt      # Pip fallback dependency list
├── pyproject.toml        # Poetry project configuration
├── sample_output.csv     # Example of the exported CSV format
└── frontend/             # React + Vite source code
    ├── src/
    │   ├── views/        # Page-level components (WelcomeScreen, AnnotationScreen, etc.)
    │   ├── utils/        # API client, localStorage helpers, annotation logic
    │   └── state/        # Reducer + action types for annotation state
    ├── vite.config.js    # Build config — outputs to ../dist, proxies /api in dev
    └── README.md         # Frontend-specific deployment notes
```

After running a production build, a `dist/` folder appears at the project root. Flask serves from this folder automatically.

---

## Quickstart — Running Locally

### Prerequisites

- **Python 3.9+**
- **Node.js 18+** and **npm** (only needed if you want to modify the frontend)
- **Poetry** (recommended Python package manager) — install once with:
  ```bash
  curl -sSL https://install.python-poetry.org | python3 -
  ```

### 1. Install Python dependencies

**With Poetry (recommended):**
```bash
cd "Directed Readings BWS Annotation"
poetry install
```

Poetry creates an isolated virtual environment and installs exact versions from `poetry.lock`. Every collaborator and every deployment gets identical packages.

**With pip (no Poetry):**
```bash
pip install -r requirements.txt
```

### 2. Start the server

**With Poetry:**
```bash
poetry run python server.py
```

**With pip:**
```bash
python server.py
```

**Custom port or options:**
```bash
python server.py --port 8080     # change port
python server.py --debug         # enable auto-reload on file changes
python server.py --help          # see all flags
```

The terminal will print:

```
  BWS Empathy Annotation Server
  ─────────────────────────────────────────
  App:      http://localhost:5000
  Admin:    http://localhost:5000/admin
  Export:   http://localhost:5000/api/export/csv
  Database: /path/to/annotations.db
```

### 3. Open the app

- **Annotators**: open `http://localhost:5000` — they enter an ID and annotate.
- **Researcher (admin)**: open `http://localhost:5000/admin` — see completion status and download CSVs.

To share with annotators on your local network, give them `http://YOUR_IP:5000` (find your IP with `ifconfig` on Mac/Linux or `ipconfig` on Windows).

---

## Annotator Workflow

1. Open the app URL in a browser.
2. Enter an **Annotator ID** (or leave blank for an auto-generated ID like `ANNO_042`).
3. For each therapy scenario, read the context and three anonymized responses (A, B, C).
4. Answer two BWS questions:
   - **Cognitive Empathy** — which response best / least shows understanding of the client's perspective?
   - **Affective Empathy** — which response best / least validates the client's emotional experience?
5. Optionally type a free-text reasoning note for each question.
6. Navigate freely via the sidebar — skip and return to any scenario.
7. Click **Finish & Export** on the final scenario.
8. Download the personal CSV from the completion screen (or the researcher collects everything from the admin panel).

**Session recovery**: annotations sync to the server every 30 seconds and within 1.5 seconds of each change. If the browser is closed, reopening the app and entering the same ID restores the full session from the server. A status badge in the header shows **Server synced** (green), **Syncing…**, or **Local only** (amber — server unreachable, saving to browser localStorage as backup).

---

## Researcher Workflow

1. Run `python server.py` (or deploy it, see below).
2. Share the URL with annotators.
3. Monitor progress at `/admin` — shows completion counts per annotator.
4. When all annotators are done, download the combined CSV from `/api/export/csv`.

---

## Frontend Development

The frontend is a React + Vite single-page application. You only need to touch this if you want to change the UI.

### Dev server (hot reload)

```bash
cd frontend
npm install          # first time only
npm run dev
```

Vite serves the app at `http://localhost:5173`. API calls (`/api/...`, `/admin`) are automatically proxied to Flask at `http://localhost:5000`. `scenarios.json` is served by a Vite middleware from the project root — no file copying needed. Flask must be running separately.

If Flask is on a port other than 5000:
```bash
FLASK_PROXY_TARGET=http://localhost:5001 npm run dev
```

### Production build

```bash
cd frontend
npm run build
```

Output goes to `dist/` at the **project root** (configured in `vite.config.js` as `outDir: '../dist'`). Running `python server.py` afterward serves this build automatically.

---

## Deployment on Render

The app is deployed in two parts on [Render](https://render.com):

```
Browser
  │
  ├── Static Site (frontend bundle at dist/)
  │     URL: https://<static-site>.onrender.com
  │     Talks to ↓
  │
  └── Web Service (server.py)
        URL: https://cogniaffect.onrender.com
        Serves: /api/*, /admin, /scenarios.json
```

### Web Service (backend — already running)

| Setting | Value |
|---|---|
| Build command | `pip install -r requirements.txt` |
| Start command | `python server.py` |
| Env var `CORS_ORIGINS` | `https://<static-site>.onrender.com` |

`CORS_ORIGINS` is a comma-separated list of allowed frontend origins. If unset, only `https://michael-fedotov.github.io/CogniAffect/` is allowed. To support both the Render static site and GitHub Pages simultaneously:
```
CORS_ORIGINS=https://<static-site>.onrender.com,https://michael-fedotov.github.io/CogniAffect/
```

### Static Site (frontend)

| Setting | Value |
|---|---|
| Build command | `cd frontend && npm ci && npm run build` |
| Publish directory | `dist` |
| Env var `VITE_API_BASE` | `https://cogniaffect.onrender.com` |

`VITE_API_BASE` is baked into the JavaScript bundle at build time. It tells the frontend where the Flask API lives when the static files are not served by Flask itself. No trailing slash.

### GitHub Pages (existing deploy — no changes needed)

The frontend detects the `michael-fedotov.github.io` hostname at runtime and automatically uses `https://cogniaffect.onrender.com` as the API base. `VITE_API_BASE` is not required for this path.

### Accessing the app via the Web Service URL directly

You can also open the app directly at `https://cogniaffect.onrender.com` (without a separate static site). Flask serves the built `dist/` bundle, so the frontend and API share the same origin — no `VITE_API_BASE` or CORS configuration is needed in this case. This is the simplest option.

> **Render free tier note**: the Web Service spins down after 15 minutes of inactivity. The first request after a cold start can take ~30 seconds. The app shows a "Waking up the server…" banner during this time — annotators should wait for it to disappear before proceeding.

---

## Scenarios File (`scenarios.json`)

Each scenario represents a therapy excerpt with three candidate responses. Edit this file to change the study stimuli.

```json
{
  "annotator_id": null,
  "import_timestamp": "2024-01-01T00:00:00Z",
  "scenarios": [
    {
      "scenario_id": "SCENARIO_01",
      "context": "Therapist: ...\n\nClient: ...",
      "responses": [
        { "response_id": "A", "text": "..." },
        { "response_id": "B", "text": "..." },
        { "response_id": "C", "text": "..." }
      ],
      "ground_truth_labels": {
        "A": "HUMAN",
        "B": "LLM_COGNITIVE",
        "C": "LLM_AFFECTIVE"
      }
    }
  ]
}
```

- Response order is **randomized per annotator** — the A/B/C labels annotators see are not the same as the IDs in the file.
- `ground_truth_labels` are never shown to annotators. They appear in the exported CSV after unblinding so you can map selections back to condition.

---

## CSV Output Format

| Column | Description |
|---|---|
| `annotation_id` | Unique ID: `{annotator_id}_S{scenario_number}` |
| `annotator_id` | The annotator's identifier |
| `scenario_id` | Scenario identifier (e.g., `SCENARIO_01`) |
| `context_snippet` | First 100 characters of the therapy context |
| `response_a_label` | Ground truth label for displayed Response A |
| `response_b_label` | Ground truth label for displayed Response B |
| `response_c_label` | Ground truth label for displayed Response C |
| `cognitive_most` | Response selected as MOST cognitively empathic (A/B/C) |
| `cognitive_least` | Response selected as LEAST cognitively empathic (A/B/C) |
| `cognitive_reasoning` | Optional free-text explanation |
| `affective_most` | Response selected as MOST affectively empathic (A/B/C) |
| `affective_least` | Response selected as LEAST affectively empathic (A/B/C) |
| `affective_reasoning` | Optional free-text explanation |
| `timestamp` | ISO 8601 timestamp of annotation completion |
| `session_duration_seconds` | Time spent on this scenario |

**Important**: `response_a_label` through `response_c_label` reflect the *displayed* order after per-annotator randomization. To recover the true condition, match `cognitive_most` / `cognitive_least` (display letter A/B/C) against `response_*_label`:

```python
import pandas as pd

df = pd.read_csv("all_annotations.csv")

def true_label(row, display_letter):
    return row[f"response_{display_letter.lower()}_label"]

df['cognitive_most_label']  = df.apply(lambda r: true_label(r, r['cognitive_most']), axis=1)
df['cognitive_least_label'] = df.apply(lambda r: true_label(r, r['cognitive_least']), axis=1)
df['affective_most_label']  = df.apply(lambda r: true_label(r, r['affective_most']), axis=1)
df['affective_least_label'] = df.apply(lambda r: true_label(r, r['affective_least']), axis=1)
```

---

## API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/` | GET | Serves the annotation app |
| `/scenarios.json` | GET | Serves the scenarios data |
| `/admin` | GET | Admin dashboard (completion status, CSV download) |
| `/api/sync` | POST | Upsert session + annotations from client |
| `/api/session/<id>` | GET | Retrieve a saved session by annotator ID |
| `/api/export/csv` | GET | Download all annotations (all annotators) |
| `/api/export/csv/<id>` | GET | Download annotations for one annotator |
| `/api/annotators` | GET | JSON list of annotators with stats |
| `/api/status` | GET | JSON summary of database state |

---

## Technical Notes

- **SQLite** — zero-configuration; `annotations.db` is created automatically on first run. No database server required.
- **No data leaves your machine** (when running locally) — all annotations stay in `annotations.db`.
- **Idempotent sync** — re-submitting the same annotation updates it (`INSERT OR REPLACE`), so retries and reconnections are safe.
- **Graceful offline fallback** — if the server is unreachable, the frontend saves to `localStorage` and shows "Local only". Data is uploaded to the server the next time it is reachable.
- **CORS** — controlled by the `CORS_ORIGINS` environment variable on the backend (see Deployment section).
- **Responsive** — works on desktop and mobile browsers.

---

## Troubleshooting

**"Local only" badge shows in the header**
→ The server is not reachable. Check that `python server.py` is running and the URL in the browser matches the server's address.

**Annotator cannot see their previous session**
→ They must use the exact same Annotator ID. The server matches sessions by ID string.

**`ModuleNotFoundError: No module named 'flask'`**
→ Run `poetry install` (Poetry) or `pip install -r requirements.txt` (pip).

**`poetry: command not found`**
→ Install Poetry: `curl -sSL https://install.python-poetry.org | python3 -` then open a new terminal window.

**CSV shows garbled characters in Excel**
→ Use Excel's Data → From Text/CSV import with UTF-8 encoding, or open in Google Sheets (handles UTF-8 automatically).

**Render app takes 30+ seconds to respond on first load**
→ Expected on the free tier (server spins down when idle). The "Waking up the server…" banner will disappear once it is ready.
