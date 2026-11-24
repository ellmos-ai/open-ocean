---
name: open-ocean
version: 0.3.1
updated: 2026-11-24
language: ja
category: infrastructure
description: "ellmos エコシステムの検証可能なローカル構成およびランタイムカーネル（読み取り専用ライブラリ・権限検証、アクティブ構成・GUI ブリッジ、監視付きランタイム・エージェント管理の3モード対応）。"
---

# open-ocean — システムスキルとアクセスモード (JA)

**言語 (World Set 11):** [Deutsch](../SKILL.md) · [English](SKILL.en.md) · [Español](SKILL.es.md) · [Français](SKILL.fr.md) · [Português](SKILL.pt.md) · [Русский](SKILL.ru.md) · [中文](SKILL.zh.md) · **日本語** · [العربية](SKILL.ar.md) · [हिन्दी](SKILL.hi.md) · [বাংলা](SKILL.bn.md)

`open-ocean` は宣言型システム構成、リソース調停、3段階の権限検証（`ocean authority`）、ハッシュ固定システム GUI ブリッジ（`ocean gui`）、および **BACH** などの具現化基盤となる監視付きランタイムを提供します。完全な CLI リファレンス（主要コマンド `16` 個、サブコマンド `16` 個）：[`api/cli-reference.md`](api/cli-reference.md)。

## 3つのアクセスモード

1. **モード A — ライブラリと診断（読み取り専用）:** `ocean_resources.client`, `tools.ocean_inspect`, `tools.governance_bridge`, `tools.help_projection`, `python ocean.py stack-status|authority`
2. **モード B — アクティブ構成・タスク・GUI ブリッジ:** `python ocean.py plan|up|inspect|gui|task` + `tools.gui_bridge` / `tools.gui_server`
3. **モード C — ランタイムスーパーバイザ・エージェント・コンソール:** `python ocean.py start|status|agents|sessions|tasks|chat|console|user|down` + `tools.runtime_supervisor`

## ドキュメント優先順位 (#2459)

1. **最新のユーザー決定**（意思決定記録 / オペレーターの明示承認）
2. **進行中の移行・改修計画**（変換対象スコープ）
3. **モジュールドキュメント**（`ellmos.module.v2` マニフェストの `docs` エントリ）
4. **コアドキュメント**（インストール済みカーネルの `docs/CORE.md` と `SKILL.md`）
