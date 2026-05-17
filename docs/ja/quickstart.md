# クイックスタート (Quickstart) — AO Operator

> 本ドキュメントは英語版の翻訳です。差異がある場合は英語版を正本とします:
> [`../../README.md`](../../README.md) の "Paste Into Codex Or Claude Code" 節

このページでは、Codex CLI または Claude Code から AO Operator を試し、サンプル SDD
を実体化してエビデンスを確認するまでの最短手順を示します。

## Codex / Claude Code への貼り付け (Paste Into Codex or Claude Code)

シェルへ直接コマンドを打ち込まないでください。新しいチェックアウトを作れる親
ディレクトリで **Codex CLI** か **Claude Code** を開き、以下のプロンプトをそのまま
貼り付けてください:

```text
ライブのプロバイダトークンを使わずに AO Operator を試す。

ゴール:
- 未取得なら https://github.com/uesugitorachiyo/ao-operator.git を clone する。
- 当該リポジトリへ移動する。
- examples/ingestible-specs/financial-citation-audit-sdd.md を読む。
- プロバイダ不要の取り込みパスで、smoke-test プロファイルとして上記 SDD を実体化する。
- OPENAI_API_KEY と ANTHROPIC_API_KEY は設定しない。
- Python 3 か git が無ければ停止して原因を説明する。

報告内容:
- SDD が要求するワークフロー結果
- AO Operator が証明している公開ウェッジ
- AO Operator が作成したロールグラフ
- 生成された RunSpec のパス
- ステータスディレクトリのパス
```

## サンプル SDD を実体化する (Materialize a Sample SDD)

シェルから直接動かす場合は以下を実行します。Python 3 と `git` が必要です:

```bash
git clone https://github.com/uesugitorachiyo/ao-operator.git
cd ao-operator
python -m pip install -r requirements-dev.txt

python scripts/factory_run.py \
    --profile smoke-test \
    --spec examples/ingestible-specs/financial-citation-audit-sdd.md \
    --provider-free
```

`--provider-free` を指定することで、Codex / Claude API への課金を発生させずに
取り込みパスのみを試せます。

## ロールグラフと RunSpec を確認する

実行が完了すると、AO Operator は以下を生成します:

- `runs/<run-id>/role-graph.json` — 当該 SDD から導出されたロール契約のグラフ
- `runs/<run-id>/runspec.yaml` — AO Runtime が実行する DAG 仕様
- `runs/<run-id>/status/` — 各ロールが残したステータス成果物
- `runs/<run-id>/evidence-pack-<run-id>.tar.zst` — 監査可能なエビデンスアーカイブ

## 評価者のクロージャを確認する (Closer Acceptance)

各ロールが提出するエビデンスが受領可能か否かを判定するのは「クローザー」役割です。
クローザーの判定は `runs/<run-id>/status/closer/` 配下に保存されます。受領拒否の場合は
具体的に欠落しているエビデンスが理由として列挙されるため、原因を辿りやすい設計に
なっています。

## 次のステップ (Next Steps)

- [`./getting-started.md`](./getting-started.md) — セットアップ詳細
- [`./TRANSLATION.md`](./TRANSLATION.md) — 用語集
- [`../../SETUP.md`](../../SETUP.md) — 英語版セットアップ手順
- [`../../PROMPT_SAMPLES.md`](../../PROMPT_SAMPLES.md) — よく使うプロンプト例
- [`../../profiles/README.md`](../../profiles/README.md) — プロファイルスキーマ
