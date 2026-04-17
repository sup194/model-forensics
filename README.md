# model-forensics

简体中文文档: [README.zh-CN.md](README.zh-CN.md)

`model-forensics` is a CLI for checking whether an LLM provider is actually serving the model it claims to serve.

Use it when:

- a provider claims to serve an official model but may be relaying to something else
- a model gateway may be mixing multiple backends behind one model name
- a suspicious endpoint may be impersonating an official OpenAI- or Anthropic-style API

## What It Checks

The project combines two kinds of evidence:

- anomaly screening for suspicious model-provider behavior
- reference-model matching against a local fingerprint database built from trusted official endpoints

In practice, it looks for signals such as:

- self-identification mismatches
- inconsistent raw API model names
- knowledge cutoff inconsistencies
- refusal and jailbreak behavior patterns
- formatting and reasoning fingerprints
- unusually high similarity across supposedly different targets

## Quick Start

### Option A: Inspect Without Local References

If you want a fast first pass, inspect a suspicious API without building any local reference database:

```bash
mforensics inspect examples/targets.yaml
```

This runs anomaly screening only. It is useful for a quick pass, but weaker than comparing against trusted reference profiles.

### Option B: Inspect With Local References

If you want stronger evidence, first build local reference profiles from official providers you trust:

```bash
mforensics profile examples/reference.yaml --save-as gpt-4o-official --db data/model-forensics.sqlite
```

Then inspect the suspicious endpoint:

```bash
mforensics inspect examples/targets.yaml --db data/model-forensics.sqlite --out reports/run-001
```

The report may include:

- anomaly verdicts for each target
- extracted identity claims
- raw API model names returned by the endpoint
- knowledge cutoff evidence
- behavior fingerprints
- top reference-model matches
- cross-target similarity findings

### Compare Historical Runs

You can compare runs over time to check whether a provider is stable or changing behavior:

```bash
mforensics compare <run-id-a> <run-id-b> --db data/model-forensics.sqlite
```

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

## Target Config

Suspicious provider example:

```yaml
name: suspect-check
targets:
  - name: suspect-openai
    provider: generic
    protocol: openai
    base_url: https://suspicious.example.com/v1
    claimed_model: gpt-4o
    api_key_env: SUSPECT_API_KEY
```

Trusted reference example:

```yaml
name: official-reference
targets:
  - name: trusted-openai
    provider: openai
    protocol: openai
    base_url: https://api.openai.com/v1
    claimed_model: gpt-4o
    api_key_env: OPENAI_API_KEY
```

For OpenAI-compatible targets, `base_url` should stop at `.../v1`.

## Current Scope

- OpenAI-compatible and Anthropic-compatible adapters
- anomaly screening aimed at suspicious model providers
- heuristic and semantic matching against local trusted reference profiles
- local SQLite storage for references and historical runs
- JSON and Markdown reports with prompt-level evidence
