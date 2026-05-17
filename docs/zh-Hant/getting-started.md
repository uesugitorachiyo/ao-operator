# 入門 (Getting Started) — AO Operator

> 本文件為英文版的翻譯。如有差異,以英文版為準:
> [`../../SETUP.md`](../../SETUP.md)

本頁介紹在本機開發機上設定 AO Operator,並實體化首個 SDD 範例的最小步驟。

## 前置條件 (Prerequisites)

- **作業系統**: macOS、Ubuntu 或 Windows (建議 WSL2)
- **Python**: 3.10 以上
- **git**
- **選用 provider**: Codex CLI 或 Claude Code (以 provider-free 模式試用時不需要)
- **選用**: AO Runtime 本機安裝 (使用 `--engine ao` 執行時需要)

## 安裝 (Install)

```bash
git clone https://github.com/uesugitorachiyo/ao-operator.git
cd ao-operator

# 建立虛擬環境 (建議)
python -m venv .venv
source .venv/bin/activate    # Windows: .venv\Scripts\activate

# 安裝開發相依套件
python -m pip install -r requirements-dev.txt
```

詳細的 provider 設定 (API 金鑰與 CLI 二進位路徑等) 請參考
[`../../SETUP.md`](../../SETUP.md)。

## 驗證 (Verify)

執行冒煙測試:

```bash
python -m pytest -q
```

該指令會全面驗證 AO Operator 的角色契約、RunSpec 產生與狀態產物的內部一致性
(與 CI 相同的測試)。

## 匯入範例 SDD (Materialize a Sample SDD)

以 provider-free 模式實體化範例 SDD:

```bash
python scripts/factory_run.py \
    --profile smoke-test \
    --spec examples/ingestible-specs/financial-citation-audit-sdd.md \
    --provider-free
```

產物會儲存在 `runs/<run-id>/` 下。詳情請參考 [`./quickstart.md`](./quickstart.md)。

## 下一步 (Next Steps)

- [`./quickstart.md`](./quickstart.md) — 從 Codex / Claude Code 試用 AO Operator 的步驟
- [`./TRANSLATION.md`](./TRANSLATION.md) — 術語表與翻譯方針
- [`../../SETUP.md`](../../SETUP.md) — 詳細設定 (英文)
- [`../../PROMPT_SAMPLES.md`](../../PROMPT_SAMPLES.md) — 常用提示範例 (英文)
- [`../../profiles/README.md`](../../profiles/README.md) — 設定檔 schema (英文)
