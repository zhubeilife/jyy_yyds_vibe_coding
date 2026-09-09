#!/bin/bash
# 下载 jyywiki GSE 2026 课程讲义 + 幻灯片，并把幻灯片转成 PDF、md 修复成真 Markdown。
#
# 去重策略：
#   - 每个文件先下载到临时文件，用 sha256 跟"上一次的原始内容"比较
#     · slides*.html：直接跟本地同名文件比较（转换脚本不会修改这个文件本身）
#     · *.md：跟 fix_md.py 生成的 *.page.html 备份比较（.md 本身在转换后已经不是原始内容了）
#   - 内容一致 -> 丢弃临时文件，原文件、mtime 都不动，后续转换步骤会自动跳过
#   - 内容不同/是新文件 -> 覆盖写入，交给对应转换脚本处理
#
# 依赖：
#   pip install playwright img2pdf pypdf
#   python3 -m playwright install chromium
#   apt install pandoc
#
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"   # 先记下脚本自身所在目录，再 cd，避免相对路径失效
BASE="https://jyywiki.cn/GSE/2026"
mkdir -p GSE2026 && cd GSE2026

sha() { sha256sum "$1" 2>/dev/null | awk '{print $1}'; }

echo "== 抓取首页链接 =="
curl -sL "$BASE/" \
  | grep -oE 'href="[a-zA-Z0-9_-]+\.(md|html)"' \
  | sed -E 's/href="(.*)"/\1/' \
  | sort -u > filelist.txt
cat filelist.txt

echo "== 下载文件（内容不变的会跳过） =="
CHANGED_MD=()
CHANGED_SLIDES=()
while read -r fname; do
    tmp="$(mktemp)"
    curl -sL -o "$tmp" "$BASE/$fname"

    if [[ "$fname" == *.md ]]; then
        ref="${fname%.md}.page.html"     # 跟上次的原始网页备份比较
    else
        ref="$fname"                      # slides*.html：跟本地文件本身比较
    fi

    if [ -f "$ref" ] && [ "$(sha "$tmp")" == "$(sha "$ref")" ]; then
        echo "- $fname 内容未变化，跳过"
        rm -f "$tmp"
    else
        echo "+ $fname 有更新，下载覆盖"
        mv "$tmp" "$fname"
        if [[ "$fname" == *.md ]]; then
            CHANGED_MD+=("$fname")
        else
            CHANGED_SLIDES+=("$fname")
        fi
    fi
done < filelist.txt

echo "== 转换 slides*.html 为 PDF =="
if [ ${#CHANGED_SLIDES[@]} -gt 0 ]; then
    python3 "$SCRIPT_DIR/html2pdf_slides.py" "${CHANGED_SLIDES[@]}"
else
    echo "没有需要（重新）转换的 slides"
fi

echo "== 修复 *.md（提取正文、转真正的 Markdown） =="
if [ ${#CHANGED_MD[@]} -gt 0 ]; then
    python3 "$SCRIPT_DIR/fix_md.py" "${CHANGED_MD[@]}"
else
    echo "没有需要（重新）转换的 md"
fi

echo "全部完成，文件在 $(pwd)"
