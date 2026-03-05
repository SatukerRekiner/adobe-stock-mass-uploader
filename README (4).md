# interview-shorts-pipeline

<p align="left">
  <img src="https://img.shields.io/badge/python-3.11%2B-3776AB?logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/LLM-Gemini%202.5%20Flash-4285F4?logo=google&logoColor=white" alt="Gemini">
  <img src="https://img.shields.io/badge/image%20processing-Pillow-8C52FF" alt="Pillow">
  <img src="https://img.shields.io/badge/output-Adobe%20Stock%20CSV-success" alt="Adobe Stock CSV">
  <img src="https://img.shields.io/badge/status-portfolio%20project-black" alt="Portfolio Project">
  <a href="https://github.com/<your-username>/<repo-name>/actions/workflows/ci.yml">
    <img src="https://github.com/<your-username>/<repo-name>/actions/workflows/ci.yml/badge.svg" alt="CI">
  </a>
</p>

An AI-assisted metadata pipeline that transforms raw image batches into **Adobe Stock-ready CSV uploads**.  
The project turns a repetitive, manual content-ops workflow into a deterministic, validation-driven, production-style automation pipeline.

---

## Project Overview

Uploading stock assets at scale is rarely blocked by image generation or editing itself — the real bottleneck is metadata:  
**titles, keyword sets, category mapping, formatting, consistency, and upload readiness**.

This project solves that bottleneck by taking a folder of source images, processing them in **fixed-size multimodal batches**, sending them to **Gemini**, and producing a clean `adobe_dane.csv` file that can be imported directly into Adobe Stock.

At a high level, the pipeline:

- scans a local input directory for supported image files,
- groups files into **exact batches of 20 images**,
- resizes images in memory to reduce vision-token cost,
- calls Gemini with a strict JSON contract,
- validates and repairs malformed model outputs,
- normalizes Adobe Stock category values,
- sanitizes titles and keyword lists,
- appends final rows into a CSV with the exact schema needed for downstream upload.

This repo is intentionally small, but it demonstrates the kind of engineering judgment that matters in real systems:

- strong I/O contracts,
- defensive parsing,
- deterministic processing,
- cost-aware LLM usage,
- retry/backoff handling,
- and clean separation between ingestion, inference, validation, and export.

---

## Why this project?

This is not “just a script.” It is a compact example of building a **resilient AI-enriched data pipeline**.

### What problem does it solve?

For stock marketplaces, metadata quality directly affects discoverability and submission throughput. Writing titles and 45–49 keywords per asset by hand is slow, inconsistent, and hard to scale.

This pipeline automates that workflow while still enforcing strict downstream requirements.

### Why is it technically interesting?

Because LLM integrations become impressive only when they are **operationally reliable**. This project goes beyond a naive API call by adding:

- **deterministic batch processing**
- **schema-aware validation**
- **fault-tolerant JSON recovery**
- **repair loops for broken model output**
- **normalization of loosely formatted category data**
- **cost optimization via image downscaling**
- **retry logic for quota/transient failures**
- **CSV contract enforcement for downstream tooling compatibility**

For a hiring manager or senior engineer, this repo signals that I understand how to bridge the gap between a model demo and a **usable pipeline**.

---

## Architecture & Pipeline Flow

> **[Insert Architecture Diagram Here]**

### End-to-end flow

```text
Input Folder (./zdjecia)
        │
        ▼
Image Discovery + Stable File Ordering
        │
        ▼
Exact Batch Chunking (20 images per batch)
        │
        ▼
In-memory Image Preprocessing
(resize / convert RGB / lower token cost)
        │
        ▼
Gemini Multimodal Request
(prompt + 20 images, JSON-only response contract)
        │
        ▼
JSON Parsing + Recovery
(strip fences / salvage first JSON array)
        │
        ▼
Validation Layer
- exactly 20 objects
- indexes 0..19
- title present and sanitized
- 45–49 keywords
- category normalized to Adobe Stock IDs
        │
        ▼
Optional Repair Pass
(text-only correction prompt for malformed outputs)
        │
        ▼
Post-processing
- dedupe keywords
- remove banned phrases/digits
- pad missing keywords safely if needed
- normalize category names/IDs
        │
        ▼
CSV Writer
Filename, Title, Keywords, Category, Releases
        │
        ▼
adobe_dane.csv
```

### Design notes

- The pipeline uses **stable ordering** so each returned object can be mapped back to the correct filename.
- It is intentionally **batch-driven** rather than event-driven because the downstream task is throughput-oriented and constrained by model request economics.
- The validation/repair step is a pragmatic pattern for making LLM output usable in automation pipelines.

---

## Tech Stack & Tools

### Language

- **Python 3.11+**
  - Chosen for rapid iteration, mature file/data tooling, and excellent support for scripting AI workflows.

### AI / Model Integration

- **Google Gemini (`google-generativeai`)**
  - Used for multimodal understanding of image batches and structured metadata generation.
  - Good fit for rapid prototyping of image-to-structured-data pipelines.

### Image Processing

- **Pillow**
  - Used to load, normalize, and downscale images in memory before inference.
  - A deliberate engineering choice to reduce request cost and payload size without mutating source assets on disk.

### Configuration / Runtime

- **python-dotenv**
  - Keeps secrets out of source code and simplifies local developer setup.

### Standard Library

- **argparse** — CLI configurability  
- **csv** — output generation compatible with import workflows  
- **json** — structured response parsing and repair  
- **logging** — operational visibility  
- **pathlib** — filesystem ergonomics  
- **re / unicodedata** — normalization, cleanup, category matching  

---

## Key Features & Technical Achievements

- **Deterministic batch pipeline**
  - Processes images in sorted order and maps model output back by index, avoiding filename/output drift.

- **Strict multimodal response contract**
  - Prompts the model to return **JSON only** with exact fields and batch indexes.

- **Schema-like validation without overengineering**
  - Verifies object count, index continuity, title quality, keyword count, and category correctness before writing anything to disk.

- **LLM output repair loop**
  - If the initial model response violates constraints, the system performs a **cheaper text-only repair pass** rather than resending all images.

- **Robust JSON recovery**
  - Strips markdown fences and attempts to salvage the first JSON array if the model wraps or pollutes output.

- **Category normalization for real-world model variance**
  - Accepts numeric IDs, numeric strings, exact names, case-insensitive names, and even accent-insensitive variants before mapping to Adobe Stock category IDs.

- **Keyword hygiene pipeline**
  - Removes duplicates, banned filler phrases, and digits; enforces the 45–49 keyword constraint; and applies safe fallback enrichment when the model undershoots.

- **Title sanitization**
  - Cleans quotes, whitespace, placeholder ellipses, and invalid punctuation-only titles while respecting length limits.

- **Cost-aware vision preprocessing**
  - Converts images to RGB and resizes them in memory before inference to reduce multimodal token usage.

- **Operational resilience**
  - Retries transient failures and quota-related `429 / RESOURCE_EXHAUSTED` responses with backoff logic.

- **CSV contract enforcement**
  - Ensures the output file has the exact expected header before appending rows, reducing downstream import surprises.

- **Pragmatic CLI design**
  - Supports configurable input/output paths, model selection, batch size, token settings, and image preprocessing controls.

---

## Repository Structure

```text
.
├── opis_csv.py
├── .env
├── zdjecia/
│   ├── image_001.jpg
│   ├── image_002.jpg
│   └── ...
├── adobe_dane.csv
└── docs/
    ├── architecture.png
    ├── examples/
    │   ├── input_01.jpg
    │   ├── input_02.jpg
    │   └── ...
    └── output-preview.png
```

---

## Local Setup & Installation

### Prerequisites

- Python **3.11+**
- A **Google Gemini API key**
- A folder containing input images in one of the supported formats:
  - `.png`
  - `.jpg`
  - `.jpeg`
  - `.webp`

### 1. Clone the repository

```bash
git clone https://github.com/<your-username>/<repo-name>.git
cd <repo-name>
```

### 2. Create and activate a virtual environment

#### macOS / Linux

```bash
python -m venv .venv
source .venv/bin/activate
```

#### Windows (PowerShell)

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

### 3. Install dependencies

```bash
pip install google-generativeai pillow python-dotenv
```

### 4. Configure environment variables

Create a `.env` file in the project root:

```env
GOOGLE_API_KEY=your_gemini_api_key_here
```

> The script can also read `GEMINI_API_KEY`, but `GOOGLE_API_KEY` is the primary option.

### 5. Add your images

Put your source images into the default input folder:

```bash
mkdir -p zdjecia
```

Then copy your files into `./zdjecia`.

### 6. Run the pipeline

```bash
python opis_csv.py
```

### 7. Run with explicit options

```bash
python opis_csv.py \
  --input-dir ./zdjecia \
  --output-csv ./adobe_dane.csv \
  --model gemini-2.5-flash \
  --batch-size 20 \
  --temperature 0.2 \
  --vision-max-side 256 \
  --max-completion-tokens 0
```

### Supported CLI options

```bash
python opis_csv.py --help
```

Expected options include:

- `--input-dir`
- `--output-csv`
- `--model`
- `--batch-size`
- `--temperature`
- `--max-completion-tokens`
- `--vision-max-side`
- `--vision-quality`

---

## Example Workflow

1. Drop images into `./zdjecia`
2. Run the script
3. The pipeline:
   - finds supported files,
   - groups them into exact batches of 20,
   - skips leftovers that do not fill a full batch,
   - calls Gemini,
   - validates and repairs outputs if needed,
   - appends final rows to `adobe_dane.csv`
4. Import `adobe_dane.csv` into Adobe Stock

---

## Example Inputs & Outputs

### Example image gallery

> Replace these placeholders with real examples from your project.

```md
<p align="center">
  <img src="./docs/examples/input_01.jpg" width="24%" />
  <img src="./docs/examples/input_02.jpg" width="24%" />
  <img src="./docs/examples/input_03.jpg" width="24%" />
  <img src="./docs/examples/input_04.jpg" width="24%" />
</p>
```

### Example `adobe_dane.csv` preview

> Once you upload a real example CSV, replace the rows below with the first 3–5 records.

| Filename | Title | Keywords | Category | Releases |
|---|---|---|---:|---|
| example_001.jpg | Modern business team meeting in bright office interior | business, teamwork, office, corporate, strategy, collaboration, meeting, startup, leadership, planning, professional, communication, workplace, company, success, project, manager, employees, laptop, presentation, creative, modern, productivity, brainstorming, organization, marketing, analytics, desk, schedule, discussion, vision, goals, innovation, people, indoor, career, management, conference, planning session, workflow, growth, support, partnership, professional life, team, business concept | 3 |  |
| example_002.jpg | Tropical beach sunset with palm silhouettes and calm ocean | beach, sunset, tropical, ocean, palm trees, coastline, travel, vacation, landscape, paradise, island, nature, summer, sky, water, reflection, scenic, tourism, horizon, tranquil, evening, seascape, destination, outdoors, exotic, relaxation, sunlight, warm, clouds, shoreline, idyllic, serene, getaway, natural beauty, color, peaceful, sand, coastline view, wanderlust, leisure, holiday, environment, scenic view, calm, travel concept | 21 |  |
| example_003.jpg | Close-up healthy salad bowl with fresh vegetables on wooden table | salad, healthy food, vegetables, fresh, nutrition, bowl, meal, diet, organic, lunch, tomato, cucumber, greens, natural, vegetarian, food photography, homemade, colorful, clean eating, ingredient, culinary, kitchen, balanced diet, wellness, delicious, appetizer, restaurant, lifestyle, gourmet, freshness, food concept, herbs, vegan, plate, table, rustic, dining, nutritious, preparation, healthy lifestyle, produce, cooking, eating, plant based, lunch idea | 7 |  |

### Optional: rendered output preview image

You can also add a static preview image showing:

- a few sample inputs,
- a screenshot of the generated CSV,
- and a short annotation of the pipeline flow.

```md
![Output Preview](./docs/output-preview.png)
```

---

## Engineering Tradeoffs

A few design choices here are deliberate:

- **Sequential batch processing over naive parallelism**  
  This keeps quota behavior predictable and simplifies operational debugging. In a production system, I would introduce controlled concurrency behind a rate limiter.

- **CSV as the terminal artifact**  
  This aligns with the downstream ingestion format and keeps the tool easy to integrate into existing content operations workflows.

- **Validation and repair instead of blind trust in model output**  
  LLMs are probabilistic systems; pipelines should not be.

- **In-memory resizing instead of writing transformed files to disk**  
  This reduces token cost while preserving original assets untouched.

---

## Future Enhancements

If I were evolving this into a production-grade system, the next steps would be:

- **Controlled concurrency + rate limiting**
  - Parallelize batch execution safely with a worker pool and provider-aware quota controls.

- **Checkpointing / resumability**
  - Persist job state so long-running imports can resume after failures without reprocessing completed batches.

- **Structured schemas**
  - Introduce `pydantic` or JSON schema validation for even clearer contracts and error reporting.

- **Automated test coverage**
  - Add unit tests for parsing, normalization, validation, and CSV generation.
  - Add golden-file tests for representative model outputs.

- **Observability**
  - Emit structured logs, metrics, and per-batch success/failure counters.
  - Add tracing for model latency and repair-rate monitoring.

- **Multi-provider abstraction**
  - Support multiple model backends behind a common interface for routing, fallback, and experimentation.

- **Human-in-the-loop QA**
  - Add a lightweight review UI for approving or editing generated metadata before export.

- **Preview artifacts in the repo**
  - Add a `docs/examples/` folder with:
    - 4–8 representative input images,
    - a sample `adobe_dane.csv`,
    - a screenshot showing the first rows of the output,
    - and optionally an HTML/Markdown gallery generated from those examples.

- **GitHub Actions**
  - Linting, test execution, type checks, and packaging validation on every push.

---

## What this project signals in an interview

This repository is a strong example of how I build software at the intersection of:

- AI systems,
- data pipelines,
- operational reliability,
- and product-driven automation.

It shows that I can:

- turn ambiguous manual workflows into deterministic pipelines,
- integrate LLMs without treating them as magic,
- design around cost and failure modes,
- and produce tools that are actually usable by downstream operators.

---

## License

Add your preferred license here, for example:

```md
MIT License
```

---

## Contact

If you are reviewing this repository as part of an application, I’m happy to walk through:

- architecture decisions,
- LLM reliability strategies,
- cost/performance tradeoffs,
- and how I would evolve this into a production service.

<!--
README customization checklist:
- Replace <your-username>/<repo-name>
- Add real CI workflow badge if applicable
- Insert architecture diagram
- Add docs/examples input images
- Replace CSV preview rows with real output
- Add license
-->
