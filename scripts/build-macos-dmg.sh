#!/usr/bin/env bash
# ============================================================================
# 把本仓库打包成 macOS 应用（.app）与安装镜像（.dmg）
#
# 用法：
#   bash scripts/build-macos-dmg.sh                 # 产物在 dist/ 下
#   OUT_DIR=~/Desktop bash scripts/build-macos-dmg.sh
#
# 产物：
#   <OUT_DIR>/ST-Manager-Pro-macos-<arch>.dmg
#   dist/ST Manager Pro.app
#
# 说明：
#   * 未签名、未公证。首次打开需右键 -> 打开，或 xattr -dr com.apple.quarantine。
#   * 需要 Python 3.10+；pyobjc-framework-Cocoa 用于程序坞集成（见 MACOS.md）。
# ============================================================================
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_DIR="$REPO/.build"
ARCH="$(uname -m)"
APP_NAME="ST Manager Pro"
OUT_DIR="${OUT_DIR:-$REPO/dist}"
DMG="$OUT_DIR/ST-Manager-Pro-macos-$ARCH.dmg"

echo "==> 仓库: $REPO"

# --- 1. 选择 Python (>=3.10) -----------------------------------------------
PY="${PYTHON:-}"
if [ -z "$PY" ]; then
  for candidate in python3.13 python3.12 python3.11 python3.10 python3; do
    if command -v "$candidate" >/dev/null 2>&1 \
       && "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
      PY="$(command -v "$candidate")"
      break
    fi
  done
fi
[ -n "$PY" ] || { echo "找不到 Python 3.10+，可用 PYTHON=/path/to/python 指定"; exit 1; }
echo "==> Python: $($PY -V 2>&1) ($PY)"

# --- 2. 构建环境 -----------------------------------------------------------
mkdir -p "$BUILD_DIR"
if [ ! -x "$BUILD_DIR/venv/bin/python" ]; then
  echo "==> 创建 venv"
  "$PY" -m venv "$BUILD_DIR/venv"
fi
VENV="$BUILD_DIR/venv/bin/python"
echo "==> 安装依赖"
"$VENV" -m pip install -q --upgrade pip
# pyobjc-framework-Cocoa：给打包后的应用装上 Cocoa 事件循环，
# 这样它会常驻程序坞，且程序坞「退出」/⌘Q 能真正结束进程（含后台 Flask 服务）。
"$VENV" -m pip install -q -r "$REPO/requirements.txt" pyinstaller pyobjc-framework-Cocoa

# --- 3. 生成 .icns 应用图标 ------------------------------------------------
echo "==> 生成应用图标"
ICNS="$BUILD_DIR/st-manager.icns"
"$VENV" - "$REPO" "$ICNS" <<'PYEOF'
import os, subprocess, sys
from PIL import Image, ImageFilter

repo, icns_out = sys.argv[1], sys.argv[2]
iconset = os.path.join(os.path.dirname(icns_out), 'st-manager.iconset')
mark = Image.open(os.path.join(repo, 'static/images/brand/stm-mark.png')).convert('RGBA')

# 原图较小，放大到 1024 画布的 86% 并轻微锐化；.icns 需要 512/1024 尺寸
master_size, content = 1024, 880
scale = content / max(mark.size)
big = mark.resize((round(mark.width * scale), round(mark.height * scale)), Image.LANCZOS)
big = big.filter(ImageFilter.UnsharpMask(radius=1.6, percent=55, threshold=2))
canvas = Image.new('RGBA', (master_size, master_size), (0, 0, 0, 0))
canvas.paste(big, ((master_size - big.width) // 2, (master_size - big.height) // 2), big)

os.makedirs(iconset, exist_ok=True)
for name, size in [('icon_16x16.png', 16), ('icon_16x16@2x.png', 32), ('icon_32x32.png', 32),
                   ('icon_32x32@2x.png', 64), ('icon_128x128.png', 128), ('icon_128x128@2x.png', 256),
                   ('icon_256x256.png', 256), ('icon_256x256@2x.png', 512), ('icon_512x512.png', 512),
                   ('icon_512x512@2x.png', 1024)]:
    canvas.resize((size, size), Image.LANCZOS).save(os.path.join(iconset, name))
subprocess.run(['iconutil', '-c', 'icns', iconset, '-o', icns_out], check=True)
print('   icns ->', icns_out)
PYEOF

# --- 4. PyInstaller 打包 .app ---------------------------------------------
echo "==> PyInstaller 打包"
( cd "$REPO" && "$VENV" -m PyInstaller --clean --noconfirm --onedir --windowed \
    --name "$APP_NAME" \
    --osx-bundle-identifier "com.dadihu123.st-manager-pro" \
    --icon "$ICNS" \
    --add-data "templates:templates" \
    --add-data "static:static" \
    --collect-submodules watchdog \
    app.py > "$BUILD_DIR/pyinstaller.log" 2>&1 ) \
  || { echo "打包失败，日志：$BUILD_DIR/pyinstaller.log"; tail -20 "$BUILD_DIR/pyinstaller.log"; exit 1; }

APP="$REPO/dist/$APP_NAME.app"
[ -d "$APP" ] || { echo "未生成 $APP"; exit 1; }

# --- 5. 组装 DMG 内容 ------------------------------------------------------
echo "==> 组装 DMG"
STAGE="$BUILD_DIR/dmg-staging"
rm -rf "$STAGE"; mkdir -p "$STAGE"
ditto "$APP" "$STAGE/$APP_NAME.app"          # ditto 保留签名与扩展属性
ln -s /Applications "$STAGE/Applications"
cp "$ICNS" "$STAGE/.VolumeIcon.icns"
SetFile -a C "$STAGE" 2>/dev/null || true

cat > "$STAGE/安装说明.txt" <<NOTES
$APP_NAME — macOS 安装说明（本地自建版）
=============================================

项目来源：https://github.com/Dadihu123/ST-Manager
打包方式：PyInstaller 冻结 + hdiutil 生成 DMG（$(uname -m)）

1. 安装
   把左边的「$APP_NAME.app」拖到右边的 Applications 文件夹。
   （直接从 DMG 里双击也能运行，但拖到「应用程序」更稳妥。）

2. 首次打开
   本应用没有 Apple 开发者签名与公证，macOS 可能提示
   「无法验证开发者」或「已损坏，无法打开」。
   → 在「应用程序」里右键点击图标，选「打开」，再点一次「打开」。
   若仍然打不开，打开「终端」执行：
       xattr -dr com.apple.quarantine "/Applications/$APP_NAME.app"

3. 启动后
   应用会自动用默认浏览器打开本机地址（默认 http://127.0.0.1:5000）。
   macOS 的「AirPlay 接收器」默认占用 5000 端口，本打包版会自动顺延到
   下一个空闲端口，并把最终端口写回 config.json。

4. 程序坞（Dock）
   应用运行期间常驻程序坞；从程序坞右键「退出」或按 ⌘Q，会一并结束
   后台的 Flask 服务与扫描线程，不会留下后台进程。
   点击程序坞图标可重新打开界面；菜单栏「文件夹」可直接在访达中定位
   数据、缓存与日志目录。

5. 数据位置（遵循 macOS 目录约定）
   ~/Library/Application Support/ST-Manager/
       config.json     配置（SillyTavern 目录、端口、认证等）
       data/library/   角色卡、世界书、聊天记录、预设、美化包
       data/assets/    图片等资源
       data/system/    数据库、回收站、自动化规则
   ~/Library/Caches/ST-Manager/
       thumbnails/     缩略图（可随时删除，会重新生成）
       temp/           临时文件
   ~/Library/Logs/ST-Manager/
       st-manager.log  运行日志（窗口版没有控制台，排障先看这里）

6. 退出
   关闭浏览器页面不会退出程序。请在程序坞右键图标选择「退出」，或按 ⌘Q；
   也可以在终端执行：pkill -f "$APP_NAME"
NOTES

mkdir -p "$OUT_DIR"
rm -f "$DMG"
hdiutil create -volname "$APP_NAME" -srcfolder "$STAGE" -ov -format UDZO "$DMG" >/dev/null
hdiutil verify "$DMG" >/dev/null
rm -rf "$STAGE"

echo
echo "✅ 完成"
echo "   DMG: $DMG  ($(du -h "$DMG" | cut -f1))"
echo "   APP: $APP"
