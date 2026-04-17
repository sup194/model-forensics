# model-forensics

简体中文: [README.zh-CN.md](README.zh-CN.md)
License: MIT

`model-forensics` is a CLI tool for checking whether the models provided by a model provider are fake.

Use it for scenarios like:

- gateway fraud, **bait-and-switch**
- one claimed model actually mixing multiple models behind it
- comparing model behavior across different periods to see whether it is stable or whether the backend switched to another model

## How It Checks

- uses combined test cases for anomaly screening
- builds a local fingerprint database from official models for model matching detection

## Quick Start

### Option A: Without Local Reference

For a quick first pass, you can skip building a local reference and run:

```bash
mforensics inspect examples/targets.yaml
```

### Option B: With Local Reference

If you want further comparison evidence, you can first build a local reference from an official model:

```bash
mforensics profile examples/reference.yaml --save-as gpt-4o-official --db data/model-forensics.sqlite
```

Then inspect the corresponding model:

```bash
mforensics inspect examples/targets.yaml --db data/model-forensics.sqlite --out reports/run-001
```

### Compare Historical Runs

You can also compare results from different periods to see whether a model is stable or whether the backend has changed:

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

The CLI walks upward from the config file directory and automatically loads the nearest `.env` file.
`.env.example`.

Example `.env`:

```bash
REFERENCE_API_KEY=replace-with-reference-api-key
SUSPECT_API_KEY=replace-with-suspect-api-key
OPENAI_API_KEY=replace-with-openai-api-key-for-embeddings
```

## Target Config

Example config for the model to inspect:

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

Example config for an official reference:

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

## Acknowledgements

Special thanks to the [Linux.do](https://linux.do) community for its support and help.
