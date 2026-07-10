# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repository is

A **static, data-only registry** of AI providers, models, and capabilities — plus a separate OSINT provider registry — designed for LLM and machine consumption. There is no application code, no build step, no test suite, and no package manager. The "site" is plain static files served via GitHub Pages from the repo root at `https://kbarbel640-del.github.io/ai-provider-registry/` (note the `<base>` tag in `index.html` that anchors all relative links to that URL).

## Commands

- **Lint/validate YAML**: `python3 -c "import yaml,glob; [yaml.safe_load(open(f)) for f in glob.glob('**/*.yaml', recursive=True)]; print('ok')"`
- **Validate JSON**: `python3 -c "import json; json.load(open('registry.json')); json.load(open('osint-providers/osint-registry.json'))"`
- **Regenerate the OSINT tree**: `python3 split_osint_providers.py` — **not runnable in this repo as-is**: it reads source YAML from hardcoded local paths (`/home/ckmaenn/Desktop/PRIV8_DBs/mcp_osint/providers.yaml` and `dork_templates.yaml`) that are not checked in. The committed `osint-providers/` files are its output. Edit the per-file YAMLs directly for corrections; only rerun the script if you have the source files locally.
- **Preview the site locally**: `python3 -m http.server 8000` then open `http://localhost:8000` (the `<base>` tag points to the Pages URL, so relative links work best against the deployed site, not localhost).

## Validating consistency

The registry is hand-maintained and redundant across `registry.json`, `llms.txt`,
and `index.html` (including hardcoded stat counts). Before committing any change to
`providers/`, `models/`, `capabilities/`, `registry.json`, `llms.txt`, or
`index.html`, run:

    python3 validate_registry.py -v   # exit 1 if anything is out of sync

It cross-checks the directories against all three index files, the three stat
counters, and the free-tier badges (`.github/workflows/validate.yml` runs the same
check on every push/PR, so a desynced commit fails CI regardless of who pushed).
Full step-by-step for adding a provider / model family / capability:
`docs/maintenance.md`.

## Architecture

### Four parallel data axes, each a directory of YAML files

- `providers/<id>.yaml` — one file per AI provider (OpenAI, Anthropic, Groq, Kimi, OpenCode Zen, …). Fields: `name`, `api_style`, `auth`, `pricing`, `supports` (capability IDs), `models`, optional `api_spec`, `endpoint`, `rate_limits`. Schema in `docs/provider-schema.md`.
- `models/<family>.yaml` — one file per model *family* (claude, gpt, llama, …). Each lists `variants`, and a variant can be served by a *different* provider than the family's creator (e.g. `models/claude.yaml` lists `claude-opus-4.8` under provider `opencode`). Schema in `docs/model-schema.md`.
- `capabilities/<id>.yaml` — one file per capability (chat, vision, tools, reasoning, …) with a `description` and a JSON `schema`. Schema in `docs/capability-schema.md`. **Note:** the `capabilities` array in `registry.json` is broader than this directory — it includes entries like `video`, `audio`, `realtime` that have no per-file YAML.
- `osint-providers/<category>/<id>.yaml` — separate registry of OSINT/search platforms, organized into category subdirectories (`dns-domain`, `threat-intel`, `code-search`, …) plus `dork-templates/`. Each file carries injected `_category` / `_category_label` fields from the split script.

### Index/entry-point files (hand-maintained — must stay in sync)

Adding or removing a provider/model/capability means updating **multiple** places in lockstep:

- `registry.json` — machine-readable index: `providers` array (id, free, api_style, supports, api_spec, optional endpoint/model_count), `capabilities` array. **Hand-edited**, not generated.
- `llms.txt` — LLM-readable manifest listing every file by section (Providers / Models / Capabilities / Documentation / OSINT). **Hand-edited.**
- `index.html` — human landing page. The stat counts (`16` providers, `10` model families, `14` capabilities) and the provider/model link lists are **hardcoded**, not derived from the data. Update both the counts and the `<ul>` lists when the set changes.
- `docs/api-styles.md` — documents the four `api_style` values (`openai`, `anthropic`, `google`, `cohere`) and their endpoint/auth/streaming conventions. Providers marked `api_style: openai` are OpenAI-SDK drop-in compatible.

### Vendored API specs (`api-specs/`)

Most providers reference their upstream OpenAPI/Discovery spec by URL in `api_spec`. NVIDIA is the exception: `api-specs/nvidia.md` is a hand-authored markdown spec (in German) committed to the repo and referenced as `api_spec: "api-specs/nvidia.md"`. Files here are large vendored snapshots (some multiple MB) — treat as reference data, don't reformat.

### `api_spec` field convention

In `registry.json` and provider YAMLs, `api_spec` is either an absolute HTTPS URL to a remote spec **or** a repo-relative path (e.g. `api-specs/nvidia.md`). Code consuming the registry must handle both forms.

### Distinct "OpenCode" providers

`opencode.yaml` (OpenCode Zen, free tier, `endpoint: https://opencode.ai/zen/v1`) and `opencode-go.yaml` (OpenCode Go, subscription/paid, `endpoint: https://opencode.ai/zen/go/v1`) are two separate provider entries that share the same upstream `api_spec` (`https://opencode.ai/openapi.json`). Model lists are enriched with per-model metadata (context window, pricing, tags) where available — see `kimi.yaml` and `opencode.yaml` for the richest examples of that structure.