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
# 附件（p7/、p10/ 下的讲义附件，如 rules.html、dsh-checks.html）不列在首页上，
# 只能从讲义正文里的站内链接发现，所以放在最后一步扫描 *.page.html 收集。
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
  | grep -oE 'href="(/GSE/2026/)?[a-zA-Z0-9_-]+\.(md|html)"' \
  | sed -E 's/href="(\/GSE\/2026\/)?(.*)"/\2/' \
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

echo "== 下载讲义里引用的站内附件（p7/、p10/ 等） =="
# 首页 filelist.txt 只有 lect*.md / lab*.md / slides*.html，附件藏在讲义正文的链接里。
# 扫的是 *.page.html（原始网页备份），不是转换后的 *.md —— 后者链接形式可能被改写。
# 只认站内 /GSE/2026/ 下的路径，且排除已经在 filelist.txt 里的文件（那些上面处理过了）。
ASSETS=$(grep -ohE 'href="/GSE/2026/[^"#?]+"' *.page.html 2>/dev/null \
    | sed -E 's/href="\/GSE\/2026\/([^"#?]+)"/\1/' \
    | grep -vE '^$' \
    | while read -r a; do
          # 跳过讲义自身（首页已覆盖），只留子目录或非 md/html 的资源
          if grep -qxF "$a" filelist.txt; then continue; fi
          case "$a" in *.md) continue ;; esac
          echo "$a"
      done \
    | sort -u)

if [ -z "$ASSETS" ]; then
    echo "没有发现站内附件"
else
    echo "$ASSETS" | while read -r asset; do
        mkdir -p "$(dirname "$asset")"
        tmp="$(mktemp)"
        if ! curl -fsL -o "$tmp" "$BASE/$asset"; then
            echo "! $asset 下载失败（链接可能已失效），跳过"
            rm -f "$tmp"
            continue
        fi
        # 防止服务器对不存在的路径返回 200 + HTML 错误页
        if head -c 512 "$tmp" | grep -qi '<title>404'; then
            echo "! $asset 返回 404 页面，跳过"
            rm -f "$tmp"
            continue
        fi
        if [ -f "$asset" ] && [ "$(sha "$tmp")" == "$(sha "$asset")" ]; then
            echo "- $asset 内容未变化，跳过"
            rm -f "$tmp"
        else
            echo "+ $asset 有更新，下载覆盖"
            mv "$tmp" "$asset"
        fi
    done
echo "附件已同步到$(pwd)"
fi

echo "全部完成，文件在 $(pwd)"
