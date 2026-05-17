# 快速開始 (Quickstart) — AO Operator

> 本文件為英文版的翻譯。如有差異,以英文版為準:
> [`../../README.md`](../../README.md) 的 "Paste Into Codex Or Claude Code" 章節

本頁介紹從 Codex CLI 或 Claude Code 試用 AO Operator,實體化範例 SDD 並確認證據的
最短路徑。

## 貼上至 Codex / Claude Code (Paste Into Codex or Claude Code)

不要直接把指令貼入 shell。在可以建立新檢出的父目錄中開啟 **Codex CLI** 或
**Claude Code**,直接貼上以下提示:

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

## 實體化範例 SDD (Materialize a Sample SDD)

直接從 shell 執行時,需要 Python 3 與 `git`:

```bash
git clone https://github.com/uesugitorachiyo/ao-operator.git
cd ao-operator
python -m pip install -r requirements-dev.txt

python scripts/factory_run.py \
    --profile smoke-test \
    --spec examples/ingestible-specs/financial-citation-audit-sdd.md \
    --provider-free
```

指定 `--provider-free` 後,無需對 Codex / Claude API 產生費用,即可試用匯入路徑。

## 檢視角色圖與 RunSpec

執行完成後,AO Operator 會產生以下產物:

- `runs/<run-id>/role-graph.json` — 從該 SDD 推導出的角色契約圖
- `runs/<run-id>/runspec.yaml` — AO Runtime 實際執行的 DAG 規格
- `runs/<run-id>/status/` — 各角色提交的狀態產物
- `runs/<run-id>/evidence-pack-<run-id>.tar.zst` — 可稽核的證據封存

## 結案者受理 (Closer Acceptance)

判定各角色提交的證據是否可受理的角色是「結案者 (Closer)」。結案者的判定儲存在
`runs/<run-id>/status/closer/` 下。若被拒絕,具體缺失的證據會作為原因列出,便於追溯。

## 下一步 (Next Steps)

- [`./getting-started.md`](./getting-started.md) — 詳細設定
- [`./TRANSLATION.md`](./TRANSLATION.md) — 術語表
- [`../../SETUP.md`](../../SETUP.md) — 英文版設定步驟
- [`../../PROMPT_SAMPLES.md`](../../PROMPT_SAMPLES.md) — 常用提示範例
- [`../../profiles/README.md`](../../profiles/README.md) — 設定檔 schema
