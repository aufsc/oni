#!/usr/bin/env python3
"""静态博客构建脚本

目录约定（均相对于本文件所在目录）：
    posts/        Markdown 文章，文件名以 _ 开头的视为草稿，不发布
    templates/    base / index / post / about / categories / contact / info .html
    static/       style.css、main.js、index.js、post.js 等，原样复制到 dist/static
    categories.md 可选。存在则用它渲染分类页；不存在则根据文章分类自动生成
    dist/         输出目录

文章头部格式：
    0: # 页面标题
    1: cover: 封面图地址   （或 ![](地址)）
    2: 时间               （2025-01-01 / 2025年1月1日 / 2025/1/1）
    3: 分类
    4: 词云标签            （逗号分隔）
    5: # 正文标题
    6+: 正文

可选依赖：pygments（代码高亮）。未安装时代码块按普通样式输出。
"""
import html
import os
import re
import shutil
from datetime import datetime, timezone
from email.utils import format_datetime
from urllib.parse import quote
from xml.sax.saxutils import escape as xml_escape

import mistune
from jinja2 import Environment, FileSystemLoader, TemplateNotFound, select_autoescape

try:
    from pygments import highlight
    from pygments.formatters import HtmlFormatter
    from pygments.lexers import get_lexer_by_name
    from pygments.util import ClassNotFound
    HAS_PYGMENTS = True
except ImportError:
    HAS_PYGMENTS = False

# ------------------------------------------------------------------ 站点配置
SITE = {
    "name": "blog",
    "domain": "xxxx.org",
    "url": "https://xxxx.org",       # 用于 sitemap / RSS / canonical；留空则不生成这些
    "description": "blog",
    "logo": "https://xxxx.org/logo",
    "email": "contact@example.com",     # 首页侧栏与联系页留言表单的收件地址
    "github": "https://github.com",
    "start_date": "2023-01-01",         # 首页“运行时间”的起点
    "giscus": {                          # 四项都填好才会加载评论；留空则不显示评论区
        "repo": "",
        "repo_id": "",
        "category": "Announcements",
        "category_id": "",
    },
}

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
POSTS_DIR = os.path.join(BASE_DIR, "posts")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR = os.path.join(BASE_DIR, "static")
DIST_DIR = os.path.join(BASE_DIR, "dist")
CATEGORIES_MD = os.path.join(BASE_DIR, "categories.md")

PAGES = ["about", "categories", "info", "contact"]
UNCATEGORIZED = "未分类"
EXCERPT_LEN = 120


# ------------------------------------------------------------------ Markdown
class Renderer(mistune.HTMLRenderer):
    """代码块用 pygments 高亮（mistune 2.x / 3.x 通用签名）。"""

    def block_code(self, code, info=None):
        lang = (info or "").strip().split(None, 1)[0] if info else ""
        if HAS_PYGMENTS and lang:
            try:
                lexer = get_lexer_by_name(lang)
            except ClassNotFound:
                lexer = None
            if lexer:
                body = highlight(code, lexer, HtmlFormatter(nowrap=True))
                return f'<pre class="highlight"><code class="language-{html.escape(lang)}">{body}</code></pre>\n'
        return super().block_code(code, info)


markdown = mistune.create_markdown(renderer=Renderer(escape=False), plugins=["table", "task_lists"])


def pygments_css():
    """明/暗两套高亮配色，分别挂在 data-theme 下。"""
    if not HAS_PYGMENTS:
        return "/* 未安装 pygments：pip install pygments 后重新构建即可启用代码高亮 */\n"
    light = HtmlFormatter(style="default").get_style_defs('[data-theme="light"] .highlight')
    try:
        dark = HtmlFormatter(style="github-dark").get_style_defs('[data-theme="dark"] .highlight')
    except ClassNotFound:
        dark = HtmlFormatter(style="monokai").get_style_defs('[data-theme="dark"] .highlight')
    css = light + "\n" + dark + "\n"
    # 只保留带 .highlight 前缀的规则，避免 pygments 的全局 pre/td 规则影响其它元素
    return "\n".join(l for l in css.splitlines() if l.startswith("[data-theme")) + "\n"


# ------------------------------------------------------------------ 工具函数
def parse_date(s):
    """解析各种日期写法，失败返回 datetime.min（排在最后）。"""
    s = (s or "").strip()
    for fmt in ("%Y-%m-%d", "%Y年%m月%d日", "%Y/%m/%d",
                "%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    m = re.match(r"(\d{4})\D+(\d{1,2})\D+(\d{1,2})", s)       # 2025-1-5 / 2025.1.5 等
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass
    return datetime.min


def post_out_name(filename):
    return re.sub(r"\.md$", ".html", filename)


def slugify(text):
    s = re.sub(r"[^\w\- ]+", "", text.lower(), flags=re.U).strip()
    return re.sub(r"[\s_]+", "-", s) or "section"


def strip_tags(s):
    return html.unescape(re.sub(r"<[^>]+>", "", s)).strip()


HEADING_RE = re.compile(r"<h([1-6])(\s[^>]*)?>(.*?)</h\1>", re.S)


def add_heading_ids(content):
    """给标题生成稳定的 id（同名自动加 -2、-3…），并收集目录。"""
    toc, used = [], {}

    def repl(m):
        level, attrs, inner = int(m.group(1)), m.group(2) or "", m.group(3)
        text = strip_tags(inner)
        found = re.search(r'\bid="([^"]+)"', attrs)
        if found:
            hid = found.group(1)
        else:
            base = slugify(text)
            n = used.get(base, 0) + 1
            used[base] = n
            hid = base if n == 1 else f"{base}-{n}"
            attrs += f' id="{hid}"'
        toc.append({"id": hid, "text": text, "level": level, "indent": max(level - 2, 0) * 12})
        return f"<h{level}{attrs}>{inner}</h{level}>"

    return HEADING_RE.sub(repl, content), toc


def make_excerpt(content):
    text = re.sub(r"<pre.*?</pre>", " ", content, flags=re.S)
    text = re.sub(r"\s+", " ", strip_tags(text))
    return text[:EXCERPT_LEN] + ("…" if len(text) > EXCERPT_LEN else "")


# ------------------------------------------------------------------ 文章解析
def parse_post(filepath):
    with open(filepath, "r", encoding="utf-8-sig") as f:
        lines = f.read().splitlines()           # 兼容 \r\n

    def line(i, default=""):
        return lines[i].strip() if len(lines) > i else default

    filename = os.path.basename(filepath)

    title_line = line(0, filename)               # 0: 页面标题
    page_title = (title_line.lstrip("#").strip() if title_line.startswith("#") else title_line) or filename

    cover = re.sub(r"^cover\s*[:：]\s*", "", line(1), flags=re.I).strip()      # 1: 封面图
    if cover.startswith("!["):
        m = re.search(r"!\[.*?\]\((.*?)\)", cover)
        cover = m.group(1).strip() if m else ""

    modified_time = line(2)                       # 2: 时间
    category = line(3)                            # 3: 分类
    tags = list(dict.fromkeys(t.strip() for t in re.split(r"[,，]", line(4)) if t.strip()))   # 4: 标签

    article_title = (line(5).lstrip("#").strip() if len(lines) > 5 else page_title) or page_title   # 5

    body = markdown("\n".join(lines[6:]))         # 6+: 正文
    body = re.sub(r"<img\b(?![^>]*\bloading=)", '<img loading="lazy" decoding="async"', body)   # 图片懒加载
    body, toc = add_heading_ids(body)

    return {
        "filename": filename,
        "url": "/post/" + quote(post_out_name(filename)),
        "title": page_title,
        "cover": cover or None,
        "modified_time": modified_time,
        "category": category,
        "tags": tags,
        "tags_str": ",".join(tags),
        "article_title": article_title,
        "content": body,
        "toc": toc,
        "excerpt": make_excerpt(body),
        "date": parse_date(modified_time),
    }


def get_posts():
    if not os.path.isdir(POSTS_DIR):
        print(f"⚠️  未找到文章目录：{POSTS_DIR}")
        return []
    posts = [parse_post(os.path.join(POSTS_DIR, f))
             for f in sorted(os.listdir(POSTS_DIR))
             if f.endswith(".md") and not f.startswith("_")]
    posts.sort(key=lambda p: p["date"], reverse=True)
    return posts


# ------------------------------------------------------------------ 分类页
def categories_from_posts(posts):
    groups = {}
    for p in posts:                               # posts 已按时间倒序
        groups.setdefault(p["category"] or UNCATEGORIZED, []).append({"name": p["title"], "href": p["url"]})
    return [{"name": k, "articles": v} for k, v in groups.items()]


def categories_from_md(text):
    """解析 categories.md：# 分类名 / ## [标题](链接)。"""
    cats, current = [], None
    for raw in text.splitlines():
        h1, h2 = re.match(r"^#\s+(.+)", raw), re.match(r"^##\s+(.+)", raw)
        if h1:
            current = {"name": h1.group(1).strip(), "articles": []}
            cats.append(current)
        elif h2 and current is not None:
            item = h2.group(1).strip()
            link = re.search(r"\[(.+?)\]\((.+?)\)", item)
            current["articles"].append({"name": link.group(1), "href": link.group(2)} if link
                                       else {"name": item, "href": "#"})
    return cats


def get_categories(posts):
    if os.path.exists(CATEGORIES_MD):
        with open(CATEGORIES_MD, encoding="utf-8-sig") as f:
            return categories_from_md(f.read())
    return categories_from_posts(posts)


# ------------------------------------------------------------------ SEO 文件
def build_sitemap(posts):
    base = SITE["url"].rstrip("/")
    urls = [("/", None)] + [(f"/{p}.html", None) for p in ("categories", "about", "contact")]
    urls += [(p["url"], p["date"]) for p in posts]
    items = []
    for path, d in urls:
        lastmod = f"<lastmod>{d:%Y-%m-%d}</lastmod>" if d and d != datetime.min else ""
        items.append(f"  <url><loc>{xml_escape(base + path)}</loc>{lastmod}</url>")
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + "\n".join(items) + "\n</urlset>\n")


def build_rss(posts):
    base = SITE["url"].rstrip("/")
    items = []
    for p in posts[:20]:
        link = xml_escape(base + p["url"])
        pub = f"<pubDate>{format_datetime(p['date'].replace(tzinfo=timezone.utc))}</pubDate>" if p["date"] != datetime.min else ""
        items.append(f"    <item><title>{xml_escape(p['title'])}</title><link>{link}</link>"
                     f"<guid>{link}</guid>{pub}<description>{xml_escape(p['excerpt'])}</description></item>")
    return ('<?xml version="1.0" encoding="UTF-8"?>\n<rss version="2.0"><channel>\n'
            f"  <title>{xml_escape(SITE['name'])}</title><link>{xml_escape(base)}/</link>"
            f"<description>{xml_escape(SITE['description'])}</description>\n" + "\n".join(items) + "\n  </channel></rss>\n")


# ------------------------------------------------------------------ 构建
def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def build():
    if os.path.exists(DIST_DIR):
        shutil.rmtree(DIST_DIR)
    os.makedirs(os.path.join(DIST_DIR, "post"), exist_ok=True)

    if os.path.isdir(STATIC_DIR):
        shutil.copytree(STATIC_DIR, os.path.join(DIST_DIR, "static"))
    write(os.path.join(DIST_DIR, "static", "pygments.css"), pygments_css())

    env = Environment(loader=FileSystemLoader(TEMPLATES_DIR),
                      autoescape=select_autoescape(["html", "xml"]))
    env.globals["SITE"] = SITE
    posts = get_posts()

    # 1. 首页
    write(os.path.join(DIST_DIR, "index.html"),
          env.get_template("index.html").render(page="index", posts=posts))

    # 2. 文章页
    post_tpl = env.get_template("post.html")
    for p in posts:
        write(os.path.join(DIST_DIR, "post", post_out_name(p["filename"])),
              post_tpl.render(page="post", **p))

    # 3. 独立页面
    built = 0
    for page in PAGES:
        try:
            tpl = env.get_template(f"{page}.html")
        except TemplateNotFound:
            print(f"⚠️  跳过：缺少模板 {page}.html")
            continue
        ctx = {"page": page, "title": page.capitalize(), "posts": posts}
        if page == "categories":
            ctx["categories"] = get_categories(posts)
        write(os.path.join(DIST_DIR, f"{page}.html"), tpl.render(**ctx))
        built += 1

    # 4. SEO 文件（需要在 SITE["url"] 里配置站点地址）
    if SITE["url"]:
        write(os.path.join(DIST_DIR, "sitemap.xml"), build_sitemap(posts))
        write(os.path.join(DIST_DIR, "rss.xml"), build_rss(posts))
        write(os.path.join(DIST_DIR, "robots.txt"),
              f"User-agent: *\nAllow: /\nSitemap: {SITE['url'].rstrip('/')}/sitemap.xml\n")

    print(f"✅ Build complete! {len(posts)} posts + {built} pages → {os.path.relpath(DIST_DIR)}/")
    if not HAS_PYGMENTS:
        print("ℹ️  未安装 pygments，代码块不会高亮（pip install pygments）")


if __name__ == "__main__":
    build()