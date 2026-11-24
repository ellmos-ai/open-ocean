---
name: open-ocean
version: 0.3.1
updated: 2026-11-24
language: bn
category: infrastructure
description: "ellmos ইকোসিস্টেমের স্থানীয়, যাচাইযোগ্য কম্পোজিশন ও রানটাইম কার্নেল, যাতে তিনটি অ্যাক্সেস মোড রয়েছে (রিড-অনলি লাইব্রেরি ও অথরিটি যাচাই, সক্রিয় কম্পোজিশন ও GUI ব্রিজ, এবং তত্ত্বাবধানকৃত রানটাইম ও এজেন্ট সার্ভিস)।"
---

# open-ocean — সিস্টেম স্কিল ও অ্যাক্সেস মোড (BN)

**ভাষাসমূহ (World Set 11):** [Deutsch](../SKILL.md) · [English](SKILL.en.md) · [Español](SKILL.es.md) · [Français](SKILL.fr.md) · [Português](SKILL.pt.md) · [Русский](SKILL.ru.md) · [中文](SKILL.zh.md) · [日本語](SKILL.ja.md) · [العربية](SKILL.ar.md) · [हिन्दी](SKILL.hi.md) · **বাংলা**

`open-ocean` ঘোষণামূলক সিস্টেম কম্পোজিশন, রিসোর্স সমন্বয়, তিন-স্তরের অথরিটি যাচাই (`ocean authority`), হ্যাশ-পিন করা সিস্টেম GUI ব্রিজ (`ocean gui`) এবং **BACH**-এর মতো সংস্করণের জন্য তত্ত্বাবধানকৃত রানটাইম ভিত্তি প্রদান করে। সম্পূর্ণ CLI রেফারেন্স (`16`টি প্রধান কমান্ড, `16`টি সাব-কমান্ড): [`api/cli-reference.md`](api/cli-reference.md)।

## তিনটি অ্যাক্সেস মোড

1. **মোড A — লাইব্রেরি ও ডায়াগনস্টিকস (শুধু পাঠযোগ্য):** `ocean_resources.client`, `tools.ocean_inspect`, `tools.governance_bridge`, `tools.help_projection`, `python ocean.py stack-status|authority`
2. **মোড B — সক্রিয় কম্পোজিশন, টাস্ক ও GUI ব্রিজ:** `python ocean.py plan|up|inspect|gui|task` + `tools.gui_bridge` / `tools.gui_server`
3. **মোড C — রানটাইম সুপারভাইজার, এজেন্ট ও কনসোল:** `python ocean.py start|status|agents|sessions|tasks|chat|console|user|down` + `tools.runtime_supervisor`

## ডকুমেন্টেশন অগ্রাধিকার ক্রম (#2459)

1. **সাম্প্রতিক ব্যবহারকারী সিদ্ধান্ত** (সিদ্ধান্ত রেকর্ড / অপারেটরের সুস্পষ্ট অনুমোদন)
2. **সক্রিয় রূপান্তর পরিকল্পনা** (চলমান মাইগ্রেশন ক্ষেত্রের জন্য)
3. **মডিউল ডকুমেন্টেশন** (`ellmos.module.v2` ম্যানিফেস্টের `docs` এন্ট্রি)
4. **কোর ডকুমেন্টেশন** (ইনস্টল করা কার্নেলের `docs/CORE.md` এবং `SKILL.md`)
