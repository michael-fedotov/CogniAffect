# Dataset generation (BWS transcript set)

This folder builds the **annotator stimuli** for the CogniAffect Best–Worst Scaling (BWS) study: a fixed set of therapeutic dialogues where each item has **one human listener reply** (ground truth) and **two LLM-generated alternatives** (cognitive vs affective empathy prompts), aligned with the project methodology (multi-turn context, MI-adherent rows where applicable).

The parent app loads a **scenarios JSON** file; scripts here turn raw CSV exports into **`outputs/transcript_set.csv`** and **`outputs/scenarios_transcript_set.json`**.

---

## What this folder contains

| Path | Role |
|------|------|
| **`all_rows.csv`** | Main **source pool**: many rows per conversation; includes `counsel_chat` and Reddit (`RED`) dialogs. Used as the default input to `build_transcript_set.py`. |
| **`shortlist_theraputic.csv`** | Smaller subset of the same schema (useful for quick tests or debugging the pipeline without reprocessing the full pool). |
| **`build_transcript_set.py`** | Selects **one row per conversation** (final listener turn), applies quality filters, **stratified** random sample to **N** dialogs (default 64), writes CSV + build log. |
| **`export_scenarios_from_shortlist.py`** | Converts the transcript CSV into **CogniAffect-style scenarios JSON** (context + responses A/B/C + labels). |
| **`outputs/`** | **Generated artifacts** (safe to regenerate; see below). |

---

## Outputs directory (`outputs/`)

| File | Description |
|------|-------------|
| **`transcript_set.csv`** | Final sampled rows: one **unique `dialog_id` per row**; columns match the source export (see [CSV columns](#csv-column-reference)). |
| **`transcript_set_build.log`** | Human-readable **run report**: counts, random seed, per-dialog collapse notes, and **excluded** dialogs with reasons. |
| **`scenarios_transcript_set.json`** | **App-ready** bundle: `scenarios` array, each with `context`, three `responses`, and `ground_truth_labels` (A = human, B/C = LLM placeholders until you fill them). |

Regenerating overwrites these files. Keep a copy elsewhere if you need to freeze a specific version.

---

## End-to-end pipeline

From the **repository root** (or `cd dataset_generation` and run the same commands without the `dataset_generation/` prefix):

```bash
python dataset_generation/build_transcript_set.py
python dataset_generation/export_scenarios_from_shortlist.py
```

Typical order:

1. **`build_transcript_set.py`** reads `all_rows.csv` (by default), writes `outputs/transcript_set.csv` and `outputs/transcript_set_build.log`.
2. **`export_scenarios_from_shortlist.py`** reads `outputs/transcript_set.csv`, writes `outputs/scenarios_transcript_set.json`.

### Using the scenarios in CogniAffect

- The Flask app serves **`scenarios.json`** from the project root by default.
- To use this generated set: **upload** `outputs/scenarios_transcript_set.json` in the annotator UI, or **copy/rename** it to `scenarios.json` at the project root for the default load.
- Replace the placeholder strings for responses **B** and **C** with your LLM outputs before running a real study (placeholders are marked in JSON).

---

## How `build_transcript_set.py` works

### 1. Collapse to one row per conversation

The source CSV has **multiple rows per `dialog_id`** (sequential listener turns in the same exchange). The script keeps **one row per `dialog_id`**:

- Choose the row with the **maximum `turn`**.
- If several rows tie on `turn`, keep the one that appears **later in the file** (higher row index).

That implements the study design: the **last human listener response** in the transcript is the ground-truth reply to compare against LLM candidates.

### 2. Quality filters

Each collapsed row must pass:

- **`mi_adherent`** treated as adherent (e.g. `1`).
- Minimum **stripped length** (tags removed for measurement) for:
  - `prior_dialog`
  - `prior_speaker_turn`
  - listener `text`
- Trivial **closings** (e.g. very short “Take care.”) are dropped.

### 3. Stratified random sample

From the eligible pool, the script samples **`--n`** rows (default **64**) with **proportional allocation** between:

- **`counsel_chat`** (professional counseling-style transcripts), and  
- **`RED`** (Reddit-sourced ids).

A fixed RNG **`--seed`** (default **42**) makes the draw **reproducible**. Change the seed to obtain a different random subset of the same size (subject to eligibility).

### 4. CLI reference (`build_transcript_set.py`)

| Argument | Default | Meaning |
|----------|---------|---------|
| `--input` | `all_rows.csv` (next to this script) | Source CSV path. |
| `--output` | `outputs/transcript_set.csv` | Written shortlist CSV. |
| `--log` | `outputs/transcript_set_build.log` | Build/exclusion log. |
| `--n` | `64` | Number of conversations to sample. |
| `--seed` | `42` | Random seed for stratified sampling. |
| `--min-prior-dialog` | `100` | Min length (after tag strip) for `prior_dialog`. |
| `--min-prior-speaker` | `50` | Min length for `prior_speaker_turn`. |
| `--min-text` | `25` | Min length for listener `text`. |

If fewer than `--n` rows are eligible after filtering, the script exits with an error (relax thresholds or use a larger `--input` pool).

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
- **`=== Excluded after collapse (reason) ===`** — `dialog_id` and a short reason (e.g. `prior_dialog too short`, `trivial closing`).

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

Some Reddit-sourced threads may touch on **suicide, self-harm, abuse, or severe distress**. Use your **IRB** and study protocol to decide inclusion, and to give annotators appropriate content warnings. This pipeline does **not** replace policy review; it only filters on length, MI-adherence, and trivial closings.

---

## Requirements

- **Python 3.9+** with the standard library only (no extra packages for these scripts).

If you change file names or paths, pass explicit `--input` / `--output` / `--log` arguments so the two scripts stay in sync.
