# 翻訳ガイドと用語集 (Translation Guide & Glossary)

このディレクトリ (`docs/ja/`) は AO Operator ドキュメントの日本語版プレースホルダです。
原文の正本は常に英語です。翻訳は段階的に追加してください。

## 翻訳方針 (Translation Policy)

1. **原文を正とする (Source of Truth)**: 英語ドキュメントが変更された場合、日本語版は
   遅れて追従します。差異が見つかった場合は英語を信頼してください。
2. **コードと識別子は訳さない (Do Not Translate Code/Identifiers)**:
   `RunSpec`, `SDD`, `factory_run`, CLI フラグ, ファイルパスなどはそのまま。
3. **「ですます」体で統一 (Polite Form)**.
4. **片仮名語より既訳語を優先 (Prefer Established Translations)**.

## 用語集 (Glossary)

| English | 日本語 | 備考 (Notes) |
| --- | --- | --- |
| Operator | オペレーター | 製品名 (AO Operator) はそのまま |
| Role contract | ロールコントラクト | |
| RunSpec | RunSpec | 訳さない |
| SDD | SDD (仕様駆動文書) | 初出のみ括弧で補足 |
| Evidence pack | エビデンスパック | 訳語固定 |
| Closer | クローザー | 役割名 |
| Profile | プロファイル | |
| Provider dispatch | プロバイダ振り分け | |
| Smoke test | スモークテスト | |
| Status artifact | ステータス成果物 | |
| Approval ticket | 承認チケット | |

## 翻訳優先順位 (Translation Priority)

1. `README.md` 冒頭 (3 段落程度)
2. `SETUP.md`
3. `README.md` の "Paste Into Codex Or Claude Code" 節
4. `docs/contracts/` 配下の主要ロール契約
5. その他

## 着手前チェック (Before You Start)

- 原文の最新版を確認する
- 用語集に未登録の重要語があれば追加する
- 訳出後は `<!-- TRANSLATION PENDING -->` マーカーを削除する
