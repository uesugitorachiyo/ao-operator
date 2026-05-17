# AO Operator

[English](../../README.md) | [日本語](../ja/README.md) | **简体中文** | [繁體中文](../zh-Hant/README.md) | [한국어](../ko/README.md)

> AO 是 **AI Orchestration Operation (AI 编排运营)** 的缩写。
> 产品名: **AO Operator**。GitHub 仓库 slug: `ao-operator`。

> 本文档是英文版的翻译。如有差异,以英文版为准:
> [`../../README.md`](../../README.md)

![AO Operator 自主代理 CLI](../../images/ao-operator-agent-team.svg)

**AO Operator 是 AI 编排运营层: 用自然语言描述目标,它就会驱动 Codex 或 Claude Code,
推进到一个经过校验的交付物。** 您提供产品请求、SDD 或任务概要,AO Operator 把它转换
为有作用域的角色、跨平台检查、RunSpec、状态产物以及可审阅的证据。

如果您希望"让 AI CLI 把工作做到完成,而不是留下一堆需要看护的聊天记录",请从这里
开始。AO Operator 面向以结果为导向的工作: 从工程规范生成应用样本、持续改进仓库、
在 macOS / Ubuntu / Windows 上验证行为、在结案者接受运行结果之前要求每个角色提交证据。

AO Operator 同时是更广阔的 AO 适配器面的产品层。OpenClaw 负责工作的投入、调度、观测;
Hermes 风格队列驱动 worker 饱和运行;AO Runtime 在底层负责提供方分派、策略、事件、证据。
AO Operator 为这些插件 / 适配器流提供统一的角色契约,避免每个集成各自发明工作流语义。

## 粘贴到 Codex / Claude Code (Paste Into Codex Or Claude Code)

不要直接把 shell 命令贴入终端。从您日常使用的 AI CLI 开始。在可以创建新检出的父目录
中打开 **Codex CLI** 或 **Claude Code**,然后粘贴以下提示:

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

(更多原文内容请参考 [`../../README.md`](../../README.md))

## 概述 (Overview)

AO Operator 接收 SDD (规范驱动文档) 或自然语言任务概要,基于**角色契约 (role contracts)**
让 Codex / Claude Code 等多个代理协同工作,生成经过校验的产物 (代码、文档、证据包)。
产品的核心是以下三点:

1. **角色契约**: 定义每个代理"应该输出什么",评估者基于该契约判定是否受理。
2. **RunSpec**: 把工作表达为可执行 DAG,在 AO Runtime 上可复现地运行。
3. **证据包**: 把执行历史、产物、签名固化为一个可审计的归档。

## 快速开始 (Quickstart)

详细步骤参见 [`./quickstart.md`](./quickstart.md)。安装参见
[`./getting-started.md`](./getting-started.md)。

## 许可证 (License)

AO Operator 采用以下任一许可证,由使用者择一选用:

- [Apache License, Version 2.0](../../LICENSE-APACHE)
- [MIT License](../../LICENSE-MIT)

详见 [`NOTICE`](../../NOTICE)。

除非您明确声明,否则您有意向本项目提交的贡献,按 Apache-2.0 许可证的定义,均以上述
双许可证形式提供,不附加其他条款或条件。

## 关于翻译 (About This Translation)

本简体中文版本是逐步添加的。术语表与翻译方针参见 [`./TRANSLATION.md`](./TRANSLATION.md)。
如与原文 (英文) 存在差异,以英文版为准。
