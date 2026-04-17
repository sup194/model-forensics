# model-forensics

English: [README.md](README.md)

`model-forensics` 是一个 CLI，用来检查一个 LLM 提供商实际提供的模型，是否和它声称的一致。

适合这类场景：

- 提供商声称自己接的是某个官方模型，但实际上可能转发到了别的模型
- 一个模型中转站可能在同一个模型名背后混用多个后端
- 一个可疑接口可能在伪装成 OpenAI 或 Anthropic 风格的官方 API

## 它检查什么

这个项目把两类证据结合起来：

- 针对可疑模型提供商行为的异常筛查
- 基于可信官方接口建立的本地指纹库做参考模型匹配

具体会检查这类信号：

- 自报身份是否和声明模型一致
- API 返回的原始模型名是否前后一致
- 知识截止时间是否前后矛盾
- 拒答和 jailbreak 表现模式
- 格式、推理和输出风格指纹
- 多个看似不同 target 之间是否异常相似

## 快速开始

### 方式 A：不使用本地 reference

如果你只是想先快速初筛，可以先不建立本地 reference，直接检查可疑 API：

```bash
mforensics inspect examples/targets.yaml
```

这种方式只会运行异常筛查，适合快速初筛，但会弱于和可信 reference 做对照。

### 方式 B：使用本地 reference

如果你想拿到更强的对照证据，可以先从你信任的官方提供商建立本地 reference：

```bash
mforensics profile examples/reference.yaml --save-as gpt-4o-official --db data/model-forensics.sqlite
```

然后对可疑接口做检查：

```bash
mforensics inspect examples/targets.yaml --db data/model-forensics.sqlite --out reports/run-001
```

报告中可能包含：

- 每个 target 的异常判定结果
- 提取出的自报身份
- 接口实际返回的原始模型名
- 知识截止时间证据
- 行为指纹
- 最接近的参考模型匹配结果
- 多个 target 之间的相似度结论

### 对比历史运行

你还可以对比不同时期的结果，判断一个提供商是否稳定，或者是否发生了后端切换：

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

你可以直接把密钥放在环境变量里，也可以放在本地 `.env` 文件中。

CLI 会从配置文件所在目录开始向上查找，并自动加载最近的 `.env` 文件。
只有真正的本地 `.env` 文件会被 git 忽略。仓库里提供了一个可跟踪的模板文件 `.env.example`。

`.env` 示例：

```bash
REFERENCE_API_KEY=replace-with-reference-api-key
SUSPECT_API_KEY=replace-with-suspect-api-key
OPENAI_API_KEY=replace-with-openai-api-key-for-embeddings
```

## Target 配置

可疑提供商示例：

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

官方 reference 示例：

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

对于 OpenAI 兼容接口，`base_url` 应该以 `.../v1` 结束。

## 当前范围

- OpenAI 兼容和 Anthropic 兼容的适配器
- 面向可疑模型提供商的异常筛查
- 基于本地可信 reference profile 的启发式和语义匹配
- 用于保存 reference 和历史运行结果的本地 SQLite 存储
- 带逐条 prompt 证据的 JSON 和 Markdown 报告输出
