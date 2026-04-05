# LLM-as-a-Judge

This folder contains a small batch pipeline that uses an **OpenAI chat model** as an automated annotator for the same **Best–Worst Scaling (BWS)** task human annotators perform in the BWS Empathy Annotation app: for each scenario, pick which of three counselor responses (**A**, **B**, **C**) shows the **most** and **least** **cognitive empathy**, then the **most** and **least** **affective empathy**.

The script is [`judge.py`](judge.py). It reads a **scenarios JSON** file, calls the API **once per scenario**, and writes a **CSV** whose columns match the app’s export format (`CSV_COLUMNS` in the main server).

---

## Why this exists

- **Human annotations** in the app are stored as rows with BWS choices plus optional reasoning fields.
- **LLM-as-a-Judge** lets you generate **parallel “machine judge” labels** on the same scenarios for comparison, inter-rater–style analysis, or pilot runs—without changing the app database unless you explicitly import the CSV.

The judge is **not** given which response is human vs LLM: it only sees **context + text of A, B, C**. Labels like `HUMAN` / `LLM_COGNITIVE` / `LLM_AFFECTIVE` come from your JSON’s `ground_truth_labels` and are written to the CSV for **your** analysis, not sent to the model.

---

## Requirements

- Python **3.9+** (same as the repo’s `pyproject.toml`).
- Dependencies: `openai`, `python-dotenv` (already listed in the project root `pyproject.toml`). Install with **`poetry install`** at the repo root, then run the script with **`poetry run python`**.
- **`OPENAI_API_KEY`** in the environment or in a **`.env`** file at the **repository root** (parent of this folder). The script runs `load_dotenv(<repo_root>/.env)`.

---

## Input: scenarios JSON

Path is passed with **`--scenarios`**, or defaults are applied (see below).

The file must be a JSON object with a top-level **`"scenarios"`** array. Each element is one scenario, typically with:

| Field | Role |
|--------|------|
| `scenario_id` | Stable ID (e.g. `SCENARIO_01`). Used in CSV and `annotation_id`. |
| `context` | Full dialogue context shown to the judge (client/therapist turns). |
| `responses` | List of `{ "response_id": "A" \| "B" \| "C", "text": "..." }`. |
| `ground_truth_labels` | Optional map `A` / `B` / `C` → label strings (e.g. `HUMAN`, `LLM_COGNITIVE`, `LLM_AFFECTIVE`) copied into the CSV only. |

The judge **user message** is built as:

1. `## CONTEXT` + the scenario `context`  
2. `## RESPONSE A` / `B` / `C` + each response’s `text`  
3. A short instruction to return **only** a JSON object with the six keys below  

**Default scenarios path (when `--scenarios` is omitted):**

1. `<repository_root>/gp5-generated-responses.json` if that file exists  
2. Otherwise `./scenarios.json` in the **current working directory**  

If neither exists, the script exits with an error listing both paths.

---

## Output: CSV format

Rows are written to **`output/llm_judge_<annotator_id_sanitized>_<UTC_timestamp>.csv`** (see `--output-dir`).

Columns match the app export (`server.py` → `CSV_COLUMNS`):

| Column | Description |
|--------|-------------|
| `annotation_id` | `{annotator_id}-{scenario_id}` |
| `annotator_id` | Defaults to the uppercased `--model` name unless `--annotator-id` is set |
| `scenario_id` | From JSON |
| `context_snippet` | First ~100 characters of `context` (single line) |
| `response_a_label`, `response_b_label`, `response_c_label` | From `ground_truth_labels` |
| `cognitive_most`, `cognitive_least` | `A`, `B`, or `C` |
| `cognitive_reasoning` | Short text from the model |
| `affective_most`, `affective_least` | `A`, `B`, or `C` |
| `affective_reasoning` | Short text from the model |
| `timestamp` | ISO 8601 UTC when the row was written |
| `session_duration_seconds` | **Wall-clock seconds** for that scenario’s API call (not human session time) |

Some spreadsheets add extra columns (e.g. analysis flags); this script outputs **only** these 15 columns so imports stay aligned with the app.

---

## Prompt design (high level)

- **System message** (`JUDGE_SYSTEM_PROMPT` in `judge.py`): Uses the **same plain-language task as human annotators** in the app (see `WelcomeScreen.jsx` / `ScenarioPanel.jsx`): *Cognitive empathy* = understanding the client’s perspective and situation; *Affective empathy* = validating the client’s emotional experience. It deliberately **does not** reuse the theoretical wording from [`prompts.py`](../prompts.py) (top-down/bottom-up, “complex reflection,” etc.). That separation reduces **circular evaluation**: the generation prompts are tuned to produce obvious cognitive vs affective “fingerprints,” and a judge trained on identical theory tends to always pick B/C over the human turn.
- **Bias mitigation in the prompt**: Instructions to judge like a **human reader**, to value **natural, genuine** replies over heavy therapeutic or emotional vocabulary, and **not** to prefer responses merely because they use more explicit emotion words (aligned with concerns in the proposal / Bagdon et al. on LLM-as-judge bias).
- **User message**: Context + three responses + JSON-only instruction.
- **API**: `chat.completions.create` with `response_format={"type": "json_object"}` so the model returns parseable JSON.
- **Validation**: Each of `cognitive_most` / `cognitive_least` / `affective_most` / `affective_least` must be `A`/`B`/`C`, and within each pair, most ≠ least. Failed parses or invalid values trigger retries with backoff.

---

## Command-line usage

Run from the repository root (recommended):

```bash
poetry run python LLM-as-a-judge/judge.py
```

Common options:

| Flag | Meaning |
|------|---------|
| `--scenarios PATH` | Explicit scenarios JSON |
| `--model NAME` | OpenAI model name (default: `gpt-5.4` unless changed in `judge.py`) |
| `--annotator-id ID` | CSV `annotator_id` and prefix for `annotation_id` (default: uppercased `--model`) |
| `--output-dir DIR` | Where to write the CSV (default: `LLM-as-a-judge/output`) |
| `--limit N` | Only process the first **N** scenarios (smoke tests) |
| `-q`, `--quiet` | Turn off `[debug]` lines (fingerprints, per-row summary, end counts) |
| `--show-api` | Print **full** system prompt, user message, and **raw** model JSON to **stderr** per scenario |

Examples:

```bash
# Full run with default scenarios file at repo root
poetry run python LLM-as-a-judge/judge.py

# First 3 scenarios, full API trace
poetry run python LLM-as-a-judge/judge.py --limit 3 --show-api

# Quiet run but still see nothing extra (useful when piping CSV only from stdout—note: CSV is written to file, not stdout)
poetry run python LLM-as-a-judge/judge.py --quiet

# Custom model and annotator id for the CSV
poetry run python LLM-as-a-judge/judge.py --model gpt-5.2 --annotator-id GPT-5.2-JUDGE
```

---

## Debugging behavior

When **not** using `--quiet`, stderr includes:

- Resolved **project root**, JSON **file size**, top-level JSON **keys**
- Per scenario: **character length** of the user message, **SHA-256 prefixes** of context and A/B/C text (to confirm each row’s inputs differ)
- A line stating that **CSV labels are not sent to the API**
- After each call: **cognitive / affective** letters and **API duration**
- At the end: **counts** of combined patterns like `cog:BA_aff:CA`

If many rows share the **same** BWS pattern but the **hashes differ** per scenario, the inputs are not duplicated; the model may still **prefer** one letter for “most cognitive” and another for “most affective” because of how **B** and **C** were generated (cognitive- vs affective-conditioned). The judge prompt is aligned with **human** app instructions and avoids mirroring generation-prompt theory, but strong dominance of one pattern can still reflect **stimulus design**. Use the hashes to verify inputs, and compare distributions to **human** annotations for your study.

**`--show-api`** is the detailed trace: full **system** text, **user** text, and **raw** assistant string (JSON).

---

## Importing results into the app

The admin CSV import path in the server expects the same column set as export. Use the generated file as-is, or merge with human exports in your analysis tool. If you rely on `annotator_id` to distinguish judges, set **`--annotator-id`** so LLM rows don’t collide with human IDs.

---

## Troubleshooting

| Issue | What to check |
|--------|----------------|
| `OPENAI_API_KEY` error | `.env` at repo root or exported env var |
| Default scenarios not found | Run from repo root, or pass `--scenarios` explicitly |
| Repeated BWS letters | Compare `--show-api` across scenarios; check hash lines; review stimulus design |
| JSON / validation failures | Model returned non-JSON or invalid letters; stderr may include last raw output on hard failure |
| Rate limits / timeouts | Retries are limited; rerun with `--limit` or smaller batches |

---

## Files in this directory

| Path | Purpose |
|------|---------|
| `judge.py` | Main script |
| `output/` | Default directory for timestamped CSV outputs (git may ignore large CSVs—add if needed) |
| `README.md` | This document |

For the main application (Flask server, DB, human UI), see the repository root `server.py` and `frontend/`.
