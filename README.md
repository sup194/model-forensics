# model-forensics

`model-forensics` is a CLI for two related jobs:

- anomaly screening for suspicious LLM APIs
- reference-model matching against a local fingerprint database

## Commands

```bash
mforensics inspect examples/targets.yaml
mforensics inspect examples/targets.yaml --db data/model-forensics.sqlite --out reports/run-001
mforensics profile examples/reference.yaml --save-as trusted-model-v1 --db data/model-forensics.sqlite
mforensics runs list --db data/model-forensics.sqlite
mforensics runs show <run-id> --db data/model-forensics.sqlite
mforensics compare <run-id-a> <run-id-b> --db data/model-forensics.sqlite
mforensics refs list --db data/model-forensics.sqlite
mforensics refs show trusted-model-v1 --db data/model-forensics.sqlite
mforensics refs delete trusted-model-v1 --db data/model-forensics.sqlite
```

## Secrets

You can keep secrets in environment variables directly, or in a local `.env` file.

The CLI auto-loads the nearest `.env` file it finds by walking upward from the config file directory.
Only real local `.env` files are ignored by git. A tracked template is available as `.env.example`.

Example `.env`:

```bash
REFERENCE_API_KEY=replace-with-reference-api-key
SUSPECT_API_KEY=replace-with-suspect-api-key
OPENAI_API_KEY=replace-with-openai-api-key-for-embeddings
```

## Usage Modes

### Inspect Without References

You can inspect a suspicious API without building any local reference database first:

```bash
mforensics inspect examples/targets.yaml
```

This runs anomaly screening only. The report still includes:

- identity claims
- knowledge cutoff inconsistencies
- anomaly verdict
- behavior fingerprint
- cross-target similarity when multiple targets are present

Reference matching is optional. If no reference profiles exist, the inspect report will say so explicitly.

### Inspect With References

If you have already profiled trusted models, `inspect` will also run candidate matching:

```bash
mforensics inspect examples/targets.yaml --db data/model-forensics.sqlite --out reports/run-001
```

### Compare Historical Runs

You can compare two stored runs later:

```bash
mforensics compare <run-id-a> <run-id-b> --db data/model-forensics.sqlite
```

## Target Config

```yaml
name: suspect-check
targets:
  - name: suspect-openai
    provider: generic
    protocol: openai
    base_url: https://suspicious.example.com/v1
    claimed_model: claimed-model-v1
    api_key_env: SUSPECT_API_KEY
```

For OpenAI-compatible targets, `base_url` should stop at `.../v1`.

## Scope

The current MVP includes:

- OpenAI-compatible and Anthropic-compatible adapters
- anomaly screening for suspicious model APIs
- heuristic and semantic matching against local reference profiles
- local SQLite storage for references and historical runs
- JSON and Markdown reports
