# Image Bench

<p align="center">
  <a href="https://www.apache.org/licenses/LICENSE-2.0"><img src="https://img.shields.io/badge/License-Apache_2.0-blue" alt="License"></a>
</p>

An evaluation toolkit for text-to-image generation models. It runs a judge model over generated images and aggregates scores across 5 top-level dimensions:

- Quality
- Aesthetics
- Alignment
- Real-world Fidelity
- Creative Generation

The scoring hierarchy covers 23 sub-dimensions and 56 fine-grained facets. Per-row outputs preserve the raw judge responses, and the toolkit also produces aggregated benchmark summaries in JSON and Excel.

## Quick Start

```bash
# 1. Clone the repo
git clone <your-repo-url> image-bench
cd image-bench

# 2. Create an environment
uv venv .venv --python 3.11
source .venv/bin/activate

# 3. Install Python dependencies
uv pip install -r requirements.txt

# 4. Set your OpenRouter API key
export OPENROUTER_API_KEY=<your-openrouter-api-key>

# 5. Run the judge on your images
python3 judge.py \
  --input your_data.jsonl
```

## Input Format

Your input file can be CSV, JSON, or JSONL and must include these columns:

| Column | Type | Description |
|--------|------|-------------|
| `ID` | int | Prompt identifier that matches [metadata/bench_metadata.json](metadata/bench_metadata.json) |
| `prompt` | str | The text prompt used to generate the image |
| `image_path` | str | Path to the generated image file |

Additional columns are preserved in the judged output.

## Installation

```bash
uv venv .venv --python 3.11
source .venv/bin/activate
uv pip install -r requirements.txt
```

Then provide an OpenRouter API key:

```bash
export OPENROUTER_API_KEY=<your-openrouter-api-key>
```

## Usage

### Judge New Images

```bash
python3 judge.py \
  --input your_data.jsonl
```

Optional metadata sources:

- `--local-metadata metadata/bench_metadata.json`
- `--hf-bench-repo your-dataset-repo --hf-filename image_bench_responses.jsonl`

OpenRouter model notes:

- The default model slug is `openai/gpt-5.5`.

#### CLI Options

| Argument | Default | Description |
|----------|---------|-------------|
| `--input` | required | Input CSV/JSON/JSONL with `ID`, `prompt`, `image_path` |
| `--model` | `openai/gpt-5.5` | OpenRouter model slug |
| `--openrouter-api-key` | `OPENROUTER_API_KEY` | OpenRouter API key |
| `--openrouter-base-url` | `https://openrouter.ai/api/v1` | OpenRouter base URL |
| `--openrouter-site-url` | — | Optional `HTTP-Referer` header |
| `--openrouter-site-title` | `Image Bench` | Optional `X-OpenRouter-Title` header |
| `--hf-bench-repo` | — | Dataset repo used to fetch metadata |
| `--hf-filename` | `image_bench_responses.jsonl` | Filename inside `--hf-bench-repo` |
| `--local-metadata` | — | Local metadata file path |
| `--max-batch-size` | `24` | Maximum number of concurrent OpenRouter requests |
| `--max-new-tokens` | `4096` | Max generation tokens |
| `--request-timeout` | `120` | Per-request timeout in seconds |

#### Output Files

After running `judge.py`, files are written next to the input:

| File | Contents |
|------|----------|
| `<input>_judged.csv` | Per-row results for CSV input |
| `<input>_judged.json` | Per-row results as a JSON array for JSON input |
| `<input>_judged.jsonl` | Per-row results as JSON lines for JSONL input |
| `<input>_bench_scores.json` | Aggregated Level-1, Level-2, and total scores |
| `<input>_bench_scores.xlsx` | Same aggregated scores in Excel |

Per-row result rows include:

- all original input fields
- `judge_model_output`
- `quality_judge_output`
- `aesthetics_judge_output`
- `alignment_judge_output`
- `real_world_fidelity_judge_output`
- `creative_generation_judge_output`

### Compute Scores from Existing Judge Responses

```bash
# From a local JSONL file
python3 compute_scores.py --input image_bench_responses.jsonl

# Or download from a dataset repo
python3 compute_scores.py \
  --hf-repo your-dataset-repo \
  --hf-filename image_bench_responses.jsonl
```

Outputs:

- `scores_result.xlsx`
- `scores_detail.json`
- `scores_result_en.xlsx` and `scores_detail_en.json` when `_en` response columns exist

## Inference Parameters

The judge backend uses fixed inference parameters for reproducibility:

| Parameter | Value |
|-----------|-------|
| `temperature` | `0` |
| `top_p` | `1.0` |
| `max_new_tokens` | `4096` |
| `max_concurrent_requests` | `24` |
| `request_timeout` | `120s` |

## Project Structure

```text
.
├── judge.py
├── compute_scores.py
├── score_utils.py
├── checklists.py
├── backends/
│   └── openrouter_backend.py
├── metadata/
│   └── bench_metadata.json
├── requirements.txt
└── assets/
```

## Evaluation Framework

The benchmark uses a 3-level scoring hierarchy:

| Level-1 Dimension | Level-2 Sub-dimensions |
|-------------------|------------------------|
| Quality | Realism, Detail, Resolution |
| Aesthetics | Composition, Color Harmony, Lighting, Anatomical Portraiture, Emotional Expression, Style Control |
| Alignment | Attributes, Actions, Layout, Relations, Scene |
| Real-world Fidelity | Fairness, Safety & Compliance, World Knowledge |
| Creative Generation | Imagination, Feature Matching, Logical Resolution, Text Rendering, Design Applications, Visual Storytelling |

Scoring rules:

- `0` = Fail -> `0`
- `1` = Pass -> `60`
- `2` = Excel -> `100`
- `N/A` = excluded from aggregation

Scores aggregate bottom-up from Level-3 to Level-2 to Level-1 and then to the overall benchmark score.

## License

This project is licensed under the [Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0).
