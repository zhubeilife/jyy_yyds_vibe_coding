#!/usr/bin/env python3
"""
把 jyywiki GSE 课程的 slidesN.html（自定义翻页幻灯片，非 reveal.js）转换成 PDF。
原理：页面用 JS 的 show(n) 函数切换 .slide 的 active 状态，一次只显示一页。
这里用 Playwright 打开页面后，逐页调用 show(n)，用 Chromium 的"打印到 PDF"
（page.pdf()）单独导出每一页，再用 pypdf 合并成一个 PDF。

为什么不用截图拼 PDF：截图方案（旧版）生成的是纯图片，文字不可选中/搜索，页面里
的超链接（引用文献、附件 PDF/xlsx 等）也全部丢失。page.pdf() 走 Chromium 原生
打印路径，文字保持矢量、<a href> 会被保留成 PDF 的 /Link 注释，可以正常点击。

用法：
    python3 html2pdf_slides.py slides1.html slides2.html slides3.html
    # 会在同目录生成 slides1.pdf / slides2.pdf / slides3.pdf
    # 默认会跳过"html 没变化且 pdf 已存在"的文件；加 --force 强制全部重新转换
"""
import sys
import os
import tempfile
from playwright.sync_api import sync_playwright
from pypdf import PdfWriter

VIEWPORT = {"width": 1280, "height": 720}
WAIT_MS = 350  # 每页切换后等待排版/公式渲染的时间


def convert(html_path: str, pdf_path: str, force: bool = False):
    html_path = os.path.abspath(html_path)

    # 去重：html 的修改时间不晚于已存在的 pdf，说明没变化过，跳过
    if not force and os.path.exists(pdf_path) and os.path.getmtime(pdf_path) >= os.path.getmtime(html_path):
        print(f"- {os.path.basename(html_path)} 未变化且 {os.path.basename(pdf_path)} 已存在，跳过（如需强制重转加 --force）")
        return

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport=VIEWPORT)
        page.goto(f"file://{html_path}")
        page.emulate_media(media="screen")  # 用屏幕样式而不是打印样式，保持跟浏览器里看到的一致
        page.wait_for_timeout(800)  # 等首屏 MathJax/highlight.js 加载

        total = page.evaluate("document.querySelectorAll('.slide').length")
        if not total:
            print(f"  ! 没找到 .slide 元素，跳过：{html_path}")
            browser.close()
            return

        with tempfile.TemporaryDirectory() as tmp:
            writer = PdfWriter()
            for i in range(total):
                page.evaluate(f"show({i})")
                page.wait_for_timeout(WAIT_MS)
                page_pdf_path = os.path.join(tmp, f"{i:03d}.pdf")
                page.pdf(
                    path=page_pdf_path,
                    width=f"{VIEWPORT['width']}px",
                    height=f"{VIEWPORT['height']}px",
                    print_background=True,
                )
                writer.append(page_pdf_path)
                print(f"  第 {i + 1}/{total} 页已导出")

            with open(pdf_path, "wb") as f:
                writer.write(f)
        browser.close()
    print(f"✓ 已生成 {pdf_path}（共 {total} 页，保留文字与超链接）")


if __name__ == "__main__":
    args = sys.argv[1:]
    force = "--force" in args
    html_files = [a for a in args if a != "--force"]
    if not html_files:
        print("用法: python3 html2pdf_slides.py slides1.html [slides2.html ...] [--force]")
        sys.exit(1)
    for html_file in html_files:
        pdf_file = os.path.splitext(html_file)[0] + ".pdf"
        print(f"处理 {html_file} -> {pdf_file}")
        convert(html_file, pdf_file, force=force)
