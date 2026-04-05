# Dataset generation (BWS transcript set)

This folder builds the **annotator stimuli** for the CogniAffect Best–Worst Scaling (BWS) study: a fixed set of therapeutic dialogues where each item has **one human listener reply** (ground truth) and **two LLM-generated alternatives** (cognitive vs affective empathy prompts), aligned with the project methodology (multi-turn context, MI-adherent rows where applicable).

The parent app loads a **scenarios JSON** file; scripts here turn raw CSV exports into **`outputs/transcript_set.csv`** and **`outputs/scenarios_transcript_set.json`**.

---

## What this folder contains

| Path | Role |
|------|------|
| **`full_dataset_rows.csv`** | Main **source pool** (default `--input`): many rows per conversation; includes `counsel_chat` and Reddit (`RED`) dialogs. |
| **`shortlist_theraputic.csv`** | Smaller subset of the same schema (useful for quick tests or debugging the pipeline without reprocessing the full pool). |
| **`text_sanitize.py`** | Shared **deterministic** cleanup: Unicode NFKC, HTML entities, common mojibake fixes; keeps Latin accents. Used by the build and export scripts. |
| **`build_transcript_set.py`** | Selects **one row per conversation** (final listener turn), **sanitizes** fields, applies quality filters, **stratified** random sample to **N** dialogs (default 64), writes CSV + build log. |
| **`export_scenarios_from_shortlist.py`** | Converts the transcript CSV into **CogniAffect-style scenarios JSON** (context + responses A/B/C + labels). |
| **`generate_llm_candidate_responses.py`** | Fills response **B** (cognitive) and **C** (affective) using **`prompts.py`** templates and the OpenAI API. Joins scenarios to **`full_dataset_rows.csv`** by `source_row_index` → `index`; builds the model-facing transcript with **`format_context`** so it matches the scenario JSON **`context`** field (Client:/Therapist:). |
| **`outputs/`** | **Generated artifacts** (safe to regenerate; see below). |

---

## Outputs directory (`outputs/`)

| File | Description |
|------|-------------|
| **`transcript_set.csv`** | Final sampled rows: one **unique `dialog_id` per row**; columns match the source export (see [CSV columns](#csv-column-reference)). |
| **`transcript_set_build.log`** | Human-readable **run report**: counts, random seed, per-dialog collapse notes, and **excluded** dialogs with reasons. |
| **`scenarios_transcript_set.json`** | **App-ready** bundle produced from `transcript_set.csv`. |
| **`scenarios_transcript_set_with_llm_candidates.json`** | Same shape as a scenarios file after **`generate_llm_candidate_responses.py`** replaces B/C placeholders with model output. |

Regenerating overwrites these files. Keep a copy elsewhere if you need to freeze a specific version.

---

## End-to-end pipeline

All commands below assume the **repository root** (the directory that contains `dataset_generation/` and `pyproject.toml`). Use **`poetry run python`** after **`poetry install`** at the repo root (dependencies include `openai` for the LLM fill step).

Build the transcript CSV (default input: `full_dataset_rows.csv`), then export scenarios JSON:

```bash
poetry run python dataset_generation/build_transcript_set.py
poetry run python dataset_generation/export_scenarios_from_shortlist.py
```

Produces:

- `dataset_generation/outputs/transcript_set.csv`
- `dataset_generation/outputs/transcript_set_build.log`
- `dataset_generation/outputs/scenarios_transcript_set.json`

Without Poetry, run the same script paths with `python` or `python3`.

### Fill LLM responses B and C (OpenAI)

When you have a scenarios JSON whose B/C fields are still placeholders (for example `outputs/dataset_to_use_4.json`), generate cognitive and affective replies from the prompts in **`prompts.py`** at the repository root:

```bash
poetry install   # once, at repo root (includes openai)
export OPENAI_API_KEY=sk-...   # or add OPENAI_API_KEY to `.env` at the repo root
poetry run python dataset_generation/generate_llm_candidate_responses.py
```

Defaults: reads **`dataset_generation/outputs/scenarios_transcript_set.json`**, joins each scenario to **`dataset_generation/full_dataset_rows.csv`** on **`source_row_index`** (must match column **`index`**), uses model **`gpt-5`**, writes **`dataset_generation/outputs/scenarios_transcript_set_with_llm_candidates.json`**. Override paths with `--input`, `--csv`, and `--output`.

**Skipping already-filled slots:** By default, the script only calls the API for **B** and/or **C** when that field’s text still equals the exact placeholders from export (`[LLM Cognitive empathy — replace with generated response]` / `[LLM Affective empathy — replace with generated response]`). Scenarios where both are already replaced are skipped (no API). Use **`--force`** to regenerate **every** B and C regardless. **`--dry-run`** processes only the **first scenario in file order** (index 0); if that row is already complete, it is skipped.

API errors **fail the run** (no output file update on failure). Requires network access to OpenAI.

#### Custom scenarios file or hand-edited `context`

The defaults above match the **straight pipeline**: export writes `scenarios_transcript_set.json`, and that file’s `context` fields match **`format_context(prior_dialog)`** from the CSV. If you instead keep a scenarios JSON **elsewhere** (for example **`gp5-generated-responses.json`** at the repository root) or you **manually changed** some `context` strings, use explicit paths and consider **`--use-json-context`**:

- **`--input` / `--output`** — Point to your file and a new output path (or a temp file, then replace the original after review).
- **`--use-json-context`** — Fills the model prompt from each scenario’s JSON **`context`** (and infers the last **Client:** turn from that text). Without this flag, the script rebuilds the transcript from the CSV, which can **diverge** from what annotators see if the JSON was edited.
- The CSV is still required: every **`source_row_index`** must exist in **`full_dataset_rows.csv`** (the script uses it for validation and, unless you use `--use-json-context`, for **`prior_dialog`** / **`prior_speaker_turn`**).

Example from the repository root:

```bash
poetry run python dataset_generation/generate_llm_candidate_responses.py \
  --input gp5-generated-responses.json \
  --csv dataset_generation/full_dataset_rows.csv \
  --output gp5-generated-responses_filled.json \
  --use-json-context
```

This is the **same script** as the default command; only paths and **`--use-json-context`** differ when your stimuli file is not the default export or no longer matches the CSV verbatim.

### Using the scenarios in CogniAffect

- The Flask app serves **`scenarios.json`** from the project root by default.
- To use a generated set: **upload** `outputs/scenarios_transcript_set.json`, or **copy** it to **`scenarios.json`** at the project root.
- Run **`generate_llm_candidate_responses.py`** (above) so that placeholder strings for responses **B** and **C** are replaced.

---

## Text sanitization (`text_sanitize.py`)

Before quality checks and in the export step, string fields are passed through **`sanitize_transcript_row`** (or equivalent):

- **`unicodedata.normalize("NFKC", ...)`** — canonical Unicode.
- **`html.unescape`** — decodes `&gt;`, `&amp;`, etc.
- **Mojibake replacements** — common sequences such as `‚Äô` → `'`, `¬†` → space (see source for the full table).
- **Control characters** — removed except newlines/tabs where needed for multiline dialog fields.
- **Whitespace** — single-line fields collapsed to single spaces; multiline dialog fields keep paragraph breaks.

Accented Latin letters (e.g. é, ñ) are **preserved**; this is not ASCII-only stripping.

---

## How `build_transcript_set.py` works

### 1. Collapse to one row per conversation

The source CSV has **multiple rows per `dialog_id`** (sequential listener turns in the same exchange). The script keeps **one row per `dialog_id`**:

- Choose the row with the **maximum `turn`**.
- If several rows tie on `turn`, keep the one that appears **later in the file** (higher row index).

That implements the study design: the **last human listener response** in the transcript is the ground-truth reply to compare against LLM candidates.

### 2. Sanitize, then quality filters

After collapse, each row is **sanitized** (see above). Filters use **sanitized** text and measure context lengths **after** stripping XML-like tags for length checks.

Each collapsed row must pass:

- **`mi_adherent`** treated as adherent (e.g. `1`).
- Minimum **character length** for listener `text` (default **50**).
- Minimum **word count** for listener `text` (default **15** words, whitespace-split).
- Minimum **stripped length** (tags removed) for `prior_dialog` and `prior_speaker_turn`.
- Trivial **closings** (e.g. “Take care.”) when very short.
- Trivial **agreements** (e.g. “I agree.”, “Yeah.”) when the reply has at most **5** words and matches a small blocklist.

### 3. Sensitive content 

By default, the build applies a **conservative** pass aimed at keeping the sampled set appropriate for annotation and IRB review. **Generally sensitive material is excluded** from the response set; this does not replace protocol-level review or content warnings for annotators.

### 4. Stratified random sample

From the eligible pool, the script samples **`--n`** rows (default **64**) with **proportional allocation** between:

- **`counsel_chat`** (professional counseling-style transcripts), and  
- **`RED`** (Reddit-sourced ids).

A fixed RNG **`--seed`** (default **42**) makes the draw **reproducible**. Change the seed to obtain a different random subset of the same size (subject to eligibility).

### 5. CLI reference (`build_transcript_set.py`)

| Argument | Default | Meaning |
|----------|---------|---------|
| `--input` | `full_dataset_rows.csv` (next to this script) | Source CSV path. |
| `--output` | `outputs/transcript_set.csv` | Written shortlist CSV. |
| `--log` | `outputs/transcript_set_build.log` | Build/exclusion log. |
| `--n` | `64` | Number of conversations to sample. |
| `--seed` | `42` | Random seed for stratified sampling. |
| `--no-content-filter` | off | If set, disables the optional sensitive-content exclusion pass. |
| `--min-prior-dialog` | `100` | Min length (after tag strip) for `prior_dialog`. |
| `--min-prior-speaker` | `50` | Min length for `prior_speaker_turn`. |
| `--min-text` | `50` | Min character length for listener `text` (after sanitization). |
| `--min-text-words` | `15` | Min word count for listener `text`. |

If fewer than `--n` rows are eligible after filtering, the script exits with an error (relax `--min-text` / `--min-text-words` or use a larger `--input` pool).

---

## How `export_scenarios_from_shortlist.py` works

Maps each CSV row to one scenario:

- **`context`**: from `prior_dialog`, with `<speaker>` / `<listener>` → **Client:** / **Therapist:** labels and blank lines normalized.
- **`responses`**: **A** = human `text`; **B** and **C** = placeholders for LLM cognitive and affective empathy generations.
- **`ground_truth_labels`**: A = `HUMAN`, B = `LLM_COGNITIVE`, C = `LLM_AFFECTIVE` (for analysis; the UI may shuffle presentation).

### CLI reference

| Argument | Default |
|----------|---------|
| `--input` | `outputs/transcript_set.csv` |
| `--output` | `outputs/scenarios_transcript_set.json` |

---

## Interpreting `transcript_set_build.log`

The log is plain text. Top section:

- **`input:`** / **`output:`** — absolute paths used for that run.
- **`raw rows`** — rows read from the CSV.
- **`unique dialogs (collapsed)`** — after one-row-per-`dialog_id`.
- **`eligible after quality filters`** — after length/mi/trivial-closing rules.
- **`excluded`** — count of dialogs dropped by filters.
- **`sampled n=`** and **`seed=`** — sample size and reproducibility seed.
- **`counsel_chat:`** / **`RED:`** — counts in the final sample (stratification balance).

Then:

- **`=== Collapse (multi-row dialogs) ===`** — dialogs where multiple CSV rows were merged; shows chosen `turn` and file index.
- **`=== Excluded after collapse (reason) ===`** — `dialog_id` and a short reason (e.g. `prior_dialog too short`, `text too few words`, `trivial closing`, `trivial agreement`, sensitive-content exclusions when that pass is enabled).

Use this file to audit **what was removed** and to **reproduce** a run (same `--input`, `--seed`, and filter flags → same `transcript_set.csv`).

---

## CSV column reference

Rows follow the motivational-interviewing style export. Important columns:

| Column | Meaning |
|--------|---------|
| `index` | Original row id in the source export. |
| `dialog_id` | **Conversation id**; must be unique in `transcript_set.csv` after sampling. |
| `turn` | Turn index; **max `turn` per dialog** selects the final listener row. |
| `text` | Human **listener/counselor** reply (ground truth for response A). |
| `target_text` | Same content wrapped in `<target>...</target>`. |
| `prior_speaker_turn` | Last **client** utterance before this listener reply. |
| `prior_dialog` | **Longer context** (speaker + prior listener turns) — primary source for the annotator context. |
| `speaker_and_target_text` / `dialog_and_target_text` | Full-thread variants including the target reply (QA / reconstruction). |
| `final_agreed_label` | MI-style behavior label (e.g. Give Information, Support). |
| `mi_adherent` | Adherence flag (must pass for inclusion). |

---

## JSON structure (`scenarios_transcript_set.json`)

Top level:

- **`annotator_id`** — usually `null` in the file; set per session in the app.
- **`import_timestamp`** — UTC time when the JSON was written.
- **`source_csv`** — path to the CSV used for that export.
- **`scenarios`** — array of scenario objects.

Each scenario includes:

- **`scenario_id`** — `SCENARIO_01` … `SCENARIO_NN` (order matches CSV row order).
- **`source_dialog_id`**, **`source_row_index`**, **`turn`**, **`final_agreed_label`** — traceability to the CSV.
- **`context`** — annotator-facing dialogue text.
- **`responses`** — three items with `response_id` `A` / `B` / `C` and `text`.
- **`ground_truth_labels`** — maps A/B/C to human vs LLM types for scoring.

---

## Ethics and content note

Some sources may still touch on difficult themes. Use your **IRB** and study protocol for inclusion decisions and **content warnings** for annotators. Automated steps here (length, MI adherence, trivial phrasing, and a **broad exclusion of generally sensitive material** from the sampled set) are helpers only and **do not** replace ethics or policy review.

---

## Requirements

- **Python 3.9+**
- **Core pipeline** (`build_transcript_set.py`, `export_scenarios_from_shortlist.py`, `text_sanitize.py`): standard library only.
- **`generate_llm_candidate_responses.py`**: from the repo root run **`poetry install`** (pulls in **`openai`**), set **`OPENAI_API_KEY`**, and keep **`prompts.py`** at the repository root (imported by the script). Invoke with **`poetry run python dataset_generation/generate_llm_candidate_responses.py`**.

If you change file names or paths, pass explicit `--input` / `--output` / `--log` arguments so the scripts stay in sync.
