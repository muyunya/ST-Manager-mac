# macOS 打包与适配

本仓库是 [Dadihu123/ST-Manager](https://github.com/Dadihu123/ST-Manager) 的个人自用分支，
额外做了「打包成 macOS 应用（.app / .dmg）」所需的适配。上游代码逻辑未改动，
差异集中在启动入口、目录约定和打包脚本三处。

## 一键打包

```bash
bash scripts/build-macos-dmg.sh              # 产物在 dist/ 下
OUT_DIR=~/Desktop bash scripts/build-macos-dmg.sh
```

脚本会：建 venv → 装依赖（含 `pyobjc-framework-Cocoa`）→ 用应用图标生成 `.icns`
→ PyInstaller 冻结成 `ST Manager Pro.app` → 组装成带 `Applications` 快捷方式的 `.dmg`。

需要 Python 3.10+（可用 `PYTHON=/path/to/python` 指定）。

## 相对上游的改动

| 位置 | 改动 | 原因 |
| --- | --- | --- |
| `core/config.py` | 冻结版的数据目录改为 `~/Library/Application Support/ST-Manager` | 上游把 `config.json` / `data/` 放在可执行文件旁边；`.app` 包内可能只读（直接从 DMG 运行、App Translocation），会写入失败 |
| `core/config.py` | 缩略图/临时文件 → `~/Library/Caches/ST-Manager`，日志 → `~/Library/Logs/ST-Manager` | 遵循 macOS 目录约定；缓存目录可被系统清理，因此只放可再生数据，用户数据仍留在 Application Support |
| `app.py` | 端口被占用时自动顺延并写回 `config.json` | macOS 的「AirPlay 接收器」默认占用 5000；窗口版没有控制台，直接退出会让用户以为应用没反应 |
| `app.py` | 冻结版把日志写入文件，启动失败弹系统对话框 | 同上，窗口版看不到任何输出 |
| `app.py` | 用 Cocoa（`NSApplication`）事件循环托管 Flask 服务 | PyInstaller 的 windowed bootloader 是纯命令行进程，不处理 Cocoa 事件：程序坞点「退出」或 ⌘Q 会一直挂住。现在程序坞常驻、点击图标重新打开界面、退出时后台服务一起结束 |
| `scripts/build-macos-dmg.sh` | 新增 | 上游 CI 只产出 `.app` 的 zip，没有 dmg |

源码模式（`python app.py`）的目录布局与上游完全一致，以上 macOS 目录约定只在
PyInstaller 冻结运行时生效（`sys.frozen` + `sys.platform == 'darwin'`）。

## 数据位置

```
~/Library/Application Support/ST-Manager/
    config.json       配置（SillyTavern 目录、端口、认证等）
    data/library/     角色卡、世界书、聊天记录、预设、美化包
    data/assets/      图片等资源
    data/system/      数据库、回收站、自动化规则
~/Library/Caches/ST-Manager/
    thumbnails/       缩略图（可删，会重新生成）
    temp/             临时文件
~/Library/Logs/ST-Manager/
    st-manager.log    运行日志
```

应用运行后，菜单栏「文件夹」菜单可以直接在访达中打开这三个目录。

## 首次打开（Gatekeeper）

本应用未签名、未公证，从网络下载后 macOS 会拦截：

- 在「应用程序」里**右键 → 打开**，再点一次「打开」；
- 或执行 `xattr -dr com.apple.quarantine "/Applications/ST Manager Pro.app"`。

本地自行构建的 dmg 不带 quarantine 标记，可以直接双击。

## 与上游同步

```bash
git remote add upstream https://github.com/Dadihu123/ST-Manager.git   # 若尚未添加
git fetch upstream && git merge upstream/main
```

## 许可

上游为 **AGPL-3.0**（见 `LICENSE`）。自用、不对外分发时无额外义务；
若要把本分支公开或分发构建产物，需要保留许可并在显著位置说明修改内容。
