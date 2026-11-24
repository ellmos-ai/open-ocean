---
name: open-ocean
version: 0.3.1
updated: 2026-11-24
language: hi
category: infrastructure
description: "ellmos पारिस्थितिकी तंत्र का स्थानीय, सत्यापन-योग्य संयोजन और रनटाइम कर्नेल जिसमें तीन एक्सेस मोड हैं (रीड-ओनली लाइब्रेरी व अधिकार जाँच, सक्रिय संयोजन व GUI ब्रिज, तथा पर्यवेक्षित रनटाइम व एजेंट सेवा)।"
---

# open-ocean — सिस्टम कौशल और एक्सेस मोड (HI)

**भाषाएँ (World Set 11):** [Deutsch](../SKILL.md) · [English](SKILL.en.md) · [Español](SKILL.es.md) · [Français](SKILL.fr.md) · [Português](SKILL.pt.md) · [Русский](SKILL.ru.md) · [中文](SKILL.zh.md) · [日本語](SKILL.ja.md) · [العربية](SKILL.ar.md) · **हिन्दी** · [বাংলা](SKILL.bn.md)

`open-ocean` घोषणात्मक सिस्टम संयोजन, संसाधन प्रबंधन, तीन-स्तरीय अधिकार सत्यापन (`ocean authority`), पिन किए गए सिस्टम GUI ब्रिज (`ocean gui`) और **BACH** जैसे संस्करणों के लिए पर्यवेक्षित रनटाइम आधार प्रदान करता है। पूर्ण CLI संदर्भ (`16` मुख्य कमांड, `16` सब-कमांड): [`api/cli-reference.md`](api/cli-reference.md)।

## तीन एक्सेस मोड

1. **मोड A — लाइब्रेरी और निदान (केवल पठन):** `ocean_resources.client`, `tools.ocean_inspect`, `tools.governance_bridge`, `tools.help_projection`, `python ocean.py stack-status|authority`
2. **मोड B — सक्रिय संयोजन, कार्य और GUI ब्रिज:** `python ocean.py plan|up|inspect|gui|task` + `tools.gui_bridge` / `tools.gui_server`
3. **मोड C — रनटाइम सुपरवाइज़र, एजेंट और कंसोल:** `python ocean.py start|status|agents|sessions|tasks|chat|console|user|down` + `tools.runtime_supervisor`

## दस्तावेज़ीकरण वरीयता क्रम (#2459)

1. **नवीनतम उपयोगकर्ता निर्णय** (निर्णय रिकॉर्ड / ऑपरेटर की स्पष्ट स्वीकृति)
2. **सक्रिय रूपांतरण योजना** (चल रहे माइग्रेशन क्षेत्रों के लिए)
3. **मॉड्यूल दस्तावेज़ीकरण** (`ellmos.module.v2` मैनिफ़ेस्ट में `docs` प्रविष्टि)
4. **कोर दस्तावेज़ीकरण** (स्थापित कर्नेल के `docs/CORE.md` और `SKILL.md`)
