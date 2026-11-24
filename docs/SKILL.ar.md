---
name: open-ocean
version: 0.3.1
updated: 2026-11-24
language: ar
category: infrastructure
description: "النواة المحلية القابلة للتحقق لتركيب وتشغيل منظومة ellmos بثلاثة أنماط وصول (المكتبة والتحقق من الصلاحيات، التركيب النشط وجسر الواجهة الرسومية، ومشرف التشغيل والوكلاء)."
---

# open-ocean — مهارة النظام وأنماط الوصول (AR)

**اللغات (World Set 11):** [Deutsch](../SKILL.md) · [English](SKILL.en.md) · [Español](SKILL.es.md) · [Français](SKILL.fr.md) · [Português](SKILL.pt.md) · [Русский](SKILL.ru.md) · [中文](SKILL.zh.md) · [日本語](SKILL.ja.md) · **العربية** · [हिन्दी](SKILL.hi.md) · [বাংলা](SKILL.bn.md)

توفر `open-ocean` النواة التصريحية لتركيب الأنظمة، وتحكيم الموارد، والتحقق الحتمي من الصلاحيات عبر ثلاث طبقات (`ocean authority`)، وجسر واجهة النظام المثبت بالبصمة (`ocean gui`)، وبيئة التشغيل المُراقَبة التي تعتمد عليها إصدارات مثل **BACH**. المرجع الكامل لواجهة الأوامر (`16` أمراً رئيسياً و`16` أمراً فرعياً): [`api/cli-reference.md`](api/cli-reference.md).

## أنماط الوصول الثلاثة

1. **النمط A — المكتبة والتشخيص (للقراءة فقط):** `ocean_resources.client`، `tools.ocean_inspect`، `tools.governance_bridge`، `tools.help_projection`، `python ocean.py stack-status|authority`
2. **النمط B — التركيب النشط والمهام وجسر GUI:** `python ocean.py plan|up|inspect|gui|task` مع `tools.gui_bridge` / `tools.gui_server`
3. **النمط C — مشرف التشغيل والوكلاء والطرفية:** `python ocean.py start|status|agents|sessions|tasks|chat|console|user|down` مع `tools.runtime_supervisor`

## أولوية التوثيق (#2459)

1. **قرار المستخدم الأحدث** (سجلات القرارات / اعتماد المشغل الصريح)
2. **خطة التحويل النشطة** (للنطاقات قيد الترحيل النشط)
3. **توثيق الوحدة** (حقل `docs` في بيان `ellmos.module.v2`)
4. **التوثيق الأساسي** (`docs/CORE.md` و`SKILL.md` للنواة المثبتة)
