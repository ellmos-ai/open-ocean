---
name: open-ocean
version: 0.3.0
updated: 2026-10-31
language: ja
category: infrastructure
description: "ellmos エコシステムの検証可能なローカル構成およびランタイムカーネル（3つのアクセスモード対応）。"
---

# open-ocean — システムスキルとアクセスモード (JA)

`open-ocean` は宣言型システム構成、リソース調停、ガバナンスブリッジ、および監視付きランタイムの基盤を提供します。

## 3つのアクセスモード

1. **モード A — ライブラリ（読み取り専用）:** `ocean_resources.client`, `tools.ocean_inspect`, `tools.governance_bridge`
2. **モード B — アクティブ構成と GUI ブリッジ:** `python ocean.py plan|up|inspect|task` + `tools.gui_bridge`
3. **モード C — ランタイムスーパーバイザ:** `python ocean.py start|status|user|down` + `tools.runtime_supervisor`
