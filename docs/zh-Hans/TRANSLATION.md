# 翻译指南与术语表 (Translation Guide & Glossary)

本目录 (`docs/zh-Hans/`) 是 AO Operator 文档的简体中文版。原文以英文版为准。

## 翻译方针 (Translation Policy)

1. **原文为准 (Source of Truth)**.
2. **代码与标识符不翻译**: `RunSpec`、`SDD`、`factory_run`、CLI 选项、文件路径等
   保留原样。
3. **正式书面语**.
4. **优先既译,谨慎新音译**.

## 术语表 (Glossary)

| English | 简体中文 | 备注 (Notes) |
| --- | --- | --- |
| Operator | 运营层 / Operator | 产品名 (AO Operator) 不翻译 |
| Role contract | 角色契约 | |
| RunSpec | RunSpec | 不翻译 |
| SDD | SDD (规范驱动文档) | 首次出现时括注 |
| Evidence pack | 证据包 | 固定译法 |
| Closer | 结案者 | 角色名 |
| Profile | 配置 (文件) / Profile | |
| Provider dispatch | 提供方分派 | |
| Smoke test | 冒烟测试 | |
| Status artifact | 状态产物 | |
| Approval ticket | 审批单 / Approval ticket | |

## 翻译优先顺序 (Translation Priority)

1. `README.md` 开头 (约 3 段)
2. `SETUP.md`
3. `README.md` 的 "Paste Into Codex Or Claude Code" 章节
4. `docs/contracts/` 下的主要角色契约
5. 其余

## 着手前检查 (Before You Start)

- 确认原文最新版本
- 如有重要术语未登记,添加到上表
- 翻译完成后,删除 `<!-- TRANSLATION PENDING -->` 标记
