# はじめに (Getting Started) — AO Operator

> 本ドキュメントは英語版の翻訳です。差異がある場合は英語版を正本とします:
> [`../../SETUP.md`](../../SETUP.md)

このページでは、AO Operator をローカル開発機にセットアップし、最初のサンプル SDD を
実体化するまでの最小手順を示します。

## 前提条件 (Prerequisites)

- **OS**: macOS、Ubuntu、または Windows (WSL2 推奨)
- **Python**: 3.10 以上
- **git**
- **任意のプロバイダ**: Codex CLI または Claude Code (provider-free モードで試す場合は
  不要)
- **任意**: AO Runtime のローカルインストール (`--engine ao` で実行する場合)

## インストール (Install)

```bash
git clone https://github.com/uesugitorachiyo/ao-operator.git
cd ao-operator

# 仮想環境を作成 (推奨)
python -m venv .venv
source .venv/bin/activate    # Windows: .venv\Scripts\activate

# 開発用依存関係をインストール
python -m pip install -r requirements-dev.txt
```

詳細なプロバイダ設定 (API キーや CLI バイナリのパス指定など) は
[`../../SETUP.md`](../../SETUP.md) を参照してください。

## 動作確認 (Verify)

スモークテストを実行します:

```bash
python -m pytest -q
```

このコマンドは AO Operator のロール契約、RunSpec 生成、ステータス成果物の整合性を
網羅的に検証します (CI と同じテストです)。

## サンプル SDD を取り込む (Materialize a Sample SDD)

プロバイダ不要モードで、サンプルの SDD を実体化します:

```bash
python scripts/factory_run.py \
    --profile smoke-test \
    --spec examples/ingestible-specs/financial-citation-audit-sdd.md \
    --provider-free
```

成果物は `runs/<run-id>/` 配下に保存されます。詳細は
[`./quickstart.md`](./quickstart.md) を参照してください。

## 次のステップ (Next Steps)

- [`./quickstart.md`](./quickstart.md) — Codex / Claude Code から AO Operator を試す手順
- [`./TRANSLATION.md`](./TRANSLATION.md) — 用語集と翻訳方針
- [`../../SETUP.md`](../../SETUP.md) — 詳細セットアップ (英語)
- [`../../PROMPT_SAMPLES.md`](../../PROMPT_SAMPLES.md) — よく使うプロンプト例 (英語)
- [`../../profiles/README.md`](../../profiles/README.md) — プロファイルスキーマ (英語)
