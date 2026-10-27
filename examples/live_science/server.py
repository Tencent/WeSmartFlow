#!/usr/bin/env python3
"""
server.py — 知识之境 · live_science 本地服务器（复用主项目鉴权和用量服务）

职责：
1. 静态文件服务（替代 python -m http.server）
2. GET  /api/health — 报告 LLM/TTS 可用性
3. POST /api/llm   — 代理 LLM 调用（OpenAI 兼容 chat/completions）
4. POST /api/tts   — 代理 TTS 调用（OpenAI 兼容 audio/speech，可选）
   配置自动复用 edu-agent 根目录的 .env：
     LLM_BASE_URL / LLM_API_KEY / LLM_MODEL          （必配，自由问答用）
     TTS_BASE_URL / TTS_API_KEY / TTS_MODEL / TTS_VOICE （选配，真人级配音用）

运行：python3 server.py  （默认端口 8767）
"""

import json
import os
import shutil
import urllib.request
import urllib.error
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENV_PATH = ROOT.parent.parent / ".env"  # edu-agent/.env
PORT = int(os.environ.get("PORT", "8767"))
# 默认只监听本机回环；确需局域网访问时显式设置 LIVE_SCIENCE_HOST=0.0.0.0。
HOST = os.environ.get("LIVE_SCIENCE_HOST", "127.0.0.1")
ALLOWED_ORIGINS = {
    o.strip()
    for o in os.environ.get(
        "CORS_ORIGINS", "http://localhost:5173,http://localhost:5174"
    ).split(",")
    if o.strip() and o.strip() != "*"
}

ENV_KEYS = [
    "LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL",
    "TTS_BASE_URL", "TTS_API_KEY", "TTS_MODEL", "TTS_VOICE",
    "IMG_BASE_URL", "IMG_API_KEY", "IMG_MODEL",
    "DASHSCOPE_API_KEY", "TAVILY_API_KEY",
]

# DashScope 纯 HTTP（零依赖，无需 pip install dashscope）
DASHSCOPE_GEN_URL = "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"


def load_env_config():
    """从 edu-agent 根目录 .env 读取配置"""
    cfg = {k: "" for k in ENV_KEYS}
    if not ENV_PATH.exists():
        return cfg
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        if k in cfg:
            cfg[k] = v.strip().strip('"').strip("'")
    return cfg


CFG = load_env_config()

# Integrated and standalone paid routes share authenticated usage accounting.
import sys
sys.path.insert(0, str(ROOT.parent.parent / "backend"))
from services.external_usage import before_raw, record_raw, UsageThread, usage_scope
from services.credit_quota import CreditsExceeded



def _llm_request(base, key, model, messages, timeout, max_tokens, json_mode=False):
    before_raw("llm", model=model)
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.8,
        "max_tokens": max_tokens,
    }
    if json_mode:  # DeepSeek/OpenAI 兼容的强制 JSON 输出
        payload["response_format"] = {"type": "json_object"}
    payload = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        base.rstrip("/") + "/chat/completions",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
    data = json.loads(raw)
    msg = data["choices"][0]["message"]
    from services.pricing import ensure_usage
    record_raw("llm", model=model, usage=ensure_usage(data.get("usage"), messages, msg.get("content")))
    text = (msg.get("content") or "").strip()
    if not text:
        text = (msg.get("reasoning_content") or "").strip()
    if not text:
        raise RuntimeError(f"empty content, finish_reason={data['choices'][0].get('finish_reason')}")
    return text


def call_llm(messages, timeout=60, max_tokens=3000, json_mode=False):
    """项目 LLM 优先；余额/鉴权失败时自动回退 DashScope qwen-plus（OpenAI 兼容模式）"""
    try:
        return _llm_request(CFG["LLM_BASE_URL"], CFG["LLM_API_KEY"], CFG["LLM_MODEL"],
                            messages, timeout, max_tokens, json_mode)
    except CreditsExceeded:
        raise
    except Exception as e:
        if CFG["DASHSCOPE_API_KEY"]:
            print(f"[llm] 主通道失败({e})，回退 DashScope qwen-plus")
            return _llm_request("https://dashscope.aliyuncs.com/compatible-mode/v1",
                                CFG["DASHSCOPE_API_KEY"], "qwen-plus",
                                messages, timeout, max_tokens, json_mode)
        raise


# ================= 篇章生成管线 =================
import threading
import re

JOBS = {}  # job_id -> {stage, message, slug}

STYLE_SUFFIX = (", 3D otome game style cinematic render, exquisite detailed face, elegant flowing composition, "
                "soft volumetric god rays, deep purple and gold palette, film still, ultra detailed, masterpiece quality, "
                "clean scene, no text, no words, no letters, no watermark, no signature, no UI elements")

# 序章/终章的向导形象专用描述（保证跨图一致 + 避免文字出戏）
GUIDE_PROMPT_HINT = ("a mysterious ethereal celestial guide figure with flowing silver-blue luminous hair, "
                     "elegant translucent ribbon gown made of starlight, standing in a vast nebula of deep purple and gold")

AUDIENCE_LABELS = {
    "elementary": "小学生（全口语、拟人化、术语必须当场翻译成大白话；决策点二选一情感驱动；实验只用滑块/点击直观型；quiz 为看图直观判断）",
    "middle": "初中生（直觉先行、半术语化；决策三选一；实验为滑块+读数；quiz 为课本基础题）",
    "high": "高中生（术语准确对齐人教A版教材；干扰项用真实历史错误观点；全类型实验；quiz 为课本/高考基础题）",
    "university": "大学生（可谈证明思想与学派争议；决策可开放辩论；quiz 升级为思考题）",
    "public": "大众科普（趣味优先、生活类比、弱课标映射）",
}

INTERACT_TYPES = """【首选】custom-lab：通用参数化实验（滑块+运算+读数+完成条件全部声明式配置，任何主题适用）。config 结构：
  sliders:[{id,label,min,max,step,init}]（**id 必须是简单英文变量名，如 a/b/x/rate/temp/pop，禁止使用 JS 保留字 var/in/of/class/function/new/this/typeof 等——否则表达式求值会失败**），可选 ops:[运算符号数组]，
  readouts:[{label, expr}]（expr 为 JS 表达式，可用滑块 id、op、Math、touched.<id>.size），
  big:{label, expr}（画布大字读数），win:{expr, text}（完成条件与达成文案），hint/note 提示。
  示例（封闭性检测）：sliders a,b 两个整数；ops ["+","−","×","÷"]；win.expr 用 op 与 a,b 判定。
  **ops 只在该实验的核心机制确实是"选运算符"时才加**（如封闭性检测）；其余实验（如连续型数值模拟）不要加 ops——若加了 ops 却没有任何 readouts/big/win 的 expr 用到裸标识符 op，就是无意义的装饰性按钮，必须删除 ops 字段。
- tycho-data：真实数据研读（表格找异常行）。**只需给出叙事语义，不要计算任何具体数值**——LLM 不擅长保证"恰好几行异常且幅度分明"，具体数值由代码事后按规则精确构造，你只需判断"哪些记录在历史上是关键异常"。rows 恰好 10 行，每行对象 {"date":"记录标识（如日期/世代/组号，需体现真实历史顺序）","anomaly":true/false}；恰好 1-2 行 anomaly=true（对应真实历史上那条关键异常记录，异常的科学原因写进 hint/conclusion，不要写进 rows）；其余 8-9 行 anomaly=false；cols 给四个中文表头 [记录列表头, 实测量表头, 理论预期表头, "偏差"]（如 ["世代","子代平均尾长(cm)","理论递减值(cm)","偏差"]）；hint 用角色口吻引导去找异常（不要提前透露是哪一行）；conclusion 是异常指向的真实科学结论
- law-finder：跨样本找恒定规律（如开普勒第三定律 T²∝a³、胡克定律 F∝x）。适用场景：科学家手头有多个真实样本（多颗行星/多个弹簧/多组电路），要在其中找出"某个量的组合在所有样本上恒定不变"的规律——这与 tycho-data（找反例/异常）是完全不同的推理，不要混用。**只需给出真实的 x 值（历史真实数据）和目标关系表达式，不要计算 y**——y 由代码按你给的目标关系精确构造，保证正确公式在所有样本上算出几乎恒定的值。
  rows: 恰好 5-6 行，每行 {"label":"样本名（如『水星』『金星』）","x":真实数值}（x 必须是可查证的真实历史数据，如各行星的轨道半长轴 AU 数）
  target_expr: 一个以 x 为自变量的 JS 表达式字符串，代表"科学家最终发现的真实规律"（如开普勒第三定律排除法可用 "x**1.5" 表示 T=x^1.5，即 T²=a³）——必须是真实科学史上的关系，不要编造
  xLabel/yLabel: 两个中文表头（如 "轨道半长轴 a (AU)" / "公转周期 T (年)"）
  candidates: 3-4 个候选公式 [{"expr":"JS表达式","label":"中文描述，如『T／a』"}]，**必须包含 target_expr 本身对应的一个候选**（label 写成学生看得懂的中文比值描述，不要直接抄 target_expr），其余候选是历史上真实存在过的错误猜想或临近的错误比例关系（如 T/a、T/a²，制造"看起来也合理但不恒定"的干扰）
  hint/note：角色口吻引导 + 补充说明（可提史实背景，如"第谷留下的数据摆在你面前，答案曾让整个欧几里得几何体系崩塌"）
【以下四种是几何/物理主题的专用实验，仅当主题确实是圆锥曲线/轨道力学/光学时使用，否则一律用 custom-lab】
- volume-cube：倍立方逼近（仅圆锥曲线篇）
- cone-slice：切圆锥（仅圆锥曲线篇）
- ellipse-params：椭圆参数联动（仅圆锥曲线篇）
- orbit-velocity：轨道力学模拟（仅轨道/引力主题）
- light-focus：抛物面聚焦对比（仅光学/抛物线主题）"""

GEN_PROMPT = '''你是「知识之境」篇章工厂的剧本师。为科学主题【{topic}】生成完整篇章剧本。
受众画像：{audience_desc}

【叙事结构】8 个节点：序章（概念拟人化向导引入）→ 5-6 个历史节点（沿时间线：发现→体系化→实证→形式化→统一/应用）→ 终章（向导揭示真名=知识点本身）。
每幕节奏：briefing 幕前铺垫（**必须 2-3 页，每页至少 120 字，不能只写 1 页**，讲清时代困境的前因后果，且必须包含"这个知识点到底是什么"的清晰讲解——不能只用意境化隐喻一笔带过）→ dialogues 对话（**必须 4-6 句，不能少于 4 句**）→ choice 决策点（历史困境，干扰项=真实历史错误观点）→ interact 探究实验 → afterChoice 收尾（**2-3 句，情感高峰+知识点再强调一次**）→ bridge 衔接课堂（课本映射+小题）→ card 知识卡。

【内容深度铁律——这是最容易被忽略、但最重要的一条】
每个历史节点的 briefing 必须做到三件事，缺一不可：
① 讲清楚"当时的知识背景"——读者需要知道的前置概念，用一两句话讲明白，不能假设读者已经懂
② 讲清楚"这个人到底发现/证明/构造了什么"——具体的数学/科学内容本身，不能只停留在"他很困惑""他灵光一闪"这种情绪化描述而回避内容
③ 讲清楚"这一步为什么关键"——它解决了什么问题，或者打开了什么新问题
不要把 briefing 写成纯粹的文学化场景描写（那是 dialogues 该做的事）；briefing 是读者获取知识的主要渠道，必须信息密度高、讲解到位，读完之后读者应该"看懂了"这一步在讲什么数学/科学内容，而不是只感受到了氛围。

【历史知识 ↔ 课本知识的联结必须是真推导，不是贴标签——这是本次重点加固的一条】
之前的失败模式：bridge.mapping 只写"‘24种排列’ → S₄（4阶对称群）含4!=24个元素"这种箭头短语，读者看到的是两个名词被强行画等号，看不出"为什么历史发现在数学上等价于课本概念"，读起来像贴标签而非真推导，这正是"花拳绣腿"的根源。
新规则：
① bridge.mapping 每一条**必须是完整的推导句**（不是箭头短语），结构固定为"当年他做的[具体操作/发现]，用今天课本的语言严格地说，就是[课本概念]——因为[数学/逻辑等价的原因]"。例如不要写"‘24种排列’ → S₄含4!=24个元素"，要写"拉格朗日数的4个根的所有排列方式恰好是24种，这在今天的课本语言里就是对称群S₄——因为n个元素的全部置换在数学上天然构成一个群，n=4时元素个数为4!=24，他当年数出来的排列数和课本定义S₄的方式，本质是同一件事"。每条不少于50字，必须出现"因为/由于/本质上/等价于"这类给出推导理由的连接词，不能只是把两个短语并列。
② briefing 的**最后一页**必须显式预告"这段历史将对应到什么现代概念"（不需要写课本页码，只需一句话点出"你即将学到的东西，此刻正在被这段历史发现"），让读者在进入 dialogues/interact 之前已经知道自己在探究什么，而不是全程被悬念吊着、直到最后 bridge 才第一次看到知识点名字。
③ card.text 不能只是概念的静态定义复述——必须包含"这个概念解决了 briefing 里提到的哪个具体困境"这一句，让"历史困境"和"课本概念"在同一段文字里被同时提及，形成读者能直接看到的因果链，而不是两个孤立的知识片段。

【铁律】
1. 困境先行：每节点必须有一个真实的"当时未解的难题"
2. 数字必须真实可查证
3. NPC 严守时代知识边界（freetalk.persona 里写死"你只知道 XX 年之前的知识"）
4. 对话台词有性格；单句不超过 80 字；关键词用 <b class="em">高亮</b>
5. briefing 文本可用 <span class="formula-line">居中公式行</span> 和 <span class="violet">紫色关键概念</span>
6. 课标必须诚实（bridge.textbook / card.textbook / bridge.mapping[] / bridge.quiz.explain / river_book **五处都要遵守**，不能只顾 textbook 一处——mapping 和 quiz.explain 是最容易漏检的两处，之前发生过 textbook 已经诚实标注"大学先修"，但 mapping 里仍写"课本P80『群的四个公理』"、explain 里仍写"（例4）"这种精确页码/例题号，同一节点内自相矛盾的真实事故）：若主题超出该学段真实课标（如抽象代数不在高中课本），三处都写「大学先修 · 《近世代数》拓展」之类的真实定位，绝对禁止编造教材版本名（如"人教A版选修三"——现行人教A版只有必修+选择性必修，没有"选修三"这个册次）、章节号、页码。**绝对禁止编造任何量化数字**——"考试权重约12%""高考年均2-3题""分值6-8分"这类百分比/题量/分值，没有统一考纲依据、完全是编造，一律不写；**绝对禁止编造思想史排名/并列关系**——"现代数学三大支柱之一，与微积分、数理逻辑并列""与日心说、相对论并列为三大科学革命"这类"三大XX之一"式排名是虚构的历史学术共识，一律不写，只客观描述这个知识点本身的作用和意义（如"为代数方程的可解性提供了完整判据"），不要编造它在整个学科史里的排名位次。此类超纲主题 quiz 改为思考题。若主题确实在课标内（如万有引力在高中必修二），可写真实的教材定位但不要编造精确页码范围（写"必修二 · 万有引力定律"而非"必修二 P46"，页码未经核实不能写），也不要编造考试分值/题量
7. freetalk.hint 必须用角色口吻的入戏邀请（如「出发之前，还有什么想和我聊聊的吗？」），禁止任何技术术语（接口、配置等）
8. tycho-data 的 rows 必须是对象数组，字段固定为 date/obs/pred/dev（dev 为数值），并带 cols（四列中文表头）、hint（角色口吻引导语）、conclusion（异常指向的结论）
9. cast 必须覆盖每一个在 dialogues/afterChoice 里作为 who 出现过的科学家姓名（向导名、"旁白"、"你"不需要），性别必须真实准确——配音选声完全依赖这个字段，性别错填会导致历史人物被配上错误性别的声音
10. dialogues/afterChoice 的 text 会被 TTS 朗读，禁止写公式等式（如"F=Gm₁m₂/r²"）和多字母下标连写（如"S₃""A₅"作为拼接主体）——TTS 会把这类符号读成乱码或吞掉下标（实测 F=Gm₁m₂/r² 被读成不可辨认的乱音，A₅ 被读成"哎"）。正确做法：等式全部口语化（"F等于G乘m1乘m2除以r的平方"），字母+下标的数学对象用中文全称代替（"S₃"→"三阶置换群"，"A₅"→"五阶交错群"）。单纯的上标次方²³和"×10²⁴"这类科学记数法 TTS 能正确读出，不必改写；只有等式(=)、多变量连写、纯符号堆砌才是真正的风险点
11. 应用幕（app_nodes）：从 river_apps 精选 2-3 个最有价值的应用，每个展开成一幕完整的「知识应用现场」——当下或近未来的真实工作场景（发射控制室/手术室/实验室/工程现场），由职业人物（工程师/医生/科学家，进 cast 标注性别）用本篇章的课本知识解决一个具体问题。对话必须体现知识的具体使用（真实参数、真实计算、真实取舍），严禁口号式赞美"知识真有用"；每幕一个决策点让学生做技术选择（正解=用对知识，干扰项=用错知识并在回应中纠偏）；eraTitle 必须以「应用篇 · 」开头；台词 TTS 规则同第 10 条

【输出】只输出一个合法 JSON 对象（可用 ```json 包裹，此外不要任何文字）：
{{
  "slug": "英文小写短slug（必须是真实英文单词/词组的 kebab-case，如 photosynthesis-journey、cell-theory-journey；绝对禁止用中文拼音，如 shulie-zhi-jing、xulie 这类拼音串）",
  "title": "篇章标题（如：万有引力 · 从苹果到星辰）",
  "subtitle": "一句话副标题",
  "guide_name": "概念拟人化向导名（如：引力之灵）",
  "cast": {{"科学家姓名1":"m 或 f 或 m-old 或 m-young 或 f-old 或 f-young（性别必须真实——绝大多数科学史人物是男性，只有确实是女性历史人物才填 f，如玛丽·居里、爱达·洛芙莱斯；年龄后缀按人物真实年龄段标注：年长学者/老者标 -old 配沉稳老者音色，少年/年轻学者标 -young，不标默认中年音色；应用幕的职业人物同样标注）", "科学家姓名2":"同左"}},
  "endings_max": 180,
  "nodes": [
    {{
      "id": "英文小写id",
      "eraEn": "1609 A.D. · Prague 式",
      "eraTitle": "1609年 · 布拉格 式",
      "image_prompt": "英文场景描述（人物+时代服饰+核心道具+光影氛围；画面中绝对不要出现任何文字、公式、字母、符号、书本封面文字）",
      "briefing": [{{"title":"…","text":"…"}}] 或 null,
      "dialogues": [{{"who":"说话人——只能是「旁白」「你」、guide_name 的值本身、或该节点科学家的真实姓名，禁止用「向导名」等占位词","text":"…"}}],
      "choice": {{"prompt":"…","options":[{{"t":"选项文字","d":20,"r":"NPC回应（正解）"}},{{"t":"…","d":5,"r":"…（干扰项，回应中纠偏）"}}]}} 或 null,
      "freetalk": {{"hint":"…","persona":"角色卡（年代/性格/知识边界）","presets":[{{"q":"…","a":"…"}}]}} 或 null,
      "interact": {{"type":"custom-lab / tycho-data / law-finder 之一","title":"…","intro":"…","config":{{仅 custom-lab，见上方结构}}, "rows":[tycho-data 每行{{date,anomaly}}；law-finder 每行{{label,x}}，见下方说明], "cols":[tycho-data 四个中文表头], "target_expr":"仅 law-finder", "xLabel":"仅 law-finder", "yLabel":"仅 law-finder", "candidates":[仅 law-finder], "hint":"…", "conclusion":"…（仅 tycho-data）", "note":"仅 law-finder 可选"}} 或 null,
      "afterChoice": [{{"who":"…","text":"…"}}],
      "bridge": {{"textbook":"教材定位","mapping":["历史发现→课本概念的完整推导句，2-3条，每条≥50字，须含'因为/由于/本质上/等价于'类连接词——见上方'历史知识↔课本知识联结'规则，禁止写成箭头短语"],"quiz":{{"q":"…","options":["A","B","C","D"],"answer":0,"explain":"解析要回扣历史场景"}}}} 或 null,
      "card": {{"title":"…","text":"定义句 + 一句'这个概念解决了briefing里的什么困境'","formula":"…","textbook":"…"}} 或 null
    }}
  ],
  "app_nodes": [
    {{
      "id": "英文小写id（如 satellite-launch）",
      "eraEn": "2024 A.D. · Wenchang 式",
      "eraTitle": "应用篇 · 2024年 · 文昌航天发射场 式（必须以「应用篇 · 」开头）",
      "image_prompt": "英文现代应用场景描述（职业人物+工作环境+核心设备+光影氛围；画面中绝对不要出现任何文字、公式、字母、符号、屏幕上的字）",
      "briefing": [{{"title":"…","text":"…"}}]（1-2页：这个应用现场是什么、此刻要解决什么真实问题）,
      "dialogues": [{{"who":"说话人——只能是「旁白」「你」、guide_name 的值本身、或该幕职业人物姓名","text":"…"}}]（4-6句：课本知识如何被具体使用——真实参数、真实计算、真实张力）,
      "choice": {{"prompt":"…","options":[{{"t":"选项文字","d":20,"r":"NPC回应（正解）"}},{{"t":"…","d":5,"r":"…（干扰项，回应中纠偏）"}}]}}（学生帮职业人物做一次技术决策）,
      "afterChoice": [{{"who":"…","text":"…"}}]（收尾：这个应用的价值点题，具体不空泛）
    }}
  ],
  "river": [{{"stage":"诞 生","era":"…","who":"…","did":"…","pass":"传给下一站的一句话"}}],
  "river_book": "课本地位的客观描述——禁止编造考试权重百分比/题量/分值，禁止编造'三大XX之一/与YY并列'式排名",
  "river_apps": ["emoji 应用——原理（5-6 条）"],
  "river_quote": "向导的最终引言"
}}

可选 interact.type：
{interact_types}'''


def slugify(s):
    s = re.sub(r'[^a-z0-9]+', '-', s.lower()).strip('-')
    return s or 'chapter'


def call_image(prompt, timeout=180):
    """qwen-image（DashScope multimodal-generation），返回图片二进制"""
    model = CFG["IMG_MODEL"] or "qwen-image-2.0"
    before_raw("image", model=model, provider="qwen")
    payload = json.dumps({
        "model": CFG["IMG_MODEL"] or "qwen-image-2.0",
        "input": {"messages": [{"role": "user", "content": [{"text": prompt}]}]},
        "parameters": {"size": "1536*1024", "n": 1},
    }).encode("utf-8")
    req = urllib.request.Request(
        CFG["IMG_BASE_URL"] or DASHSCOPE_GEN_URL,
        data=payload,
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {CFG['IMG_API_KEY'] or CFG['DASHSCOPE_API_KEY']}"},
        method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read().decode())

    def find_url(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k in ("image", "url") and isinstance(v, str) and v.startswith("http"):
                    return v
                r = find_url(v)
                if r:
                    return r
        elif isinstance(o, list):
            for it in o:
                r = find_url(it)
                if r:
                    return r
        return None

    url = find_url(data.get("output"))
    if not url:
        raise RuntimeError("image gen 无图片返回: " + json.dumps(data, ensure_ascii=False)[:200])
    record_raw("image", model=model, provider="qwen")
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return r.read()


def extract_json(text):
    """从 LLM 输出提取 JSON，带容错修复（尾随逗号/JS布尔/未转义换行）"""
    m = re.search(r'```(?:json)?\s*(\{.*\})\s*```', text, re.S)
    if m:
        text = m.group(1)
    i, j = text.find('{'), text.rfind('}')
    if i < 0 or j <= i:
        raise ValueError("LLM 输出中找不到 JSON")
    s = text[i:j+1]
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        s2 = re.sub(r",\s*([}\]])", r"\1", s)          # 尾随逗号
        s2 = re.sub(r"\bTrue\b", "true", s2)
        s2 = re.sub(r"\bFalse\b", "false", s2)
        s2 = re.sub(r"\bNone\b", "null", s2)
        s2 = re.sub(r'(?<=:\s)\'([^\']*)\'(\s*[,}\]])', r'"\1"\2', s2)  # 单引号值
        return json.loads(s2)


# ================= Tavily 史实调研 =================
def call_tavily(query, timeout=30):
    """Tavily 搜索：返回答案摘要 + 结果正文片段"""
    before_raw("search", provider="tavily")
    payload = json.dumps({
        "api_key": CFG["TAVILY_API_KEY"],
        "query": query,
        "search_depth": "advanced",
        "max_results": 5,
        "include_answer": True,
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://api.tavily.com/search",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read().decode("utf-8"))
    record_raw("search", provider="tavily", units=(data.get("usage") or {}).get("credits", 2))
    parts = []
    if data.get("answer"):
        parts.append("【摘要】%s" % data["answer"])
    for it in (data.get("results") or [])[:5]:
        parts.append("【%s】%s\n%s" % (it.get("title", ""), it.get("url", ""), (it.get("content") or "")[:600]))
    return "\n\n".join(parts)


def extract_textbook_knowledge(topic, audience):
    """从本地教材索引召回 topic 相关的课内知识点（章节标题 + 页码 + 原文），
    作为生成剧本的最高优先级知识骨架——召回越全面越贴近课本。

    召回策略：
    - 关键词命中「章标题」→ 整章召回（遍历该章所有节，覆盖完整知识体系；如"数列"→数列的概念+等差+等比+数学归纳法）
    - 关键词只命中「节标题」→ 召回该节
    - 整章召回最多 6 章（覆盖"细胞"这类跨多章主题的完整知识体系；每节压字数控总量）

    学段映射：elementary→小学, middle→初中, high→高中；university/public 无教材索引返回空。
    未命中教材时返回空字符串，由 research_topic 的科学史素材兜底（topic 不在教材范围内）。
    """
    stage_map = {"elementary": "小学", "middle": "初中", "high": "高中"}
    stage = stage_map.get(audience, "")
    try:
        import sys
        scripts_dir = str(ROOT / "textbook_index" / "scripts")
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        from lookup import find_chapter, get_page_text
    except Exception as e:
        print("[textbook] 教材索引不可用：%s" % e)
        return ""

    hits = find_chapter(topic, stage=stage) if stage else find_chapter(topic)
    if not hits and stage:
        hits = find_chapter(topic)  # 学段放宽重试（可能属于相邻学段）
    if not hits:
        print("[textbook] 关键词「%s」未命中教材目录" % topic)
        return ""

    blocks = []
    seen_chapters = set()
    full_chapters = 0  # 整章召回计数（控制总量）

    for h in hits:
        ch = h["chapter"]
        ch_key = (h["subject"], h["grade"], ch["title"])
        if ch_key in seen_chapters:
            continue
        seen_chapters.add(ch_key)

        if topic in ch["title"]:
            # 命中章标题 → 整章召回（遍历所有节，覆盖完整知识体系）
            full_chapters += 1
            if full_chapters > 6:
                continue
            secs = ch.get("sections") or []
            if not secs:
                # 章节无子节（目录解析失败等）→ 整章兜底提取
                start = ch.get("start_page") or ch.get("page") or 1
                end = ch.get("end_page") or start + 5
                if end <= start:
                    end = start + 5
                text = get_page_text(h["path"], start, end)
                if text:
                    blocks.append("【%s·%s】%s → %s（第%d-%d页）\n%s"
                                  % (h["subject"], h["grade"], h["title"], ch["title"], start, end, text[:900]))
                continue
            for sec in secs:
                start = sec.get("page") or sec.get("start_page") or ch.get("start_page") or 1
                end = sec.get("end_page") or start + 3
                if end <= start:  # 索引数据个别 end_page 解析异常，兜底
                    end = start + 3
                text = get_page_text(h["path"], start, end)
                if text:
                    blocks.append("【%s·%s】%s → %s（第%d-%d页）\n%s"
                                  % (h["subject"], h["grade"], ch["title"], sec["title"], start, end, text[:350]))
        else:
            # 命中节标题（不在章标题）→ 召回该节
            node = h["section"] or ch
            start = node.get("page") or node.get("start_page") or ch.get("start_page") or 1
            end = node.get("end_page") or start + 3
            if end <= start:
                end = start + 3
            text = get_page_text(h["path"], start, end)
            if text:
                loc = h["section"]["title"] if h["section"] else ch["title"]
                blocks.append("【%s·%s】%s → %s（第%d-%d页）\n%s"
                              % (h["subject"], h["grade"], ch["title"], loc, start, end, text[:700]))

    if not blocks:
        return ""
    return "\n\n".join(blocks)[:12000]


def research_topic(topic, audience):
    """剧本生成前的史实调研：科学史细节 + 真实课标定位，作为素材注入剧本 prompt"""
    if not CFG["TAVILY_API_KEY"]:
        return ""
    queries = [
        "%s 科学史 关键人物 历史事件 时间线 趣闻 困境" % topic,
        "%s 历史 未解难题 争议 真实数据 发现过程" % topic,
        "%s 教材 课标 章节 哪个年级 人教版" % topic,
    ]
    if audience in ("university", "public"):
        queries[2] = "%s 大学课程 教材 章节 哪门课" % topic
    blocks = []
    for q in queries:
        try:
            blocks.append("### 检索：%s\n%s" % (q, call_tavily(q)))
        except Exception as e:
            print("[tavily] 检索失败(%s): %s" % (q, e))
    return "\n\n".join(blocks)[:6000]  # 素材总量封顶


def gen_story(topic, audience, research="", textbook_kb=""):
    desc = AUDIENCE_LABELS.get(audience, AUDIENCE_LABELS["high"])
    prompt = (GEN_PROMPT
              .replace("{topic}", topic)
              .replace("{audience_desc}", desc)
              .replace("{interact_types}", INTERACT_TYPES))
    if textbook_kb:
        prompt += ("\n\n【课内教材知识点（本地教材索引提取，最高优先级知识骨架）——"
                   "剧本的每一幕必须严格锚定下面这些真实教材知识点，按教材章节顺序组织剧情；"
                   "这是真实课内内容，故事的\"知识\"部分必须取自这里，不得另编知识点、不得编造教材版本名/章节号/页码；"
                   "科学史细节只用于给这些知识点配上历史场景，但知识本体以这里为准：】\n" + textbook_kb)
    if research:
        prompt += ("\n\n【真实史料素材（Tavily 检索结果）——剧本中的史实、数字、人物细节、课标定位必须优先取材于此；"
                   "素材未覆盖的地方才允许用你的知识，但禁止编造精确页码/章节号：】\n" + research)
    last_err = None
    for attempt in range(2):
        p = prompt
        if attempt > 0:
            p += ("\n\n【上次输出解析失败：" + str(last_err)[:120] + "】请重新输出，必须是严格合法 JSON："
                  "所有键名和字符串一律双引号、无尾随逗号、无注释、字符串内不要出现未转义的英文双引号。")
        # 重型剧本生成走 DashScope qwen-plus（长 JSON 实测最稳；推理型模型 16K 易截断）
        raw = _llm_request("https://dashscope.aliyuncs.com/compatible-mode/v1",
                           CFG["DASHSCOPE_API_KEY"], "qwen-plus",
                           [{"role": "user", "content": p}], timeout=600, max_tokens=32768)
        try:
            story = extract_json(raw)
            assert story.get("nodes") and len(story["nodes"]) >= 6, "节点不足"
            assert story.get("river"), "缺 river"
            return story
        except Exception as e:
            last_err = e
            # 留存原始输出供调试
            with open("/tmp/live_science_gen_raw.txt", "w") as f:
                f.write(raw)
    raise RuntimeError("剧本 JSON 两次生成均不合法：" + str(last_err))


def _norm_row(r):
    """tycho-data 行统一为 {date,obs,pred,dev} 对象"""
    if isinstance(r, dict):
        if "dev" in r and "obs" in r:
            return r
        keys = list(r.keys())
        vals = [r[k] for k in keys]
        return {"date": vals[0], "obs": vals[1] if len(vals) > 1 else "",
                "pred": vals[2] if len(vals) > 2 else "", "dev": vals[3] if len(vals) > 3 else 0}
    if isinstance(r, list):
        return {"date": r[0] if len(r) > 0 else "", "obs": r[1] if len(r) > 1 else "",
                "pred": r[2] if len(r) > 2 else "", "dev": r[3] if len(r) > 3 else 0}
    return None


def _gap_threshold(devs_abs):
    """最大间隔切分法：与引擎 labTychoData 的判定算法保持完全一致。
    把 |dev| 降序排列，在 top1/top2、top2/top3 之间找差距最大的缝，阈值取缝两侧中点。
    不会像"倍数阈值"那样在数据打平（如两行并列最大值）时把阈值推过头导致 0 命中——这是曾经的真实 bug。"""
    s = sorted(devs_abs, reverse=True)
    if len(s) < 2:
        return (s[0] - 0.001) if s else 4.0
    best_gap, best_i = -1, 1
    for i in (1, 2):
        if i >= len(s):
            continue
        gap = s[i - 1] - s[i]
        if gap > best_gap:
            best_gap, best_i = gap, i
    return (s[best_i - 1] + s[best_i]) / 2 if best_i < len(s) else s[best_i - 1] - 0.001


# 科学史上确有记录的女性人物名单（用于 cast 兜底判断——LLM 漏填时代码不能瞎猜性别，
# 但历史科学家绝大多数是男性，所以未知角色默认判male远比默认交替/默认female准确得多；
# 这份名单只覆盖"确实是女性"的情况，用于纠正默认值）
KNOWN_FEMALE_SCIENTISTS = {
    "玛丽·居里", "居里夫人", "爱达·洛芙莱斯", "露丝·哈金斯", "罗莎琳德·富兰克林",
    "希帕提亚", "埃米·诺特", "诺特", "梅特纳", "莉泽·梅特纳", "卡罗琳·赫歇尔",
    "格蕾丝·霍普", "凯瑟琳·约翰逊", "多罗西·霍奇金", "简·古道尔", "玛丽亚·米切尔",
}

# 中文典型女性名用字（末字命中且 LLM 标了男性时自动纠正——实测 LLM 把应用幕的"林薇"标成了 m）
FEMALE_NAME_CHARS = set("薇婷娜静丽娟燕琳慧颖欣怡佳莹芳萍梅玲红玉洁云凤霞岚倩瑜媛")


DANGEROUS_TAGS = re.compile(
    r'<\s*(script|iframe|object|embed|link|meta|style|form|svg)\b[^>]*>.*?<\s*/\s*\1\s*>'
    r'|<\s*(script|iframe|object|embed|link|meta|style|form)\b[^>]*/?>'
    r'|on\w+\s*=\s*["\'][^"\']*["\']'
    r'|javascript\s*:',
    re.I | re.S)


def all_speech_nodes(story):
    """历史幕 + 应用幕的拼接列表（应用幕缺失时安全退化为历史幕）。"""
    return list(story.get("nodes") or []) + list(story.get("app_nodes") or [])


def sanitize_html_fields(story):
    """危险标签清洗：dialogues/briefing/card/bridge 等文本会被引擎直接 innerHTML 渲染，
    只允许 LLM 输出里约定的白名单标签（b/span/i），移除 script/iframe/on*事件属性/javascript: 等危险内容。
    本工具是纯本地单机运行、内容源是本地 LLM 输出，风险本身较低，但多一道防线成本几乎为零，
    比"确认后再说"更稳妥——尤其是 LLM 输出偶尔会有异常/被投毒的可能性不能完全排除。"""
    removed = []

    def clean(text):
        if not isinstance(text, str) or not text:
            return text
        if DANGEROUS_TAGS.search(text):
            removed.append(text[:60])
            return DANGEROUS_TAGS.sub('', text)
        return text

    for n in all_speech_nodes(story):
        for key in ("dialogues", "afterChoice"):
            for dlg in (n.get(key) or []):
                dlg["text"] = clean(dlg.get("text", ""))
        for b in (n.get("briefing") or []):
            b["title"] = clean(b.get("title", ""))
            b["text"] = clean(b.get("text", ""))
        card = n.get("card") or {}
        for k in ("title", "text", "formula", "textbook"):
            if k in card:
                card[k] = clean(card[k])
        bridge = n.get("bridge") or {}
        if "textbook" in bridge:
            bridge["textbook"] = clean(bridge["textbook"])
    for k in ("river_book", "river_quote"):
        if story.get(k):
            story[k] = clean(story[k])
    river_apps = story.get("river_apps") or []
    story["river_apps"] = [clean(a) for a in river_apps]
    return removed


def _looks_like_pinyin(slug):
    """启发式判断 slug 是否疑似中文拼音：由多个短音节（≤6字母）拼成、且不含英文词根。"""
    parts = slug.split("-")
    if len(parts) < 2:
        return False
    if any(len(p) > 6 for p in parts):
        return False
    EN_MARKERS = ("tion", "sion", "logy", "graph", "ness", "ology", "ism", "ance", "ence", "ment", "ity", "ous")
    if any(m in slug for m in EN_MARKERS):
        return False
    return True


def _translate_slug(title):
    """用 LLM 把中文标题翻译成英文短 slug（带后处理，容忍 LLM 输出啰嗦）。"""
    try:
        raw = _llm_request(
            "https://dashscope.aliyuncs.com/compatible-mode/v1",
            CFG["DASHSCOPE_API_KEY"], "qwen-plus",
            [{"role": "user", "content": "Translate this Chinese title to a short English slug: lowercase words joined by hyphens, max 3 words. Output ONLY the slug.\n\nTitle: %s" % title}],
            timeout=30, max_tokens=40)
        first = (raw or "").strip().splitlines()[0].strip()
        s = slugify(re.sub(r"[^a-zA-Z0-9\- ]", " ", first).strip())
        parts = s.split("-")
        if len(parts) > 4:  # LLM 输出成了句子 → 只取前 3 词
            s = "-".join(parts[:3])
        if s and s != "chapter":
            return s
    except Exception as e:
        print("[slug] 翻译失败: %s" % e)
    return ""


def validate_story(story):
    """生成后自动质检+修复：不是只报告——能修的全部修到位，修完冒烟复验，确保实验一定可完成"""
    issues = []
    removed = sanitize_html_fields(story)
    if removed:
        issues.append("安全清洗：移除 %d 处危险HTML标签/事件属性，样例：%s" % (len(removed), removed[:2]))
    # slug 质检：必须英文小写；疑似拼音/非法时自动翻译成英文
    slug = story.get("slug") or ""
    if not slug or not re.fullmatch(r"[a-z][a-z0-9-]{2,40}", slug) or _looks_like_pinyin(slug):
        en = _translate_slug(story.get("title") or "")
        if en:
            issues.append("slug 疑似拼音/非法「%s」，已翻译为英文「%s」" % (slug, en))
            story["slug"] = en
        else:
            issues.append("slug 疑似拼音/非法「%s」，翻译失败，保持原样" % slug)
    # cast 完整性兜底：LLM 可能漏填部分角色的性别，代码补全（默认 male，命中已知女性名单则 female）
    # ——这是"配音走性别错配"的最后一道防线，之前发生过卡文迪许/爱因斯坦被分配女声的真实事故
    cast = story.get("cast") or {}
    all_speakers = set()
    for n in all_speech_nodes(story):
        for key in ("dialogues", "afterChoice"):
            for dlg in (n.get(key) or []):
                who = dlg.get("who")
                if who and who not in ("旁白", "你", story.get("guide_name")):
                    all_speakers.add(who)
    for name in all_speakers:
        if name not in cast:
            cast[name] = "f" if name in KNOWN_FEMALE_SCIENTISTS else "m"
            issues.append("cast 缺失角色[%s]性别标注，已按%s兜底" % (name, cast[name]))
        else:
            raw = str(cast[name])
            # 女性名启发式：中文名末字为典型女性用字但标了男性 → 纠正（实测 LLM 把应用幕的"林薇"标成了 m）
            if raw.startswith("m") and len(name) >= 2 and name[-1] in FEMALE_NAME_CHARS:
                cast[name] = "f" + raw[1:]
                issues.append("cast 角色[%s]为典型女性名但标为男性，已自动纠正为女性" % name)

    # river_book 编造检测（实测踩过3篇章真实事故：三个已生成篇章的river_book都写了
    # "考试权重约12%"/"高考年均2-3题，分值6-8分"这类无据可查的量化数字，
    # 以及"现代数学三大支柱之一，与微积分、数理逻辑并列"/"与日心说、相对论并列为三大科学革命"
    # 这类虚构的思想史排名——这是node级别bridge/card课标诚实规则之外的第三个漏检点，
    # river_book在story顶层而不在node里，容易被"逐节点检查"的思路漏掉）
    river_book = story.get("river_book", "")
    if river_book:
        FABRICATED_WEIGHT = re.compile(r'权重|约\d+%|\d+%|高考年均|分值\d|考\d+[-~]\d+题|年均\d+[-~]\d+题')
        FABRICATED_RANK = re.compile(r'三大\S{0,6}之一|四大\S{0,6}之一|并列为|与.{1,10}并列')
        hit_weight = FABRICATED_WEIGHT.search(river_book)
        hit_rank = FABRICATED_RANK.search(river_book)
        if hit_weight or hit_rank:
            issues.append("river_book 疑似编造%s：「%s」，需改为客观描述（不写权重/排名）" %
                          ("考试权重数字" if hit_weight else "思想史排名", river_book))
        elif cast[name] not in ("m", "f"):
            cast[name] = "f" if name in KNOWN_FEMALE_SCIENTISTS else "m"
    story["cast"] = cast

    nodes = story.get("nodes", [])
    for n in nodes:
        nid = n.get("id", "?")
        it = n.get("interact") or {}
        t = it.get("type")
        if t == "tycho-data":
            raw_rows = it.get("rows") or []
            if not (6 <= len(raw_rows) <= 14):
                issues.append("%s: 数据表行数 %d 异常，已移除该实验" % (nid, len(raw_rows)))
                n["interact"] = None
                continue
            cols = it.get("cols")
            if not cols or len(cols) != 4:
                cols = ["记录", cols[0] if cols else "实测值", cols[1] if cols and len(cols) > 1 else "理论预期", "偏差"]
                issues.append("%s: cols 长度不足，已补全为4列" % nid)
            it["cols"] = cols[:4]
            if it.get("hitWhen") is not None:
                pass  # 字符串标记模式，不涉及数值合成
            elif any("anomaly" in r for r in raw_rows if isinstance(r, dict)):
                # 新架构：LLM 只给语义标记（date + anomaly bool），数值由代码精确构造
                # 命中数天然由 anomaly=true 的行数决定，若不在 1-2 范围内做最小纠偏（不改 LLM 的叙事判断，只调计数）
                anomaly_flags = [bool(r.get("anomaly")) for r in raw_rows if isinstance(r, dict)]
                n_anom = sum(anomaly_flags)
                if n_anom == 0:
                    raw_rows[-1]["anomaly"] = True
                    issues.append("%s: 无 anomaly=true 行，已指定末行为异常" % nid)
                elif n_anom > 2:
                    kept = 0
                    for r in raw_rows:
                        if r.get("anomaly"):
                            kept += 1
                            if kept > 2:
                                r["anomaly"] = False
                    issues.append("%s: anomaly=true 行数 %d>2，已保留前2行" % (nid, n_anom))
                it["rows"] = synth_tycho_rows(raw_rows, seed=hash(nid) & 0xffff)
                issues.append("%s: 数值已由代码合成（语义驱动，非 LLM 生成）" % nid)
            else:
                # 兼容旧格式（LLM 直接给了数值 dev）：归一化 + 最大间隔判定，异常时按语义重新合成而非硬改数字
                rows = [_norm_row(r) for r in raw_rows]
                rows = [r for r in rows if r]
                for r in rows:
                    try:
                        r["dev"] = float(r["dev"])
                    except (TypeError, ValueError):
                        r["dev"] = 0.0
                devs = [abs(r["dev"]) for r in rows]
                thresh = _gap_threshold(devs)
                hits = sum(1 for d in devs if d >= thresh)
                if not (1 <= hits <= 2):
                    # 退化为语义合成：按当前偏差排序取 top1 作为异常，其余合成正常值
                    order = sorted(range(len(rows)), key=lambda i: -devs[i])
                    semantic_rows = [{"date": rows[i]["date"], "anomaly": rank < 1} for rank, i in enumerate(order)]
                    semantic_rows.sort(key=lambda r: [rr["date"] for rr in rows].index(r["date"]))
                    rows = synth_tycho_rows(semantic_rows, seed=hash(nid) & 0xffff)
                    issues.append("%s: 旧格式数值判定失败，已退化为语义合成重建" % nid)
                it["rows"] = rows
        elif t == "law-finder":
            raw_rows = it.get("rows") or []
            target_expr = it.get("target_expr")
            cands = it.get("candidates") or []
            if not (4 <= len(raw_rows) <= 8) or not target_expr or len(cands) < 2:
                issues.append("%s: law-finder 配置不全（rows/target_expr/candidates），已移除实验" % nid)
                n["interact"] = None
            else:
                try:
                    it["rows"] = synth_law_rows(raw_rows, target_expr, seed=hash(nid) & 0xffff)
                except Exception as e:
                    issues.append("%s: law-finder 数值合成失败(%s)，已移除实验" % (nid, e))
                    n["interact"] = None
                    continue
                # 冒烟复验：target_expr 对应的候选必须在所有样本上几乎恒定（变异系数<5%），
                # 且至少要有一个干扰候选不恒定（否则"找规律"这个动作没有意义，随便选都对）
                def _cv(expr, rows):
                    import math
                    vals = []
                    for r in rows:
                        try:
                            v = eval(expr.replace("^", "**"), {"__builtins__": {}}, {"x": r["x"], "y": r["y"], "math": math})
                            if isinstance(v, (int, float)) and math.isfinite(v):
                                vals.append(v)
                        except Exception:
                            pass
                    if len(vals) < len(rows) * 0.8 or not vals:
                        return 999
                    mean = sum(vals) / len(vals)
                    if mean == 0:
                        return 999
                    var = sum((v - mean) ** 2 for v in vals) / len(vals)
                    return (var ** 0.5) / abs(mean)
                target_cvs = [(ci, _cv(c["expr"], it["rows"])) for ci, c in enumerate(cands)]
                correct = [ci for ci, cv in target_cvs if cv < 0.05]
                if not correct:
                    issues.append("%s: 候选公式里没有一个能对合成数据保持恒定，已移除实验" % nid)
                    n["interact"] = None
                    continue
                if len(correct) == len(cands):
                    issues.append("%s: 所有候选都恒定（缺乏干扰项区分度），已移除实验" % nid)
                    n["interact"] = None
                    continue
                issues.append("%s: law-finder 数值已由代码合成并复验（正确候选下标 %s）" % (nid, correct))
        elif t == "custom-lab":
            cfg = it.get("config") or {}
            if not cfg.get("sliders") or not (cfg.get("win") or {}).get("expr"):
                issues.append("%s: custom-lab 配置不全，已降级移除实验" % nid)
                n["interact"] = None
            else:
                # 无意义的装饰性 ops：加了运算按钮但没有任何 expr 真正引用 op，直接删掉字段
                if cfg.get("ops"):
                    exprs_all = [r.get("expr", "") for r in (cfg.get("readouts") or [])]
                    exprs_all += [(cfg.get("big") or {}).get("expr", ""), (cfg.get("win") or {}).get("expr", "")]
                    if not any(re.search(r'\bop\b', e or "") for e in exprs_all):
                        issues.append("%s: custom-lab 的 ops 未被任何表达式引用（装饰性按钮），已移除" % nid)
                        cfg.pop("ops", None)
                # 滑块结构校验
                bad = [sl for sl in cfg["sliders"] if not all(k in sl for k in ("id", "label", "min", "max"))]
                if bad:
                    issues.append("%s: custom-lab 滑块字段缺失，已移除实验" % nid)
                    n["interact"] = None
                else:
                    # JS 保留字/非法标识符检测：滑块 id 会被 new Function(id,...) 当形参名，
                    # 撞上 var/in/class 等保留字会导致语法错误被 catch 吞掉，读数全部 NaN（已实测踩过）
                    JS_RESERVED = {"var","let","const","in","of","class","function","return","new","this",
                                   "if","else","for","while","do","switch","case","break","continue","typeof",
                                   "instanceof","delete","void","yield","await","try","catch","finally","throw",
                                   "with","default","export","import","extends","super","static","null","true","false"}
                    renames = {}
                    for sl in cfg["sliders"]:
                        sid = str(sl["id"])
                        if sid in JS_RESERVED or not re.fullmatch(r'[A-Za-z_$][A-Za-z0-9_$]*', sid):
                            new_id = "v_" + re.sub(r'[^A-Za-z0-9_$]', '', sid) or ("v_%d" % id(sl))
                            renames[sid] = new_id
                    if renames:
                        issues.append("%s: custom-lab 滑块 id 撞 JS 保留字/非法标识符 %s，已重命名" % (nid, renames))
                        for sl in cfg["sliders"]:
                            if sl["id"] in renames:
                                sl["id"] = renames[sl["id"]]
                        # 同步替换所有 expr 里的旧 id（词边界，避免误伤子串）
                        def _sub_ids(expr):
                            for old, new in renames.items():
                                expr = re.sub(r'\b%s\b' % re.escape(old), new, expr)
                            return expr
                        for r in (cfg.get("readouts") or []):
                            r["expr"] = _sub_ids(r["expr"])
                        if cfg.get("big"):
                            cfg["big"]["expr"] = _sub_ids(cfg["big"]["expr"])
                        if cfg.get("win"):
                            cfg["win"]["expr"] = _sub_ids(cfg["win"]["expr"])
                    # 静态复验：expr 是 JS 语法（三元 a?b:c 等），不能用 Python eval 执行；
                    # 改为提取 expr 中的裸标识符，确认全部落在合法 scope 内（滑块 id / op / Math / touched）
                    exprs = [r["expr"] for r in (cfg.get("readouts") or [])]
                    if cfg.get("big"):
                        exprs.append(cfg["big"]["expr"])
                    if cfg.get("win"):
                        exprs.append(cfg["win"]["expr"])
                    known = {sl["id"] for sl in cfg["sliders"]} | {"op", "Math", "touched", "true", "false", "null"}
                    JS_KEYWORDS = {"Math","true","false","null","NaN","Infinity"}
                    bad_exprs = []
                    for e in exprs:
                        # 去掉字符串字面量后再提取标识符，避免字符串内容被误判
                        stripped = re.sub(r'"[^"]*"|\'[^\']*\'', '""', e)
                        idents = set(re.findall(r'\b[A-Za-z_$][A-Za-z0-9_$]*\b', stripped))
                        idents -= JS_KEYWORDS
                        idents = {i for i in idents if not re.fullmatch(
                            r'(pow|max|min|round|floor|ceil|abs|sqrt|log|exp|sin|cos|tan|random|sign|'
                            r'size|has|add|delete|clear|forEach|map|filter|reduce|includes|indexOf|'
                            r'toFixed|toString|toPrecision|toUpperCase|toLowerCase|charAt|slice|split|join|'
                            r'length|values|keys|entries|Array|Set|Object|Number|String|Boolean|parseInt|parseFloat|isNaN)', i)}
                        unknown = idents - known
                        if unknown:
                            bad_exprs.append((e, unknown))
                    if bad_exprs:
                        issues.append("%s: custom-lab 表达式引用未知标识符 %s，已移除实验" % (nid, bad_exprs))
                        n["interact"] = None
        elif t in ("volume-cube", "cone-slice", "ellipse-params"):
            issues.append("%s: 圆锥曲线专用实验 %s 出现在非圆锥主题，已移除" % (nid, t))
            n["interact"] = None
        # 课标诚实性检测（实测踩过：card.textbook 编造"人教A版选修三"这个不存在的册次+精确页码，
        # 与同节点 bridge.textbook 已经诚实标注的"大学先修"自相矛盾）——两处字段独立生成，
        # 之前只检查了 bridge.textbook，card.textbook 是漏检的另一半，必须同时覆盖
        # 2026-08 追加：bridge.mapping[]（每条历史细节→课本概念的映射）和 quiz.explain 也会独立编造
        # 精确页码/例题号（如"课本P84例3"、"练习3"），是比 textbook 更隐蔽的漏检点——因为它们是
        # 数组/嵌套字段，逐节点扫描时容易只看 textbook 就跳过。真实事故：抽象代数篇已在 textbook
        # 诚实标注"大学先修"，但 mapping 里仍写"课本P80'群的四个公理'"这种精确页码，自相矛盾。
        FABRICATED_PAGE = re.compile(r'[PＰ]\d+|定义\d|例\d|练习\d|选修三|选修二|选修一(?!\S)')
        checks = [(("bridge", "textbook"), (n.get("bridge") or {}).get("textbook", "")),
                  (("card", "textbook"), (n.get("card") or {}).get("textbook", ""))]
        for i, m in enumerate((n.get("bridge") or {}).get("mapping") or []):
            checks.append((("bridge", "mapping[%d]" % i), m))
        quiz_explain = ((n.get("bridge") or {}).get("quiz") or {}).get("explain", "")
        if quiz_explain:
            checks.append((("bridge", "quiz.explain"), quiz_explain))
        for field, text in checks:
            if text and FABRICATED_PAGE.search(text) and "拓展" not in text and "先修" not in text:
                issues.append("%s.%s: 疑似编造教材版本/精确页码/例题号「%s」，需人工核实为真实定位" % (nid, field[0]+"."+field[1], text))

        # 知识联结深度检测（用户反馈"花拳绣腿"的真实根因：bridge.mapping 只写箭头短语，
        # 如"'24种排列' → S₄含4!=24个元素"——两个名词被强行画等号，没有推导过程，读起来像贴标签。
        # 不硬造推导内容（需要真实的数学/科学等价关系，代码编不出来），但必须让"写得太薄"的
        # 节点在质检报告里可见，逼着下一轮生成或人工补写时能定位到具体哪一条不合格）
        REASON_WORDS = ("因为", "由于", "本质上", "等价于", "这正是", "换句话说")
        for i, m in enumerate((n.get("bridge") or {}).get("mapping") or []):
            if len(m) < 40 or not any(w in m for w in REASON_WORDS):
                issues.append("%s.bridge.mapping[%d]: 疑似仍是箭头短语而非完整推导句（%d字，缺推导连接词）：「%s」" %
                              (nid, i, len(m), m[:50]))

        # TTS 朗读风险检测（实测踩过：F=Gm₁m₂/r² 被读成乱码，A₅/S₃ 被读丢下标）——
        # 台词含等式(=)+下标变量、或纯符号+下标堆砌时打日志提醒，不做自动改写（语义改写需要人工/LLM二次判断，
        # 硬替换风险更高），但必须让问题在质检报告里可见，不能像之前那样静默漏过被用户听出来
        TTS_RISK = re.compile(r'[A-Za-z][₀-₉]+|[A-Za-z]=[A-Za-z]|[A-Za-z][₀-₉]*[÷/][A-Za-z]')
        for key in ("dialogues", "afterChoice"):
            for d in (n.get(key) or []):
                plain = re.sub(r'<[^>]+>', '', d.get("text", ""))
                if TTS_RISK.search(plain):
                    issues.append("%s.%s[%s]: 台词含等式/下标变量连写，TTS朗读高风险（需口语化改写）: %s" % (nid, key, d.get("who"), plain[:50]))
        for d in (n.get("dialogues") or []):
            if len(d.get("text", "")) > 130:
                issues.append("%s: 台词超长 %d 字" % (nid, len(d["text"])))
        if not n.get("dialogues"):
            issues.append("%s: 缺 dialogues" % nid)
        # 内容深度检测：历史节点（非序章/终章）briefing 太单薄会导致"讲解不够"——
        # 实测发现 LLM 经常只顶 prompt 的下限（1页/2句），必须让这个问题在质检时就可见。
        # 不做自动补写（内容深度需要真实的历史/科学知识，硬凑字数只会制造空洞文本，比不写更差）
        if it or n.get("choice"):  # 用 interact/choice 存在与否粗略判断是否为"正文历史节点"
            briefing_pages = n.get("briefing") or []
            briefing_len = sum(len(re.sub(r'<[^>]+>', '', b.get("text", ""))) for b in briefing_pages)
            dialogue_cnt = len(n.get("dialogues") or [])
            if len(briefing_pages) < 2 or briefing_len < 240:
                issues.append("%s: briefing 内容单薄（%d页/%d字，建议≥2页且≥240字），知识讲解可能不够" % (nid, len(briefing_pages), briefing_len))
            if dialogue_cnt < 4:
                issues.append("%s: dialogues 只有 %d 句（建议4-6句）" % (nid, dialogue_cnt))
    if len(nodes) < 6:
        issues.append("节点数 %d 不足" % len(nodes))
    return issues


def synth_tycho_rows(raw_rows, seed=0):
    """数值合成器：LLM 只给语义标记（每行 date + anomaly true/false），
    具体数值由代码按规则精确构造——保证「1-2 行异常、幅度分明、其余行正常」在数学上必然成立，
    彻底跳过"生成数值→猜阈值→检测→硬修"这条不稳定链路。
    输入：[{date, anomaly}, ...]  输出：[{date, obs, pred, dev}, ...]（引擎可直接渲染）"""
    import random
    rnd = random.Random(seed)
    base = round(rnd.uniform(8, 40), 1)
    rows = []
    for r in raw_rows:
        pred = round(base + rnd.uniform(-2, 2), 1)
        if r.get("anomaly"):
            dev = round(rnd.uniform(5.0, 8.0) * rnd.choice([1, -1]), 1)
        else:
            dev = round(rnd.uniform(0.1, 1.2) * rnd.choice([1, -1]), 1)
        obs = round(pred + dev, 1)
        rows.append({"date": r.get("date", ""), "obs": obs, "pred": pred, "dev": dev})
    return rows


def synth_law_rows(raw_rows, target_expr, seed=0, noise=0.02):
    """规律数值合成器（跨样本找恒定规律场景，如开普勒 T²/a³）：
    LLM 只给真实的 x（如各行星轨道半长轴——这是历史事实，LLM 该负责的部分），
    代码按目标公式 y=f(x) 精确构造 y，加极小真实测量噪声，使正确公式在所有样本上几乎恒定，
    错误候选公式则天然不恒定——不依赖 LLM 去凭空编出满足某种关系的数字。
    raw_rows: [{label, x}]  target_expr: 以 x 为自变量的 JS 表达式字符串（如 "x**1.5"）
    返回: [{label, x, y}]"""
    import random, math
    rnd = random.Random(seed)
    safe_env = {"__builtins__": {}}
    rows = []
    for r in raw_rows:
        x = float(r["x"])
        try:
            y = eval(target_expr.replace("^", "**"), safe_env, {"x": x, "math": math})
        except Exception:
            y = x
        y *= (1 + rnd.uniform(-noise, noise))  # 真实测量噪声，但不足以破坏恒定性
        rows.append({"label": r.get("label", ""), "x": round(x, 4), "y": round(y, 4)})
    return rows


def build_story_js(story):
    nodes = story["nodes"]
    guide = story.get("guide_name") or "向导之灵"
    story_nodes = []
    tycho_rows = None
    for node in nodes:
        nd = dict(node)
        nd["img"] = "assets/%s.png" % node["id"]
        nd.pop("image_prompt", None)
        # who 规范化：LLM 可能把 prompt 占位说明当字面量用
        for key in ("dialogues", "afterChoice"):
            if nd.get(key):
                for dlg in nd[key]:
                    if dlg.get("who") in ("向导名", "角色名", "向导"):
                        dlg["who"] = guide
        if nd.get("interact") and nd["interact"].get("rows") and tycho_rows is None:
            tycho_rows = nd["interact"]["rows"]  # 仅作全局兜底，不再从节点删除
        story_nodes.append(nd)
    # 应用幕：同构转换（img + who 规范化），台词的 audio 字段由 prerender_audio 预先写入、浅拷贝自动保留
    app_nodes = []
    for node in (story.get("app_nodes") or []):
        nd = dict(node)
        nd["img"] = "assets/%s.png" % node["id"]
        nd.pop("image_prompt", None)
        # eraTitle 清理：LLM 偶尔把 prompt 的示例标记"式"字抄进标题尾部
        if (nd.get("eraTitle") or "").endswith("式"):
            nd["eraTitle"] = nd["eraTitle"].rstrip(" 式").rstrip()
        for key in ("dialogues", "afterChoice"):
            if nd.get(key):
                for dlg in nd[key]:
                    if dlg.get("who") in ("向导名", "角色名", "向导"):
                        dlg["who"] = guide
        app_nodes.append(nd)
    max_res = int(story.get("endings_max") or 180)
    endings = [
        {"min": int(max_res*0.83), "rank": "TRUE END", "title": "执 火 者",
         "text": "你没有“学完”它——你和它一起，重新诞生了一次。这条长河，如今有一部分属于你。"},
        {"min": int(max_res*0.58), "rank": "GOOD END", "title": "同 行 者",
         "text": "你见证了它的重生，并在大多数历史关头做出了与伟大心灵相同的选择。仍有一些岔路值得重返。"},
        {"min": 0, "rank": "NORMAL END", "title": "拾 星 者",
         "text": "你走完了整条长河，捡起了一些星光。知识之境没有时间的尽头——随时回来。"},
    ]
    data = {
        "META": {"title": story.get("title", ""), "subtitle": story.get("subtitle", ""),
                 "guide_name": guide, "cast": story.get("cast", {})},
        "STORY": story_nodes,
        "APP_STORY": app_nodes,
        "RIVER": story.get("river", []),
        "RIVER_BOOK": story.get("river_book", ""),
        "RIVER_APPS": story.get("river_apps", []),
        "RIVER_QUOTE": story.get("river_quote", ""),
        "RIVER_QUOTE_AUDIO": story.get("river_quote_audio", ""),
        "TYCHO_DATA": tycho_rows or [],
        "ENDINGS": endings,
    }
    return ("/* 知识之境 · 篇章数据（由工厂生成） */\nwindow.STORY_DATA = "
            + json.dumps(data, ensure_ascii=False, indent=1) + ";\n")


def run_generate(job_id, topic, audience):
    try:
        JOBS[job_id] = {"stage": "story", "message": "正在从教材索引召回「%s」的课内知识点……" % topic}
        textbook_kb = extract_textbook_knowledge(topic, audience)
        JOBS[job_id] = {"stage": "story", "message": "正在通过 Tavily 检索「%s」的真实史料与课标……" % topic}
        research = research_topic(topic, audience)
        JOBS[job_id]["message"] = "素材到手（教材知识点 %d 字 + 史料 %d 字），正在撰写剧本……（约 2-3 分钟）" % (len(textbook_kb), len(research))
        story = gen_story(topic, audience, research, textbook_kb)
        # 生成后自动质检：快速过一遍材料，能修的自动修
        issues = validate_story(story)
        if issues:
            print("[validate]", "; ".join(issues))
        JOBS[job_id]["message"] = "剧本质检完成（%s）。" % ("通过" if not issues else "%d 项已自动修正" % len(issues))
        slug = slugify(story.get("slug") or topic)
        out_dir = ROOT / "chapters" / slug
        nodes = all_speech_nodes(story)
        n = len(nodes)

        (out_dir / "assets").mkdir(parents=True, exist_ok=True)
        fallback_ids = ["prologue", "menaechmus", "apollonius", "kepler", "descartes", "newton", "modern", "finale"]
        for i, node in enumerate(nodes):
            JOBS[job_id].update(stage="images", slug=slug,
                                message="剧本完成（%d 节点）。正在生成场景 CG（%d/%d）……" % (n, i+1, n))
            # 序章/终章强制使用向导形象描述（画风一致 + 避免文字出戏）
            is_guide_scene = node["id"] in ("prologue", "epilogue", "finale") or i in (0, n-1)
            if is_guide_scene:
                prompt = GUIDE_PROMPT_HINT + ", " + (node.get("image_prompt") or "") + STYLE_SUFFIX
            else:
                prompt = (node.get("image_prompt") or ("scene of " + node.get("eraTitle", ""))) + STYLE_SUFFIX
            try:
                img = call_image(prompt)
                (out_dir / "assets" / ("%s.png" % node["id"])).write_bytes(img)
            except Exception:
                fb = ROOT / "assets" / (fallback_ids[min(i, 7)] + ".png")
                if fb.exists():
                    (out_dir / "assets" / ("%s.png" % node["id"])).write_bytes(fb.read_bytes())

        JOBS[job_id].update(stage="assemble", message="场景完成，正在装配篇章……")
        # 预渲染固定台词配音（dialogues / afterChoice / 收束引言），播放时零等待
        if CFG["DASHSCOPE_API_KEY"]:
            JOBS[job_id]["message"] = "正在预渲染台词配音……"
            try:
                prerender_audio(story, out_dir)
            except Exception as e:
                print("[tts-prerender] 预渲染整体失败，回退实时配音：%s" % e)
        (out_dir / "story.js").write_text(build_story_js(story), encoding="utf-8")
        # 引擎模板：用圆锥曲线篇的播放器（注意：根目录 index.html 已是门户页，不能用作模板）
        engine = (ROOT / "chapters" / "conic-sections" / "index.html").read_text(encoding="utf-8")
        # 封面：game-chapter 显示篇章主标题，其下插入副标题行
        chap_title = story.get("title") or topic
        chap_sub = story.get("subtitle") or ""
        engine = engine.replace("圆锥曲线 · 两千三百年的六次重生", chap_title)
        if chap_sub and chap_sub != chap_title:
            engine = engine.replace(
                '<div class="game-feats">',
                '<div style="font-size:14px;color:var(--text-dim);letter-spacing:.2em;margin-bottom:26px;">'
                + chap_sub + '</div>\n    <div class="game-feats">', 1)
        engine = engine.replace("live_science_conic_v3", "live_science_%s_v1" % slug)
        engine = engine.replace("<title>知识之境 · 圆锥曲线 —— 两千三百年的六次重生</title>",
                                "<title>知识之境 · %s</title>" % chap_title)
        if "/example-auth.js" not in engine:
            engine = engine.replace("<head>", '<head><script src="/example-auth.js"></script>', 1)
        (out_dir / "index.html").write_text(engine, encoding="utf-8")
        (out_dir / "README.md").write_text(
            "# 知识之境 · %s\n\n由篇章工厂生成（topic: %s, audience: %s）。\n\n"
            "运行：圆锥曲线篇目录 `python3 server.py` 后访问 /chapters/%s/\n"
            % (story.get("title") or topic, topic, audience, slug),
            encoding="utf-8")
        # 自动同步到前端产物（新篇章无需手动 build 即可在 WeSmartFlow 直接访问）
        try:
            public_chapter = ROOT.parent.parent / "frontend" / "public" / "live-science" / "chapters" / slug
            if public_chapter.exists():
                shutil.rmtree(public_chapter)
            shutil.copytree(out_dir, public_chapter)
            # 同步集中音频资产（assets/audio/<slug> → public/live-science/assets/audio/<slug>）
            src_audio = ROOT / "assets" / "audio" / slug
            public_audio = ROOT.parent.parent / "frontend" / "public" / "live-science" / "assets" / "audio" / slug
            if src_audio.exists():
                if public_audio.exists():
                    shutil.rmtree(public_audio)
                shutil.copytree(src_audio, public_audio)
            print("[sync] 已同步到前端产物 chapters/%s/ + assets/audio/%s/" % (slug, slug))
        except Exception as e:
            print("[sync] 同步到前端产物失败（可手动 build 兜底）: %s" % e)
        JOBS[job_id].update(stage="done", slug=slug,
                            message="篇章「%s」生成完成！" % (story.get("title") or topic))
    except Exception as e:
        JOBS[job_id].update(stage="error", message=str(e))


def tts_normalize(text):
    """TTS 朗读前的数学符号口语化：把 Unicode 下标/上标/公式符号替换成可读文本，
    避免 DashScope 把 a₁、Sₙ 这类下标读成乱码或吞掉。"""
    if not text:
        return text
    sub_digits = "₀₁₂₃₄₅₆₇₈₉"
    cn_digits = "零一二三四五六七八九"
    sub_val = {ch: i for i, ch in enumerate(sub_digits)}

    def _cn_num(n):
        if n < 10:
            return cn_digits[n]
        if n < 100:
            tens, ones = divmod(n, 10)
            return ("" if tens == 1 else cn_digits[tens]) + "十" + (cn_digits[ones] if ones else "")
        return str(n)

    def _cn_full(n):
        """整数转中文读法（支持到亿级），用于多位阿拉伯数字的 TTS 口语化。"""
        if n == 0:
            return "零"
        units = ["", "万", "亿"]
        def four(x):  # 0-9999 段内读法
            if x == 0:
                return ""
            parts = []
            q, b, s, g = x // 1000, x // 100 % 10, x // 10 % 10, x % 10
            if q:
                parts.append(cn_digits[q] + "千")
            if b:
                parts.append(cn_digits[b] + "百")
            elif q and (s or g):
                parts.append("零")
            if s:
                parts.append(cn_digits[s] + "十")
            elif b and g:
                parts.append("零")
            if g:
                parts.append(cn_digits[g])
            return "".join(parts)
        parts, idx = [], 0
        while n > 0:
            seg = n % 10000
            if seg:
                parts.append(four(seg) + units[idx])
            n //= 10000
            idx += 1
        out = "".join(reversed(parts))
        return out.replace("二万", "两万", 1) if out.startswith("二万") else out

    # 连续下标数字 → 中文数字读法（a₃₀→a三十，a₁₀→a十，a₁→a一）
    text = re.sub("[" + sub_digits + "]+",
                  lambda m: _cn_num(int("".join(str(sub_val[c]) for c in m.group()))), text)
    # 多位阿拉伯数字（≥4位）→ 中文读法（27845→两万七千八百四十五），避免 TTS 逐位读
    text = re.sub(r"\d{4,}", lambda m: _cn_full(int(m.group())), text)
    # 下标字母 → 空格+字母（aₙ→a n，避免拼成英文单词 an 被误读）
    for u, c in {"ₙ": "n", "ₖ": "k", "ₘ": "m", "ₓ": "x", "ᵢ": "i", "ⱼ": "j"}.items():
        text = text.replace(u, " " + c)
    # 连续上标数字（≥2个）→ "的N次方"（10²⁴→10的24次方），先于单字符上标处理
    sup_digits = "⁰¹²³⁴⁵⁶⁷⁸⁹"
    sup_val = {ch: i for i, ch in enumerate(sup_digits)}
    text = re.sub("[" + sup_digits + "]{2,}",
                  lambda m: "的" + str(int("".join(str(sup_val[c]) for c in m.group()))) + "次方", text)
    # 上标次方 → 口语化
    for u, c in {"²": "的平方", "³": "的立方", "⁴": "的四次方", "⁵": "的五次方", "⁶": "的六次方"}.items():
        text = text.replace(u, c)
    # 运算符号 → 口语化（含 Unicode 减号 U+2212、全角等号）
    text = (text.replace("×", "乘").replace("÷", "除以")
            .replace("−", "减").replace("－", "减").replace("-", "减")
            .replace("＝", "等于").replace("=", "等于")
            .replace("+", "加")
            .replace("/", "除以"))
    return text


def call_tts_dashscope(voice, text, instruct, timeout=90):
    """DashScope qwen3-tts-instruct-flash（纯 HTTP，零依赖）：返回 (音频二进制, content-type)
    voice: Cherry/Serena/Vivian/Bella/Stella/Momo/Maia/Chelsie/Ethan/Nofish
    instruct: 自然语言语气指令（如"空灵缓慢的女声"），是本模型的核心能力
    """
    text = tts_normalize(text)
    model = CFG["TTS_MODEL"] or "qwen3-tts-instruct-flash"
    before_raw("audio", model=model, provider="qwen")
    key = CFG["DASHSCOPE_API_KEY"] or os.environ.get("DASHSCOPE_API_KEY", "")
    if not key:
        raise RuntimeError("DASHSCOPE_API_KEY 未配置")
    payload = json.dumps({
        "model": CFG["TTS_MODEL"] or "qwen3-tts-instruct-flash",
        "input": {"text": text, "voice": voice or "Cherry", "instructions": instruct or ""},
        "parameters": {"optimize_instructions": True},
    }).encode("utf-8")
    req = urllib.request.Request(
        DASHSCOPE_GEN_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    url = (data.get("output") or {}).get("audio", {}).get("url")
    if not url:
        raise RuntimeError(f"dashscope 无音频返回: {json.dumps(data, ensure_ascii=False)[:300]}")
    record_raw("audio", model=model, provider="qwen", units=(data.get("usage") or {}).get("characters", len(text)))
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return r.read(), "audio/wav"


# ================= 配音预渲染 =================
# 复现前端 Voice.registerMeta() 的音色分配：预置 profiles + 按 META.cast 性别从男女音色池轮转。
# 预渲染必须和前端用完全相同的音色映射，否则生成时合成的声音与实时不一致。

PRESET_PROFILES = {
    "旁白": {"tvoice": "Serena", "instruct": "平静温柔的旁白女声，娓娓道来的讲述感"},
    "你": {"tvoice": "Ethan", "instruct": "年轻学生的声音，好奇、轻声"},
    "？？？": {"tvoice": "Chelsie", "instruct": "空灵、缓慢的女声，像在星空中低语，带轻微回响感"},
    # 圆锥曲线篇（出厂预装）手工预置的科学家声线，复刻前端 profiles 保证音色一致
    "曲线之灵": {"tvoice": "Chelsie", "instruct": "空灵、缓慢的女声，像在星空中低语，带轻微回响感"},
    "梅内克缪斯": {"tvoice": "Ethan", "instruct": "年轻学者，急切而兴奋，语速偏快"},
    "阿波罗尼奥斯": {"tvoice": "Nofish", "instruct": "沉稳自信的中年学者男声，从容不迫"},
    "开普勒": {"tvoice": "Nofish", "instruct": "中年男声，疲惫而执着，略带沙哑，偶尔激动"},
    "笛卡尔": {"tvoice": "Nofish", "instruct": "从容慵懒的中年男声，循循善诱"},
    "牛顿": {"tvoice": "Ethan", "instruct": "冷峻的年轻男声，语速略快，防御性中藏着热切"},
}
GUIDE_PROFILE = {"tvoice": "Chelsie", "instruct": "空灵、缓慢的女声，像在星空中低语，带轻微回响感"}

POOL_MALE = [
    {"tvoice": "Eldric Sage", "instruct": "沉稳睿智的老者男声，沧桑如松却心明如镜，语速缓慢字字有力"},
    {"tvoice": "Ethan", "instruct": "标准普通话年轻男声，阳光温暖，充满朝气与冲劲"},
    {"tvoice": "Nofish", "instruct": "从容自信的中年男声，循循善诱，带点狡黠"},
    {"tvoice": "Mochi", "instruct": "聪明伶俐的年轻男声，语速偏快，带一点少年早慧的锐气"},
    {"tvoice": "Vincent", "instruct": "带沙哑烟嗓质感的男声，苍劲豪情，字字有重量"},
    {"tvoice": "Arthur", "instruct": "被岁月浸泡过的质朴男声，不疾不徐，带乡野智者的从容"},
    {"tvoice": "Kai", "instruct": "温润舒缓的男声，如耳畔SPA般平和亲切"},
    {"tvoice": "Moon", "instruct": "率性帅气的男声，洒脱不羁又带一丝孤傲"},
    {"tvoice": "Neil", "instruct": "平直基线语调，字正腔圆，专业播报感"},
]
POOL_FEMALE = [
    {"tvoice": "Serena", "instruct": "温柔成熟的女性学者声，清晰理性，不疾不徐"},
    {"tvoice": "Bella", "instruct": "干脆利落带点小暴躁的女声，倔强直接"},
    {"tvoice": "Vivian", "instruct": "温和成熟女声，带学者的耐心与韧性"},
    {"tvoice": "Maia", "instruct": "知性与温柔碰撞的女声，沉静而有分量"},
    {"tvoice": "Chelsie", "instruct": "清亮灵动的年轻女声，好奇又专注"},
    {"tvoice": "Katerina", "instruct": "御姐气质女声，韵律沉稳，回味十足"},
    {"tvoice": "Momo", "instruct": "撒娇搞怪略带调皮的女声，鲜活跳脱"},
    {"tvoice": "Cherry", "instruct": "阳光积极亲切自然的女声，稳重可靠"},
]

# 年龄段音色子集：cast 标注 -old/-young 时从这里选（图年长的人物不再配年轻音）
POOL_MALE_ELDER = [
    {"tvoice": "Eldric Sage", "instruct": "沉稳睿智的老者男声，沧桑如松却心明如镜，语速缓慢字字有力"},
    {"tvoice": "Vincent", "instruct": "带沙哑烟嗓质感的男声，苍劲豪情，字字有重量"},
    {"tvoice": "Arthur", "instruct": "被岁月浸泡过的质朴男声，不疾不徐，带乡野智者的从容"},
]
POOL_MALE_YOUNG = [
    {"tvoice": "Ethan", "instruct": "标准普通话年轻男声，阳光温暖，充满朝气与冲劲"},
    {"tvoice": "Mochi", "instruct": "聪明伶俐的年轻男声，语速偏快，带一点少年早慧的锐气"},
]
POOL_FEMALE_ELDER = [
    {"tvoice": "Serena", "instruct": "温柔成熟的女性学者声，清晰理性，不疾不徐"},
    {"tvoice": "Katerina", "instruct": "御姐气质女声，韵律沉稳，回味十足"},
    {"tvoice": "Vivian", "instruct": "温和成熟女声，带学者的耐心与韧性"},
]
POOL_FEMALE_YOUNG = [
    {"tvoice": "Bella", "instruct": "干脆利落带点小暴躁的女声，倔强直接"},
    {"tvoice": "Chelsie", "instruct": "清亮灵动的年轻女声，好奇又专注"},
    {"tvoice": "Momo", "instruct": "撒娇搞怪略带调皮的女声，鲜活跳脱"},
]


def resolve_voice_profiles(story):
    """复现前端 registerMeta 的音色分配（含年龄段解析），返回 {角色名: {tvoice, instruct}}。
    cast 值支持 m / f / m-old / m-young / f-old / f-young——与前端保持完全一致的分配顺序。"""
    guide_name = story.get("guide_name", "")
    cast = story.get("cast", {}) or {}
    profiles = dict(PRESET_PROFILES)
    if guide_name:
        profiles[guide_name] = dict(GUIDE_PROFILE)
    seen = set()
    for n in all_speech_nodes(story):
        for key in ("dialogues", "afterChoice"):
            for d in n.get(key) or []:
                who = d.get("who", "")
                if who and who not in ("旁白", "你", "？？？") and who != guide_name:
                    seen.add(who)
    counters = {}
    for name in sorted(seen):
        if name in profiles:
            continue
        raw = str(cast.get(name, "m"))
        is_f = raw.startswith("f")
        age = "old" if raw.endswith("old") else ("young" if raw.endswith("young") else "")
        if age == "old":
            pool = POOL_FEMALE_ELDER if is_f else POOL_MALE_ELDER
            key = ("f" if is_f else "m") + "-old"
        elif age == "young":
            pool = POOL_FEMALE_YOUNG if is_f else POOL_MALE_YOUNG
            key = ("f" if is_f else "m") + "-young"
        else:
            pool = POOL_FEMALE if is_f else POOL_MALE
            key = "f" if is_f else "m"
        i = counters.get(key, 0)
        profiles[name] = dict(pool[i % len(pool)])
        counters[key] = i + 1
    return profiles


def prerender_audio(story, out_dir):
    """批量预渲染固定台词配音（dialogues / afterChoice / river_quote）。

    音频集中存 assets/audio/<slug>/*.wav（不入 git），
    并给每个台词对象加 audio 字段（相对篇章页面的 ../../assets/audio/<slug>/xxx.wav）。
    逐句容错：单句合成失败只跳过该句，不阻断生成。
    """
    profiles = resolve_voice_profiles(story)
    guide_name = story.get("guide_name", "")
    slug = out_dir.name
    audio_rel = f"../../assets/audio/{slug}"  # 前端相对 chapters/<slug>/index.html 的路径
    audio_dir = ROOT / "assets" / "audio" / slug
    audio_dir.mkdir(parents=True, exist_ok=True)
    count = 0

    def synth(profile, text):
        text = re.sub(r"<[^>]+>", "", text or "").strip()
        if not text:
            return None
        try:
            audio, _ = call_tts_dashscope(profile["tvoice"], text, profile["instruct"])
            return audio
        except Exception as e:
            print("[tts-prerender] 失败(%s): %s" % (e, text[:30]))
            return None

    for n in all_speech_nodes(story):
        nid = n.get("id", "node")
        for key, prefix in (("dialogues", "dlg"), ("afterChoice", "after")):
            for i, d in enumerate(n.get(key) or []):
                who = d.get("who", "")
                profile = profiles.get(who) or profiles.get("旁白") or {"tvoice": "Cherry", "instruct": ""}
                audio = synth(profile, d.get("text", ""))
                if audio is None:
                    continue
                fname = "%s_%s_%d.wav" % (nid, prefix, i)
                (audio_dir / fname).write_bytes(audio)
                d["audio"] = audio_rel + "/" + fname
                count += 1
        # choice 选项回应（opt.r 播放时配音，who 取该节点首个非旁白/你/向导的科学家）
        speaker = next((d["who"] for d in (n.get("dialogues") or []) if d.get("who") not in ("旁白", "你", guide_name)), None)
        for i, opt in enumerate((n.get("choice") or {}).get("options") or []):
            r = opt.get("r") or ""
            if not r:
                continue
            profile = profiles.get(speaker) or profiles.get("旁白") or {"tvoice": "Cherry", "instruct": ""}
            audio = synth(profile, r)
            if audio is None:
                continue
            fname = "%s_opt_%d.wav" % (nid, i)
            (audio_dir / fname).write_bytes(audio)
            opt["audio"] = audio_rel + "/" + fname
            count += 1
        # freetalk 预设答案是固定文本，也预渲染；用户手打问题仍实时 TTS
        for i, preset in enumerate((n.get("freetalk") or {}).get("presets") or []):
            answer = preset.get("a") or ""
            if not answer:
                continue
            profile = profiles.get(speaker) or profiles.get("旁白") or {"tvoice": "Cherry", "instruct": ""}
            audio = synth(profile, answer)
            if audio is None:
                continue
            fname = "%s_preset_%d.wav" % (nid, i)
            (audio_dir / fname).write_bytes(audio)
            preset["audio"] = audio_rel + "/" + fname
            count += 1

    quote = story.get("river_quote", "")
    if quote:
        profile = profiles.get(guide_name) or profiles.get("旁白")
        audio = synth(profile, quote)
        if audio is not None:
            (audio_dir / "river_quote.wav").write_bytes(audio)
            story["river_quote_audio"] = audio_rel + "/river_quote.wav"
            count += 1

    print("[tts-prerender] 完成 %d 段配音" % count)
    return count


def call_tts(voice, text, speed, timeout=90):
    """调用 OpenAI 兼容 TTS，返回音频二进制"""
    model = CFG["TTS_MODEL"] or "tts-1"
    before_raw("audio", model=model, provider="openai")
    base = CFG["TTS_BASE_URL"].rstrip("/")
    url = f"{base}/audio/speech"
    payload = json.dumps({
        "model": CFG["TTS_MODEL"] or "tts-1",
        "voice": voice or (CFG["TTS_VOICE"] or "nova"),
        "input": text,
        "speed": speed,
    }).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {CFG['TTS_API_KEY'] or CFG['LLM_API_KEY']}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        audio = resp.read()
        record_raw("audio", model=model, provider="openai", units=len(text))
        return audio, resp.headers.get("Content-Type", "audio/mpeg")


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def _cors(self):
        # 只回显白名单内的来源；同源访问不需要 CORS 头。
        origin = self.headers.get("Origin", "")
        if origin in ALLOWED_ORIGINS:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")

    def end_headers(self):
        # 禁用缓存：改完前端代码刷新即生效
        self.send_header("Cache-Control", "no-store, must-revalidate")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        if self.path == "/api/health":
            out = json.dumps({
                "ok": True,
                "llm": bool(CFG["LLM_API_KEY"] and CFG["LLM_BASE_URL"] and CFG["LLM_MODEL"]),
                "tts": bool(CFG["DASHSCOPE_API_KEY"] or CFG["TTS_BASE_URL"]),
                "tts_backend": "dashscope" if CFG["DASHSCOPE_API_KEY"] else ("openai" if CFG["TTS_BASE_URL"] else "browser"),
                "image": bool(CFG["IMG_API_KEY"] or CFG["DASHSCOPE_API_KEY"]),
                "model": CFG["LLM_MODEL"],
            }).encode("utf-8")
            self.send_response(200)
            self._cors()
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(out)))
            self.end_headers()
            self.wfile.write(out)
            return
        if self.path.startswith("/api/generate/status"):
            from urllib.parse import urlparse, parse_qs
            job = parse_qs(urlparse(self.path).query).get("job", [""])[0]
            st = JOBS.get(job) or {"stage": "unknown", "message": "任务不存在"}
            out = json.dumps(st, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self._cors()
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(out)))
            self.end_headers()
            self.wfile.write(out)
            return
        if self.path == "/api/chapters":
            chapters = []
            ch_dir = ROOT / "chapters"
            if ch_dir.is_dir():
                for d in sorted(ch_dir.iterdir()):
                    if not d.is_dir() or not (d / "index.html").exists():
                        continue
                    meta = {"slug": d.name, "title": d.name, "subtitle": "", "cover": "prologue.png"}
                    sj = d / "story.js"
                    if sj.exists():
                        try:
                            # 之前用正则 r'"META"\s*:\s*(\{[^{}]*\})' 提取 META，META 内嵌套了 cast 对象
                            # （cast 自己也是 {}），正则的 [^{}]* 遇到嵌套花括号直接匹配失败、静默 catch 掉，
                            # 导致 title 一直是默认值 d.name（英文 slug）——门户卡片显示英文正是这个 bug。
                            # 改用真正的 JSON 解析（和 validate_story/sync_engine 等处一致的写法）。
                            txt = sj.read_text(encoding="utf-8")
                            full = json.loads(txt[txt.index("{", txt.index("=")):txt.rstrip().rstrip(";").rindex("}") + 1])
                            m2 = full.get("META") or {}
                            if m2:
                                meta.update(m2)
                        except Exception:
                            pass
                    assets = d / "assets"
                    if assets.is_dir() and not (assets / meta["cover"]).exists():
                        imgs = sorted(p.name for p in assets.glob("*.png"))
                        if imgs:
                            meta["cover"] = imgs[0]
                    meta["badge"] = "AI 生成"
                    chapters.append(meta)
            out = json.dumps({"ok": True, "chapters": chapters}, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self._cors()
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(out)))
            self.end_headers()
            self.wfile.write(out)
            return
        # /chapters/<slug>/... → 服务 ROOT/chapters/<slug>/ 目录（生成的新篇章）
        if self.path.startswith("/chapters/"):
            rel = self.path[len("/chapters/"):]
            slug = rel.split("/")[0].split("?")[0]
            sub = rel[len(slug):].split("?")[0]
            if sub in ("", "/"):
                sub = "/index.html"
            if re.fullmatch(r'[a-z0-9-]+', slug):
                base = (ROOT / "chapters" / slug).resolve()
                target = (base / sub.lstrip("/")).resolve()
                if str(target).startswith(str(base)) and target.is_file():
                    import mimetypes
                    ctype = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
                    data = target.read_bytes()
                    self.send_response(200)
                    self._cors()
                    if ctype.startswith(("text", "application/javascript")):
                        ctype += "; charset=utf-8"
                    self.send_header("Content-Type", ctype)
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                    return
            self.send_error(404)
            return
        super().do_GET()

    def do_POST(self):
        from dependencies import decode_access_token
        try:
            auth = self.headers.get("Authorization", "")
            user_id = decode_access_token(auth.removeprefix("Bearer "))
        except Exception:
            self.send_error(401, "Authentication required")
            return
        with usage_scope(user_id, "live-science"):
            self._do_POST()

    def _do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        try:
            body = json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception:
            body = {}

        if self.path == "/api/generate":
            try:
                topic = (body.get("topic") or "").strip()
                audience = (body.get("audience") or "high").strip()
                if not topic:
                    raise ValueError("missing topic")
                if not (CFG["LLM_API_KEY"] and CFG["LLM_BASE_URL"]):
                    raise RuntimeError("LLM 未配置，无法生成")
                import uuid
                job_id = uuid.uuid4().hex[:8]
                JOBS[job_id] = {"stage": "queued", "message": "排队中……"}
                UsageThread(target=run_generate, args=(job_id, topic, audience), daemon=True).start()
                self._json_ok({"ok": True, "job": job_id})
            except Exception as e:
                self._json_ok({"ok": False, "error": str(e)})
            return

        if self.path == "/api/llm":
            try:
                messages = body.get("messages")
                if not messages:
                    raise ValueError("missing messages")
                text = call_llm(messages)
                self._json_ok({"ok": True, "text": text})
            except Exception as e:  # 代理失败统一回 200 + ok:false，前端降级
                self._json_ok({"ok": False, "error": str(e)})
            return

        if self.path == "/api/tts":
            try:
                text = (body.get("input") or "")[:600]
                voice = body.get("voice", "")
                instruct = body.get("instruct") or ""
                if CFG["DASHSCOPE_API_KEY"]:
                    audio, ctype = call_tts_dashscope(voice, text, instruct)
                elif CFG["TTS_BASE_URL"]:
                    audio, ctype = call_tts(voice, text, body.get("speed") or 1.0)
                else:
                    raise RuntimeError("TTS 未配置（.env 缺少 DASHSCOPE_API_KEY 或 TTS_BASE_URL）")
                self.send_response(200)
                self._cors()
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(audio)))
                self.end_headers()
                self.wfile.write(audio)
            except Exception as e:
                self._json_ok({"ok": False, "error": str(e)})
            return

        self.send_error(404)

    def _json_ok(self, obj):
        out = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self._cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def log_message(self, fmt, *args):
        if args and isinstance(args[0], str) and "/api/" in args[0]:
            print(f"[api] {fmt % args}")
        else:
            super().log_message(fmt, *args)


if __name__ == "__main__":
    print(f"知识之境 server → http://{HOST}:{PORT}")
    print(f"  .env: {ENV_PATH} ({'found' if ENV_PATH.exists() else 'NOT FOUND'})")
    print(f"  LLM:  {CFG['LLM_MODEL'] or '?'} @ {CFG['LLM_BASE_URL'] or '?'} key={'yes' if CFG['LLM_API_KEY'] else 'NO'}")
    tts_desc = "dashscope qwen3-tts-instruct-flash" if bool(CFG["DASHSCOPE_API_KEY"]) else (CFG["TTS_BASE_URL"] or "not configured (fallback: browser voice)")
    print(f"  TTS:  {tts_desc}")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
