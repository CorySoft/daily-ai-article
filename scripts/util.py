import glob
import json
import re


# 全文验收阈值：write.py / git_write.py / report.py 共用，避免口径漂移
# 两档语义：TARGET 是提示词向模型要的区间，ACCEPT 是闸门。ACCEPT 比 TARGET 宽，
# 但下限不能像老版本 1800 那样宽到把「短一截」也放行 —— 语料里 5 篇不足 2000 字
# 全程绿灯，读者只会觉得今天这篇没写透。
ACCEPT_WORD_MIN = 2200
ACCEPT_WORD_MAX = 3400
TARGET_WORD_MIN = 2400
TARGET_WORD_MAX = 3200


def word_count(md):
    body = "\n".join(l for l in md.splitlines() if not l.lstrip().startswith("#"))
    return len(re.sub(r"\s", "", body))


_TRAILING_PUNCT = ("。", "！", "？", "。”", "！”", "？”", "》", "）", ".")

# 文末引用行：write.py 注入的「> 参考来源：…」与模型自己写的「（来源：…）」「Sources: …」
_CITATION_TAIL = re.compile(
    r"^(?:>)?\s*[（(]?\s*(参考来源|资料来源|参考资料|来源|引用|Sources?|References?|Refs?)\s*[:：]",
    re.IGNORECASE)
# 开源精选结尾的「🔗 GitHub: https://…」（历史格式，保留）
_LINK_TAIL = re.compile(r"^(?:>\s*)?(?:🔗\s*)?(\bGitHub\b|链接|网址)?\s*[:：]?\s*https?://\S+")


def _is_pure_link_line(line):
    """去掉所有 URL 与分隔符后几乎不剩文字的行 —— 视为引用行，不参与截断判定。"""
    if "http" not in line:
        return False
    rest = re.sub(r"https?://\S+", "", line)
    rest = re.sub(r"[\s>＞·、,，。；;:：/|（）()\[\]【】*-]", "", rest)
    return len(rest) <= 8


def is_complete(text):
    """True if the article was not truncated by max_tokens.
    A complete essay ends with sentence punctuation and has >=3 ## sections.
    Trailing citation lines (参考来源 / 纯链接行 / 🔗 GitHub) are stripped first,
    because write.py appends them *after* generation and they never end in punctuation.
    """
    lines = text.rstrip().splitlines()
    while lines:
        last = lines[-1].strip()
        core = re.sub(r"^[*_`>\s]+", "", last)   # 去掉行首的斜体/引用标记再判引用行
        if (not last or re.fullmatch(r"[-*_]{3,}", last)          # 空行与 --- 分隔线
                or _CITATION_TAIL.match(core) or _is_pure_link_line(last) or _LINK_TAIL.match(core)):
            lines.pop()
            continue
        break
    if not lines:
        return False
    # 结尾的 **加粗** / `代码` 标记不是正文终止符
    t = re.sub(r"[*_`]+$", "", lines[-1].rstrip()).rstrip()
    ends_ok = t.endswith(_TRAILING_PUNCT) or bool(re.search(r"[！？?。][”\"’]?$", t))
    has_sections = len(re.findall(r"^## ", text, re.MULTILINE)) >= 3
    return bool(ends_ok) and has_sections


# 公众号内容安全红线：命中即不可发布（涉黄/攻击工具/作弊/破解/仿冒品牌/灰产）
RISK_PATTERNS = [
    (r"nsfw|18\+|uncensored|\bporn(?:hub|hography)?\b|adult\s*(?:video|content|site)|hentai|onlyfans|"
     r"xxx\b|nude|naked|色情|成人内容|淫|裸聊|约炮", "涉黄"),
    (r"\bexploit\b|\bpoc\b|cve-\d{4}-\d+|webshell|backdoor|keylogger|brute[-\s]?force|ddos|botnet|"
     r"ransomware|malware|rootkit|privilege[-\s]?escalation|payload[-\s]?(?:gen|builder)|bypass[-\s]?av|"
     r"漏洞利用|注入攻击|免杀|木马|后门|恶意软件|挖矿脚本?|脱库|勒索软件|钓鱼(?:网站|邮件|链接)", "攻击/漏洞利用"),
    (r"aimbot|wallhack|auto[-\s]?aim|\bcheat\b|hack[-\s]?(?:menu|client)|unfairplay|anti[-\s]?cheat[-\s]?bypass|"
     r"外挂|辅助科技|自动瞄准|穿墙透视", "游戏作弊"),
    (r"\bcrack(?:ed|key)?\b|keygen|serial[-\s]?(?:gen|key)|pirat|激活码|破解版|注册机|盗版", "盗版/破解"),
    (r"spam[-\s]?(?:bot|er)|fake[-\s]?(?:traffic|followers|review)|刷量|引流软件|代发(?:短信|广告)|接码|"
     r"薅羊毛|免税卡|批量注册|养号|代挂|刷(?:播放量|粉丝|点赞|评论|单)|免费(?:领|刷|开通)(?:会员|账号)|"
     r"trial[-\s]?abuse|free[-\s]?trial[-\s]?(?:script|auto|bot)", "灰产"),
    (r"^(?:microsoft[-_]?office|chatgpt|claude[-_]?\d|gpt[-_]?\d*[-_]?pro|notion[-_]?pro|spotify[-_]?premium|"
     r"canva[-_]?pro|youtube[-_]?premium|netflix[-_]?account)$", "仿冒品牌"),
]


def risk_flags(*texts):
    """返回命中的风险类别（去重）。用于选题/发布前硬拦，不参与正文措辞统计。

    仓库名形如 owner/name，仿冒品牌那条只在「名字段」上判，所以整串与每个 / 段都要试。
    """
    hits = set()
    for t in texts:
        t = (t or "").strip()
        if not t:
            continue
        scopes = [t] + [seg for seg in t.split("/") if seg and seg != t]
        for pat, label in RISK_PATTERNS:
            if any(re.search(pat, s, re.IGNORECASE) for s in scopes):
                hits.add(label)
    return sorted(hits)


# 「攻击/漏洞利用」以外的类别无论什么口径都不能出现；这一类的界限要看我们是
# 在推荐一个项目，还是在报道一件事 —— 供应链木马本来就是日更的正当选题。
RISK_ALWAYS = ("涉黄", "游戏作弊", "盗版/破解", "灰产", "仿冒品牌")


def risk_verdict(subject_texts, editorial_texts, recommend):
    """返回 (必须拦下的类别, 只告警的类别)。

    subject = 被推荐/被报道的对象（仓库名、描述、topics、素材标题/URL）；
    editorial = 我们写出来的话（标题、topic、angle、core_view）。

    recommend=True（开源精选）：任何一类命中都硬拦 —— 我们是在让读者去用这个东西。
    recommend=False（日更新闻）：只硬拦 RISK_ALWAYS，「攻击/漏洞利用」降为告警 ——
    报道一个 PoC、一条 npm 恶意包新闻本来就是正当选题，把它打死等于自废一半版面。
    """
    always = set(RISK_ALWAYS)
    subject = set(risk_flags(*subject_texts))
    editorial = set(risk_flags(*editorial_texts))
    if recommend:
        return sorted(subject | editorial), []
    hard = (subject | editorial) & always
    return sorted(hard), sorted((subject | editorial) - always)


BOILERPLATE = ("值得注意的是", "想象一下", "让我们", "综上所述", "总而言之", "不难发现",
               "可以看到", "众所周知", "首先，", "其次，", "最后，", "在当今", "毫无疑问")

MAX_BOILERPLATE = 4        # 全文套话上限（历史上最好的稿子也在 2 次以内）
MAX_SECTION_OVERLAP = 1    # 与近几天任意一篇相同小节标题的容忍个数：第 2 个就算雷同


def boilerplate_count(md):
    return sum(md.count(p) for p in BOILERPLATE)


def style_issues(md, recent_articles=(), recent_titles=()):
    """千篇一律的机器可判部分：套话密度、小节标题雷同、标题句式雷同。

    只作重试提示与告警，不判定失败 —— 排版雷同不值得让整条流水线红。
    """
    problems = []
    n = boilerplate_count(md)
    if n > MAX_BOILERPLATE:
        problems.append(f"套话过多（{n} 处，上限 {MAX_BOILERPLATE}）：请删掉「想象一下/值得注意的是/让我们」这类填充语")

    heads = set(re.findall(r"^## (.+)$", md, re.MULTILINE))
    prev_heads = set()
    for prev in recent_articles:
        prev_heads.update(re.findall(r"^## (.+)$", prev, re.MULTILINE))
    overlap = heads & prev_heads
    if len(overlap) > MAX_SECTION_OVERLAP:
        problems.append("小节标题与近期文章雷同（%d 个相同：%s）" % (
            len(overlap), "、".join(sorted(overlap)[:3])))

    if recent_titles:
        colon = lambda t: (":" in t) or ("：" in t)
        mine = md.strip().splitlines()[0].lstrip("#").strip() if md.strip() else ""
        if colon(mine) and all(colon(t) for t in recent_titles):
            problems.append("标题句式与近期文章全部一样（都是「主标题：副标题」），请换一种写法")
    return problems


def recent_outputs(days=5, kind="daily"):
    """读最近几天的产物 md，供 style_issues 比对（workflow 里 checkout 带全历史）。

    kind="daily" 对应 output/2026-11-06.md，kind="git" 对应 output/git_2026-11-05.md。
    """
    files = sorted(glob.glob("output/git_*.md" if kind == "git" else "output/2*.md"))[:-1]
    texts, titles = [], []
    for f in files[-days:]:
        try:
            with open(f, encoding="utf-8") as fh:
                text = fh.read()
        except OSError:
            continue
        texts.append(text)
        for line in text.splitlines():
            if line.startswith("# "):
                titles.append(line[2:].strip())
                break
    return texts, titles


def slim_collected(collected, max_chars=8000, max_items=6, excerpt_len=400):
    sources = []
    for source in collected.get("sources", []):
        items = []
        for item in source.get("results", [])[:max_items]:
            entry = {
                "title": item.get("title") or "",
                "url": item.get("url") or "",
                "description": (item.get("description") or "")[:240],
            }
            # 时效/热度信号：让主编能按新鲜度选选题
            for key in ("pub_date", "age_hours", "recency", "hotness", "source", "language",
                        "trending_rank", "stars", "tier"):
                if item.get(key):
                    entry[key] = item.get(key)
            ft = item.get("full_text") or ""
            if ft:
                entry["excerpt"] = ft[:excerpt_len]
            items.append(entry)
        sources.append({"query": source.get("query"), "results": items})
    payload = {
        "date": collected.get("date"),
        "topics": collected.get("topics"),
        "engine": collected.get("engine"),
        "sources": sources,
    }
    text = json.dumps(payload, ensure_ascii=False)
    if len(text) <= max_chars:
        return text
    for source in sources:
        for item in source["results"]:
            item.pop("excerpt", None)
    payload["sources"] = sources
    text = json.dumps(payload, ensure_ascii=False)
    if len(text) <= max_chars:
        return text
    while sources and len(text) > max_chars:
        if sources[-1]["results"]:
            sources[-1]["results"].pop()
            if not sources[-1]["results"]:
                sources.pop()
        else:
            sources.pop()
        payload["sources"] = sources
        text = json.dumps(payload, ensure_ascii=False)
    return text
