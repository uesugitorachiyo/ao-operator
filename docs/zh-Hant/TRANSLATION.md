# 翻譯指南與術語表 (Translation Guide & Glossary)

本目錄 (`docs/zh-Hant/`) 是 AO Operator 文件的繁體中文版。原文以英文版為準。

## 翻譯方針 (Translation Policy)

1. **原文為準 (Source of Truth)**.
2. **程式碼與識別字不翻譯**: `RunSpec`、`SDD`、`factory_run`、CLI 選項、檔案路徑等
   保留原文。
3. **正式書面語**.
4. **優先既譯,謹慎新譯**.

## 術語表 (Glossary)

| English | 繁體中文 | 備註 (Notes) |
| --- | --- | --- |
| Operator | 運營層 / Operator | 產品名 (AO Operator) 不翻譯 |
| Role contract | 角色契約 | |
| RunSpec | RunSpec | 不翻譯 |
| SDD | SDD (規格驅動文件) | 首次出現時括註 |
| Evidence pack | 證據包 | 固定譯法 |
| Closer | 結案者 | 角色名 |
| Profile | 設定檔 / Profile | |
| Provider dispatch | 提供方分派 | |
| Smoke test | 冒煙測試 | |
| Status artifact | 狀態產物 | |
| Approval ticket | 審批單 / Approval ticket | |

## 翻譯優先順序 (Translation Priority)

1. `README.md` 開頭 (約 3 段)
2. `SETUP.md`
3. `README.md` 的 "Paste Into Codex Or Claude Code" 章節
4. `docs/contracts/` 下的主要角色契約
5. 其他

## 著手前檢查 (Before You Start)

- 確認原文最新版本
- 若有重要術語未登錄,請加入上表
- 翻譯完成後,刪除 `<!-- TRANSLATION PENDING -->` 標記
