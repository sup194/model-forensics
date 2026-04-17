# model-forensics

English: README.md

`model-forensics` 是一个 CLI 工具，用来检查模型提供商提供的模型是否造假。

适合这类场景：

- 中转站造假， **挂羊头，卖狗肉**
- 一个模型背后实际混用多种模型
- 对比不同时期的模型表现，判断模型是不是稳定，是不是后端切换成了其他模型

## 怎么检查

- 通过组合测试用例作异常筛查
- 基于官方模型建立本地指纹库做模型匹配检测

## 快速开始

### 方式 A：不使用本地 reference

快速初筛，可以先不建立本地 reference，直接运行：

```bash
mforensics inspect examples/targets.yaml
```

### 方式 B：使用本地 reference

如果你想有进一步的对照证据，可以先从官方模型建立本地 reference：

```bash
mforensics profile examples/reference.yaml --save-as gpt-4o-official --db data/model-forensics.sqlite
```

然后在检测对应的模型：

```bash
mforensics inspect examples/targets.yaml --db data/model-forensics.sqlite --out reports/run-001
```

### 对比历史运行

你还可以对比不同时期的结果，判断一个模型是否稳定，或者是否发生了后端切换：

```bash
mforensics compare <run-id-a> <run-id-b> --db data/model-forensics.sqlite
```

## 命令

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

## 密钥

CLI 会从配置文件所在目录开始向上查找，并自动加载最近的 `.env` 文件。
`.env.example`。

`.env` 示例：

```bash
REFERENCE_API_KEY=replace-with-reference-api-key
SUSPECT_API_KEY=replace-with-suspect-api-key
OPENAI_API_KEY=replace-with-openai-api-key-for-embeddings
```

## Target 配置

待检测模型配置示例：

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

官方 reference 配置示例：

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

## 致谢

特别感谢 [Linux.do](https://linux.do) 社区的支持与帮助。
