# AO Operator

[English](../../README.md) | [日本語](../ja/README.md) | [简体中文](../zh-Hans/README.md) | **繁體中文** | [한국어](../ko/README.md)

> AO 是 **AI Orchestration Operation (AI 編排運營)** 的縮寫。
> 產品名: **AO Operator**。GitHub 倉庫 slug: `ao-operator`。

> 本文件為英文版的翻譯。如有差異,以英文版為準:
> [`../../README.md`](../../README.md)

![AO Operator 自主代理人 CLI](../../images/ao-operator-agent-team.svg)

**AO Operator 是 AI 編排運營層: 以自然語言描述目標,它便驅動 Codex 或 Claude Code,
將工作推進到一個經過驗證的交付物。** 您提供產品請求、SDD 或任務概要,AO Operator
會將之轉換為具範疇的角色、跨平台檢查、RunSpec、狀態產物以及可審閱的證據。

如果您希望「讓 AI CLI 把工作做到完成,而不是留下一堆需要看護的聊天記錄」,請從這裡
開始。AO Operator 面向以成果為導向的工作: 從工程規格產生應用程式樣本、持續改善
倉庫、在 macOS / Ubuntu / Windows 上驗證行為、在結案者受理執行結果之前要求每個角色
提交證據。

AO Operator 同時是更廣闊的 AO 介接器面的產品層。OpenClaw 負責工作的投入、排程、觀測;
Hermes 風格佇列驅動 worker 飽和執行;AO Runtime 在底層負責提供方分派、策略、事件、
證據。AO Operator 為這些外掛 / 介接器流提供統一的角色契約,避免每個整合自行發明工作流
語意。

## 貼上至 Codex / Claude Code (Paste Into Codex Or Claude Code)

不要直接把 shell 指令貼入終端機。從您日常使用的 AI CLI 開始。在可以建立新檢出的父
目錄中開啟 **Codex CLI** 或 **Claude Code**,然後貼上以下提示:

```text
不使用即時 provider token 來試用 AO Operator。

目標:
- 若尚未存在,則 clone https://github.com/uesugitorachiyo/ao-operator.git。
- 進入倉庫。
- 閱讀 examples/ingestible-specs/financial-citation-audit-sdd.md。
- 使用無 provider 的匯入路徑,以 smoke-test 設定檔實體化該 SDD。
- 不要設定 OPENAI_API_KEY 與 ANTHROPIC_API_KEY。
- 若缺少 Python 3 或 git,停止並說明原因。

回報內容:
- SDD 要求的工作流結果
- AO Operator 證明的公開切入點
- AO Operator 建立的角色圖
- 產生的 RunSpec 路徑
- 狀態目錄路徑
```

(更多原文內容請參考 [`../../README.md`](../../README.md))

## 概述 (Overview)

AO Operator 接收 SDD (規格驅動文件) 或自然語言任務概要,基於 **角色契約 (role contracts)**
讓 Codex / Claude Code 等多個代理人協同運作,產出經過驗證的產物 (程式碼、文件、證據包)。
產品的核心是以下三點:

1. **角色契約**: 定義每個代理人「應該輸出什麼」,評估者依此判定是否受理。
2. **RunSpec**: 將工作表述為可執行 DAG,在 AO Runtime 上可重現地執行。
3. **證據包**: 將執行歷程、產物、簽章固化為一個可稽核的封存。

## 快速開始 (Quickstart)

詳細步驟請參考 [`./quickstart.md`](./quickstart.md)。安裝請參考
[`./getting-started.md`](./getting-started.md)。

## 授權 (License)

AO Operator 在下列任一授權下提供,由使用者擇一選用:

- [Apache License, Version 2.0](../../LICENSE-APACHE)
- [MIT License](../../LICENSE-MIT)

詳見 [`NOTICE`](../../NOTICE)。

除非您明確聲明,否則您有意向本專案提交的貢獻,依 Apache-2.0 授權的定義,均以上述
雙重授權形式提供,不附加其他條款或條件。

## 關於翻譯 (About This Translation)

本繁體中文版本是逐步加入的。術語表與翻譯方針請參考 [`./TRANSLATION.md`](./TRANSLATION.md)。
如與原文 (英文) 存在差異,以英文版為準。
