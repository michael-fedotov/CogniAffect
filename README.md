# CogniAffect - BWS Empathy Annotation App

An interactive Best-Worst Scaling (BWS) annotation tool for evaluating cognitive and affective empathy in therapeutic dialogue responses. Includes a Flask backend that collects all annotations from all annotators in a central SQLite database.

## Files

| File | Description |
|---|---|
| `index.html` | The complete frontend application |
| `server.py` | Flask backend server (recommended) |
| `scenarios.json` | Input data: therapy scenarios with 3 responses each |
| `sample_output.csv` | Example of the exported CSV format |
| `pyproject.toml` | Poetry project and dependency configuration |
| `requirements.txt` | Fallback pip dependency list |
| `README.md` | This file |

---

## Quickstart (Recommended: Flask Server)

This is the correct way to run the app for a study with multiple annotators.

### 1. Install dependencies

**With Poetry (recommended):**

If you don't have Poetry yet, install it once:
```bash
curl -sSL https://install.python-poetry.org | python3 -
```

Then, from the project folder, install all dependencies into an isolated virtual environment:
```bash
cd "Directed Readings BWS Annotation"
poetry install
```

Poetry reads `pyproject.toml`, resolves exact versions, writes a `poetry.lock` file (committed to version control so every collaborator gets identical dependencies), and creates a virtual environment automatically.

**With pip (fallback, no Poetry):**
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

**Custom port** (any of these work):
```bash
python server.py --port 8080
python server.py -p 8080
PORT=8080 python server.py        # environment variable
```

**Other flags:**
```bash
python server.py --help           # show all options
python server.py --debug          # enable auto-reload during development
python server.py --host 127.0.0.1 # bind to localhost only (not LAN-accessible)
```

You will see:

```
  BWS Empathy Annotation Server
  ─────────────────────────────────────────
  App:      http://localhost:5000
  Admin:    http://localhost:5000/admin
  Export:   http://localhost:5000/api/export/csv
  Database: /path/to/annotations.db
```

### 3. Share with annotators

- **Local network**: Share `http://YOUR_IP:5000` (find your IP with `ifconfig` / `ipconfig`)
- **Remote/hosted**: Deploy to Render, Railway, or any VPS (see Deployment section below)

Each annotator opens the URL, enters their ID, and annotates. All responses go directly into `annotations.db`.

### 4. Collect results

Open `http://localhost:5000/admin` in your browser to:
- See how many annotators have completed their sessions
- Download individual annotator CSVs
- Download **all annotations in one CSV** file

Or download directly:
```
http://localhost:5000/api/export/csv
```

---

## Fallback: No Server (localStorage only)

If you cannot run a server, annotators can open `index.html` directly in their browser:

1. Double-click `index.html` to open it
2. When prompted, upload `scenarios.json` using the file picker
3. Annotate all scenarios
4. Click **Download My Annotations (CSV)** on the completion screen
5. Each annotator emails you their CSV file

> Note: When running without a server, the "Download from Server" button on the completion screen will not work. The "Download My Annotations (CSV)" button always works.

---

## Workflow

### For annotators
1. Open `http://localhost:5000` in a browser
2. Enter your Annotator ID (or leave blank to auto-generate one like `ANNO_042`)
3. Annotate each scenario by answering two questions:
   - **Cognitive Empathy**: Which response best/least shows understanding of the client's perspective?
   - **Affective Empathy**: Which response best/least validates the client's emotional experience?
4. Add optional reasoning notes for each question
5. Navigate freely — skip and return to scenarios using the sidebar
6. Click **Finish & Export** on the last scenario
7. Download your CSV from the completion screen (or the researcher collects it from the admin panel)

### For the researcher
1. Run `python server.py`
2. Send the URL to annotators
3. Monitor progress at `http://localhost:5000/admin`
4. When all annotators are done, download `http://localhost:5000/api/export/csv`

---

## Session Recovery

- Annotations sync to the server **automatically every 30 seconds** and after every annotation change (1.5s debounce)
- Progress is also saved to the browser's **localStorage** as a local backup
- If an annotator accidentally closes the browser, they can re-open the app and enter their ID — the server restores their session automatically
- The header shows a sync status indicator: **Server synced** (green) / **Syncing…** (spinning) / **Local only** (amber — server unreachable)

---

## Adding More Scenarios

Edit `scenarios.json` following this structure:

```json
{
  "annotator_id": null,
  "import_timestamp": "2024-01-01T00:00:00Z",
  "scenarios": [
    {
      "scenario_id": "SCENARIO_04",
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

Response order is randomized automatically per annotator. `ground_truth_labels` are never shown to annotators — only stored in the CSV output after unblinding.

---

## CSV Output Format

The exported CSV has the following columns:

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
| `timestamp` | ISO 8601 timestamp when the annotation was completed |
| `session_duration_seconds` | Time spent on this scenario (seconds) |

> **Important**: `response_a_label` through `response_c_label` reflect the *displayed* order after per-annotator randomization. For example, if shuffling placed the original `LLM_AFFECTIVE` response in display position A, then `response_a_label = LLM_AFFECTIVE`. Match `cognitive_most` / `cognitive_least` (display letters A/B/C) against `response_*_label` for analysis.

---

## API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/` | GET | Serves the annotation app |
| `/scenarios.json` | GET | Serves the scenarios data |
| `/admin` | GET | Admin dashboard |
| `/api/sync` | POST | Receive and store session + annotations |
| `/api/session/<id>` | GET | Retrieve a saved session by annotator ID |
| `/api/export/csv` | GET | Download all annotations (all annotators) |
| `/api/export/csv/<id>` | GET | Download annotations for one annotator |
| `/api/annotators` | GET | JSON list of annotators with completion stats |
| `/api/status` | GET | JSON summary of database state |

---

## Downstream Analysis

Load all annotations in Python:

```python
import pandas as pd

# From server export
df = pd.read_csv("all_annotations_20240222_103000.csv")

# Map display labels back to ground truth
def true_label(row, display_letter):
    return row[f"response_{display_letter.lower()}_label"]

df['cognitive_most_label']  = df.apply(lambda r: true_label(r, r['cognitive_most']), axis=1)
df['cognitive_least_label'] = df.apply(lambda r: true_label(r, r['cognitive_least']), axis=1)
df['affective_most_label']  = df.apply(lambda r: true_label(r, r['affective_most']), axis=1)
df['affective_least_label'] = df.apply(lambda r: true_label(r, r['affective_least']), axis=1)

# BWS score = (times chosen as MOST - times chosen as LEAST) / total appearances
bws = df.groupby(['scenario_id', 'cognitive_most_label']).size() - \
      df.groupby(['scenario_id', 'cognitive_least_label']).size()
```

---

## Deployment (Optional)

To host the server so annotators can access it remotely without being on your network:

### Render (free tier)
1. Push this folder to a GitHub repository
2. Create a new **Web Service** on [render.com](https://render.com)
3. Set the build command: `pip install -r requirements.txt`
4. Set the start command: `python server.py`
5. Share the Render URL with annotators

### Railway
```bash
npm install -g @railway/cli
railway login
railway init
railway up
```

### Quick tunnel (temporary, for testing)
```bash
# Using ngrok
ngrok http 5000
# Using VS Code / Cursor port forwarding
# Right-click port 5000 in the Ports tab → Make Public
```

---

## Technical Notes

- **No data leaves your server** — all annotations are stored in `annotations.db` on the machine running `server.py`
- **SQLite** — zero-configuration, the database file is created automatically on first run
- **Graceful offline fallback** — if the server is unreachable, the frontend silently saves to localStorage and shows "Local only"
- **Idempotent sync** — re-submitting the same annotation updates it (`INSERT OR REPLACE`), so retries are safe
- **Responsive** — works on desktop and mobile browsers

---

## Poetry Reference

All common tasks using Poetry:

```bash
# Install / sync all dependencies from pyproject.toml + poetry.lock
poetry install

# Run the server inside Poetry's virtual environment
poetry run python server.py

# Open a shell inside the virtual environment
poetry shell
python server.py   # then run directly

# Add a new dependency (e.g. if you extend the project)
poetry add flask-cors

# Add a dev-only dependency (e.g. for testing)
poetry add --group dev pytest

# Update all dependencies to their latest allowed versions
poetry update

# Show installed packages and their versions
poetry show

# Export to requirements.txt (for environments without Poetry)
poetry export -f requirements.txt --output requirements.txt --without-hashes

# Check for dependency conflicts or issues
poetry check
```

The `poetry.lock` file is generated automatically on the first `poetry install`. Commit it to version control so every collaborator (and any future deployment) uses the exact same package versions.

---

## Troubleshooting

**"Local only" badge shows in the header**
→ The server is not reachable. Make sure `python server.py` is running and the URL is correct.

**Annotator can't see their previous session**
→ Make sure they use the same Annotator ID. The server matches sessions by ID.

**`ModuleNotFoundError: No module named 'flask'`**
→ With Poetry: run `poetry install`. With pip: run `pip install flask` (or `pip3 install flask`).

**`poetry: command not found`**
→ Install Poetry: `curl -sSL https://install.python-poetry.org | python3 -` then restart your terminal.

**CSV fields contain strange characters in Excel**
→ Use Data → From Text/CSV with UTF-8 encoding, or open in Google Sheets which handles UTF-8 automatically.
