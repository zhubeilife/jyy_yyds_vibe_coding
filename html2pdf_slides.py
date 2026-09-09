#!/usr/bin/env python3
"""
把 jyywiki GSE 课程的 slidesN.html（自定义翻页幻灯片，非 reveal.js）转换成 PDF。
原理：页面用 JS 的 show(n) 函数切换 .slide 的 active 状态，一次只显示一页。
这里用 Playwright 打开页面后，逐页调用 show(n) 并截图，再用 img2pdf 合并成一个 PDF。

用法：
    python3 html2pdf_slides.py slides1.html slides2.html slides3.html
    # 会在同目录生成 slides1.pdf / slides2.pdf / slides3.pdf
    # 默认会跳过"html 没变化且 pdf 已存在"的文件；加 --force 强制全部重新转换
"""
import sys
import os
import tempfile
import img2pdf
from playwright.sync_api import sync_playwright

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
        page = browser.new_page(viewport=VIEWPORT, device_scale_factor=2)
        page.goto(f"file://{html_path}")
        page.wait_for_timeout(800)  # 等首屏 MathJax/highlight.js 加载

        total = page.evaluate("document.querySelectorAll('.slide').length")
        if not total:
            print(f"  ! 没找到 .slide 元素，跳过：{html_path}")
            browser.close()
            return

        with tempfile.TemporaryDirectory() as tmp:
            images = []
            for i in range(total):
                page.evaluate(f"show({i})")
                page.wait_for_timeout(WAIT_MS)
                img_path = os.path.join(tmp, f"{i:03d}.png")
                page.screenshot(path=img_path)
                images.append(img_path)
                print(f"  第 {i + 1}/{total} 页已截图")

            with open(pdf_path, "wb") as f:
                f.write(img2pdf.convert(images))
        browser.close()
    print(f"✓ 已生成 {pdf_path}（共 {total} 页）")


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
