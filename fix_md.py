#!/usr/bin/env python3
"""
jyywiki 的 "xxx.md" 链接其实不是原始 Markdown 源文件，而是 Next.js SSR 之后的完整网页
（跟首页是同一套框架渲染出来的），正文已经被转成了 <h1>/<p>/<ul> 等 HTML，外面还套了导航栏、
页脚、以及一大段内嵌的 __NEXT_DATA__ JSON（编译后的 MDX 源码 + 构建元信息）。

这个脚本做的事：
  1. 从下载下来的 "xxx.md" 文件中，提取 <div class="wiki ...">...正文...</div> 这一段真正的内容
  2. 把其中的相对路径图片（如 ai-native.webp）一并下载下来
  3. 用 pandoc 把这段 HTML 转换成干净的标准 Markdown，覆盖保存为真正的 .md 文件
  4. 原始抓取到的完整网页另存为 *.page.html，留作备份/对照

去重：*.page.html 备份就是"上一次原始网页内容"的凭证。再次运行时，会拿新下载的原始
内容跟已有的 *.page.html 比较哈希，一致就跳过（不重新转换、不覆盖已经修好的 .md）。
如果本来就已经是转换好的 Markdown（找不到 wiki 容器），会跳过并给出提示，而不是报错中断。

用法：
    python3 fix_md.py lect1.md lect2.md lect3.md lab1.md
    python3 fix_md.py --force lect1.md   # 强制重新转换
"""
import sys
import os
import re
import hashlib
import subprocess
import urllib.request

BASE = "https://jyywiki.cn/GSE/2026"

WIKI_START_RE = re.compile(r'<div class="wiki[^"]*">')
END_MARKER = '</div></div><div class="bg-neutral-100'


def extract_wiki_html(page_html: str) -> str:
    m = WIKI_START_RE.search(page_html)
    if not m:
        raise ValueError("没找到 <div class=\"wiki\"> 正文容器，页面结构可能变了")
    start = m.end()
    end = page_html.find(END_MARKER, start)
    if end == -1:
        raise ValueError("没找到正文结束标记，页面结构可能变了")
    return page_html[start:end]


def download_relative_images(html: str, out_dir: str):
    for src in re.findall(r'<img[^>]*src="([^"]+)"', html):
        if src.startswith("http") or src.startswith("data:"):
            continue
        dest = os.path.join(out_dir, src)
        if os.path.exists(dest):
            continue
        url = f"{BASE}/{src}"
        print(f"  下载图片 {url} -> {dest}")
        try:
            urllib.request.urlretrieve(url, dest)
        except Exception as e:
            print(f"  ! 图片下载失败: {e}")


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def convert_one(path: str, force: bool = False):
    out_dir = os.path.dirname(os.path.abspath(path)) or "."
    with open(path, encoding="utf-8") as f:
        page_html = f.read()

    backup_path = os.path.splitext(path)[0] + ".page.html"

    # 去重：跟上次的原始网页备份比对，内容没变就跳过
    if not force and os.path.exists(backup_path):
        with open(backup_path, encoding="utf-8") as f:
            old_page_html = f.read()
        if sha256(old_page_html) == sha256(page_html):
            print(f"- {path} 原始内容未变化，跳过（如需强制重转加 --force）")
            return

    try:
        wiki_html = extract_wiki_html(page_html)
    except ValueError:
        # 大概率是这个文件已经被转换过、现在传进来的就是真正的 Markdown 了
        print(f"- {path} 没找到网页正文容器（可能已经是转换好的 Markdown），跳过")
        return

    download_relative_images(wiki_html, out_dir)

    # 备份原始完整网页（供下次去重比对使用）
    with open(backup_path, "w", encoding="utf-8") as f:
        f.write(page_html)

    # pandoc: html -> gfm markdown
    result = subprocess.run(
        ["pandoc", "-f", "html", "-t", "gfm"],
        input=wiki_html.encode("utf-8"),
        capture_output=True,
    )
    if result.returncode != 0:
        print(f"  ! pandoc 转换失败: {result.stderr.decode()}")
        return

    with open(path, "w", encoding="utf-8") as f:
        f.write(result.stdout.decode("utf-8"))
    print(f"✓ {path} 已转换为标准 Markdown（原始网页备份为 {os.path.basename(backup_path)}）")


if __name__ == "__main__":
    args = sys.argv[1:]
    force = "--force" in args
    paths = [a for a in args if a != "--force"]
    if not paths:
        print("用法: python3 fix_md.py lect1.md [lect2.md ...] [--force]")
        sys.exit(1)
    for p in paths:
        try:
            convert_one(p, force=force)
        except Exception as e:
            print(f"  ! 处理 {p} 时出错，跳过：{e}")
