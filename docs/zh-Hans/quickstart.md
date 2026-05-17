# 快速开始 (Quickstart) — AO Operator

> 本文档是英文版的翻译。如有差异,以英文版为准:
> [`../../README.md`](../../README.md) 的 "Paste Into Codex Or Claude Code" 章节

本页介绍从 Codex CLI 或 Claude Code 试用 AO Operator,实例化样例 SDD 并确认证据的最短
路径。

## 粘贴到 Codex / Claude Code (Paste Into Codex or Claude Code)

不要直接把命令贴入 shell。在可以创建新检出的父目录中打开 **Codex CLI** 或
**Claude Code**,直接粘贴下列提示:

```text
不使用实时 provider token 来试用 AO Operator。

目标:
- 若尚未存在,则 clone https://github.com/uesugitorachiyo/ao-operator.git。
- 进入仓库。
- 阅读 examples/ingestible-specs/financial-citation-audit-sdd.md。
- 使用无 provider 的摄取路径,以 smoke-test 配置实例化该 SDD。
- 不要设置 OPENAI_API_KEY 与 ANTHROPIC_API_KEY。
- 若缺少 Python 3 或 git, 停止并说明原因。

汇报内容:
- SDD 请求的工作流结果
- AO Operator 证明的公开切入点
- AO Operator 创建的角色图
- 生成的 RunSpec 路径
- 状态目录路径
```

## 实例化样例 SDD (Materialize a Sample SDD)

从 shell 直接运行时,需要 Python 3 与 `git`:

```bash
git clone https://github.com/uesugitorachiyo/ao-operator.git
cd ao-operator
python -m pip install -r requirements-dev.txt

python scripts/factory_run.py \
    --profile smoke-test \
    --spec examples/ingestible-specs/financial-citation-audit-sdd.md \
    --provider-free
```

指定 `--provider-free` 后,无需对 Codex / Claude API 产生费用,即可试用摄取路径。

## 查看角色图与 RunSpec

运行完成后,AO Operator 生成下列产物:

- `runs/<run-id>/role-graph.json` — 该 SDD 推导出的角色契约图
- `runs/<run-id>/runspec.yaml` — AO Runtime 实际执行的 DAG 规约
- `runs/<run-id>/status/` — 各角色提交的状态产物
- `runs/<run-id>/evidence-pack-<run-id>.tar.zst` — 可审计的证据归档

## 结案者接受 (Closer Acceptance)

判断各角色提交的证据是否可受理的角色是「结案者 (Closer)」。结案者的判定保存在
`runs/<run-id>/status/closer/` 下。若被拒绝,具体缺失的证据会作为原因列出,便于追溯。

## 下一步 (Next Steps)

- [`./getting-started.md`](./getting-started.md) — 详细配置
- [`./TRANSLATION.md`](./TRANSLATION.md) — 术语表
- [`../../SETUP.md`](../../SETUP.md) — 英文版配置步骤
- [`../../PROMPT_SAMPLES.md`](../../PROMPT_SAMPLES.md) — 常用提示样本
- [`../../profiles/README.md`](../../profiles/README.md) — 配置 schema
