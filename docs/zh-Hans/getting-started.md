# 入门 (Getting Started) — AO Operator

> 本文档是英文版的翻译。如有差异,以英文版为准:
> [`../../SETUP.md`](../../SETUP.md)

本页介绍在本地开发机上配置 AO Operator,并实例化首个 SDD 样例的最小步骤。

## 前置条件 (Prerequisites)

- **操作系统**: macOS、Ubuntu 或 Windows (推荐 WSL2)
- **Python**: 3.10 以上
- **git**
- **可选 provider**: Codex CLI 或 Claude Code (使用 provider-free 模式试用时无需)
- **可选**: AO Runtime 本地安装 (使用 `--engine ao` 运行时需要)

## 安装 (Install)

```bash
git clone https://github.com/uesugitorachiyo/ao-operator.git
cd ao-operator

# 创建虚拟环境 (推荐)
python -m venv .venv
source .venv/bin/activate    # Windows: .venv\Scripts\activate

# 安装开发依赖
python -m pip install -r requirements-dev.txt
```

详细的 provider 配置 (API 密钥与 CLI 二进制路径等) 参见
[`../../SETUP.md`](../../SETUP.md)。

## 校验 (Verify)

执行冒烟测试:

```bash
python -m pytest -q
```

该命令全面校验 AO Operator 的角色契约、RunSpec 生成、状态产物的内部一致性
(与 CI 同一套测试)。

## 摄取样例 SDD (Materialize a Sample SDD)

在 provider-free 模式下实例化样例 SDD:

```bash
python scripts/factory_run.py \
    --profile smoke-test \
    --spec examples/ingestible-specs/financial-citation-audit-sdd.md \
    --provider-free
```

产物保存在 `runs/<run-id>/` 下。详细参见 [`./quickstart.md`](./quickstart.md)。

## 下一步 (Next Steps)

- [`./quickstart.md`](./quickstart.md) — 从 Codex / Claude Code 试用 AO Operator 的步骤
- [`./TRANSLATION.md`](./TRANSLATION.md) — 术语表与翻译方针
- [`../../SETUP.md`](../../SETUP.md) — 详细配置 (英文)
- [`../../PROMPT_SAMPLES.md`](../../PROMPT_SAMPLES.md) — 常用提示样本 (英文)
- [`../../profiles/README.md`](../../profiles/README.md) — 配置 schema (英文)
