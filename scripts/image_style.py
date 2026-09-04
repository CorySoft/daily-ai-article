import re

from PIL import Image

NO_TEXT = (
    "Wordless artwork only: absolutely no text, letters, numbers, UI, logos, "
    "watermarks, captions, badges, screenshots, or readable screens."
)

_SLOT_LOOK = [
    "deep navy and cyan, cool rim light, quiet negative space",
    "teal glass and warm amber, soft volumetric glow",
    "violet dusk and silver highlights, cinematic depth",
]

_MOTIFS = [
    (r"内存|memory|stream|流式|pipeline|管道",
     "molten data flowing through translucent cooling pipes, overheating core turning calm"),
    (r"降价|价格|cost|cache|缓存",
     "a descending ribbon of light settling onto balanced scales in a dark hall"),
    (r"rust|polars|高性能|数据处理",
     "copper-orange industrial lattice forging streams of structured light"),
    (r"java|jvm",
     "warm amber gears interlocking over a coffee-dark workshop, no logos"),
    (r"开源|open.?source|github|仓库",
     "a constellation of luminous nodes sharing orbits in deep space"),
    (r"模型|llm|大模型|agent",
     "a vast neural cathedral of glass filaments and slow-moving light"),
    (r"安全|隐私|safeguard",
     "a sealed crystalline vault under cool moonlight, inner glow contained"),
]


def visual_motif(topic, extra=""):
    blob = f"{topic} {extra}".lower()
    for pattern, motif in _MOTIFS:
        if re.search(pattern, blob, re.I):
            return motif
    return "abstract editorial metaphor of technology as architecture, light, and material"


def sanitize_scene(desc):
    text = (desc or "").replace("配图描述：", "").strip()
    text = re.sub(
        r"(截图|screenshot|界面|页面|仓库页面|徽章|badge|按钮|star\s*按钮|mermaid|目录结构)",
        "symbolic object",
        text,
        flags=re.I,
    )
    text = re.sub(r"GitHub\s*", "", text, flags=re.I)
    text = re.sub(r"(代码编辑器|IDE|编辑器界面)", "a desk with ambient monitor glow and no readable glyphs", text)
    text = re.sub(r"(左右对比图|左右对比|对比图)", "a diptych of two material metaphors facing each other", text)
    text = re.sub(r"(流程图|架构图)", "an isometric glowing pipeline of glass and metal", text)
    text = re.sub(
        r"(终端|命令行|console|terminal|shell|cmd)",
        "a glowing surface with no readable glyphs",
        text,
        flags=re.I,
    )
    text = re.sub(
        r"(代码|源码|source code|snippet|代码片段)",
        "layers of translucent structured material",
        text,
        flags=re.I,
    )
    text = re.sub(
        r"(表格|table|dashboard|仪表盘|统计图|chart|图表)",
        "an abstract lattice of glowing nodes and bars",
        text,
        flags=re.I,
    )
    if re.search(r"文字|字母|数字|logo|水印", text, re.I):
        text = "wordless material metaphor of the same idea, objects and light only"
    if len(text) < 15:
        text = "quiet conceptual still life of technology as light and structure"
    return text


def cover_prompt(topic, angle="", language="", kind="daily"):
    motif = visual_motif(topic, f"{angle} {language}")
    subject = (
        "WeChat banner for an open-source project feature"
        if kind == "git"
        else "WeChat banner for a daily technology essay"
    )
    lang = f"Material hint from {language}: color and texture only. " if language else ""
    prompt = (
        f"{NO_TEXT} {subject}. "
        f"Theme: {topic}. {lang}"
        f"Depict: {motif}. "
        "Wide cinematic 2.35:1 landscape, single focal object, dark atmospheric background, "
        "editorial concept art, photoreal materials with subtle sci-fi lighting, "
        "no collage, no infographic, no people faces close-up."
    )
    return prompt[:500]


def article_prompt(desc, topic, index=0):
    scene = sanitize_scene(desc)
    motif = visual_motif(topic, scene)
    look = _SLOT_LOOK[index % len(_SLOT_LOOK)]
    prompt = (
        f"{NO_TEXT} Editorial illustration for a Chinese tech essay about {topic}. "
        f"Scene: {scene}. Echo the motif: {motif}. "
        f"Palette and light: {look}. "
        "16:9, one clear subject, generous negative space, magazine quality, "
        "no diagram, no screenshot, no UI chrome."
    )
    return prompt[:500]


def fit_crop(img, width, height):
    img = img.convert("RGB")
    src_w, src_h = img.size
    if src_w == 0 or src_h == 0:
        return img.resize((width, height), Image.LANCZOS)
    width = max(1, width)
    height = max(1, height)
    target = width / height
    current = src_w / src_h
    if current > target:
        new_w = max(1, int(src_h * target))
        left = (src_w - new_w) // 2
        img = img.crop((left, 0, left + new_w, src_h))
    elif current < target:
        new_h = max(1, int(src_w / target))
        top = (src_h - new_h) // 2
        img = img.crop((0, top, src_w, top + new_h))
    return img.resize((width, height), Image.LANCZOS)
