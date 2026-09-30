import argparse
import logging
import sys
import os

# 显示将当前工作目录添加到系统路径中
base_path = os.path.dirname(os.path.abspath(__file__))
if base_path not in sys.path:
    sys.path.insert(0, base_path)

import threading
import webbrowser
import platform

# 设置 UTF-8 输出编码，支持 emoji 显示（兼容 Windows）
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        import codecs
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
        sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

# 确保在 PyInstaller 打包环境下也能正确找到资源
if getattr(sys, 'frozen', False):
    if sys.platform == 'darwin':
        # macOS：.app 包内目录可能只读（DMG 直接运行 / App Translocation），
        # 工作目录切到用户可写的数据目录，与 core/config.py 的 BASE_DIR 保持一致。
        _data_home = os.environ.get('ST_MANAGER_HOME') or os.path.join(
            os.path.expanduser('~'), 'Library', 'Application Support', 'ST-Manager')
        os.makedirs(_data_home, exist_ok=True)
        os.chdir(_data_home)
    else:
        os.chdir(os.path.dirname(sys.executable))

# 导入核心工厂和初始化函数
# create_app: 创建 Flask 应用实例
# init_services: 初始化数据库、缓存和后台扫描线程
from core import create_app, init_services
from core.config import ensure_config_file, ensure_runtime_dirs, load_config, save_config
from core.utils.net import is_port_available


def setup_frozen_logging():
    """打包运行时没有控制台，把日志写入日志目录，便于排查启动问题。

    macOS 上遵循系统约定写入 ~/Library/Logs/ST-Manager/。
    """
    if not getattr(sys, 'frozen', False):
        return
    try:
        from core.config import LOG_DIR
        handler = logging.FileHandler(os.path.join(LOG_DIR, 'st-manager.log'), encoding='utf-8')
        handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        ))
        root = logging.getLogger()
        root.setLevel(logging.INFO)
        root.addHandler(handler)
    except Exception as exc:
        print(f'⚠️ 日志文件初始化失败: {exc}')


def notify_startup_failure(message):
    """打包运行时没有控制台，用系统弹窗提示启动失败，避免双击后毫无反应。"""
    if not getattr(sys, 'frozen', False) or platform.system() != 'Darwin':
        return
    try:
        import subprocess
        lines = [
            line.replace('\\', '\\\\').replace('"', '\\"')
            for line in (message.splitlines() or [''])
        ]
        text = ' & return & '.join(f'"{line}"' for line in lines)
        subprocess.run(
            [
                'osascript', '-e',
                f'display dialog ({text}) buttons {{"好"}} default button "好" '
                'with title "ST Manager 启动失败" with icon caution',
            ],
            check=False,
            capture_output=True,
        )
    except Exception:
        pass


def find_available_port(host, port, max_tries=20):
    """从 port 起寻找可用端口；都不可用时返回 None。

    macOS 上 5000 端口默认被「AirPlay 接收器」占用，直接退出会让应用看起来毫无反应。
    """
    for candidate in range(port, port + max_tries + 1):
        if is_port_available(candidate, host):
            return candidate
    return None


def open_ui_in_browser(host, port):
    """在默认浏览器中打开界面（绑定 0.0.0.0 时改用 127.0.0.1）。"""
    open_host = '127.0.0.1' if host == '0.0.0.0' else host
    try:
        webbrowser.open(f'http://{open_host}:{port}')
    except Exception:
        pass


def build_macos_menu_bar(app_name, delegate, folders):
    """构建 macOS 菜单栏（抽成独立函数便于测试）。

    folders 为 (菜单标题, 目录路径) 列表，用于在访达中定位数据/缓存/日志目录。
    """
    from AppKit import NSMenu, NSMenuItem

    menu_bar = NSMenu.alloc().init()

    app_menu_item = NSMenuItem.alloc().init()
    menu_bar.addItem_(app_menu_item)
    app_menu = NSMenu.alloc().init()
    open_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_('打开界面', 'openUI:', 'o')
    open_item.setTarget_(delegate)
    app_menu.addItem_(open_item)
    app_menu.addItemWithTitle_action_keyEquivalent_(f'退出 {app_name}', 'terminate:', 'q')
    app_menu_item.setSubmenu_(app_menu)

    folder_menu = NSMenu.alloc().initWithTitle_('文件夹')
    for title, path in folders:
        item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, 'revealPath:', '')
        item.setTarget_(delegate)
        item.setRepresentedObject_(path)
        folder_menu.addItem_(item)
    folder_menu_item = NSMenuItem.alloc().init()
    folder_menu_item.setSubmenu_(folder_menu)
    menu_bar.addItem_(folder_menu_item)

    return menu_bar


def run_macos_app(flask_app, host, port):
    """在 macOS 上用 Cocoa 事件循环托管 Flask 服务。

    直接用 `app.run()` 时进程只是个命令行程序：双击启动虽然会拿到程序坞图标，
    但它不处理 Cocoa 事件，从程序坞「退出」或 ⌘Q 都会一直没反应（osascript 同样
    会挂住）。这里显式建立 NSApplication 并接管退出流程，保证程序坞退出时
    Flask 服务与后台扫描线程一起结束。

    需要 pyobjc-framework-Cocoa；未安装时由调用方回退到 `app.run()`。
    """
    from AppKit import (
        NSApplication,
        NSApplicationActivationPolicyRegular,
        NSObject,
        NSWorkspace,
    )
    from Foundation import NSBundle, NSURL
    from werkzeug.serving import make_server

    from core.config import CACHE_DIR, DATA_DIR, LOG_DIR

    server = make_server(host, port, flask_app, threaded=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    def _open_ui():
        open_ui_in_browser(host, port)

    class _AppDelegate(NSObject):
        def applicationShouldTerminate_(self, sender):
            # NSTerminateNow(1)：立即退出，进程结束后台线程随之结束
            return 1

        def applicationWillTerminate_(self, notification):
            try:
                server.shutdown()
            except Exception:
                pass

        def applicationShouldHandleReopen_hasVisibleWindows_(self, sender, has_visible_windows):
            # 应用没有窗口：点程序坞图标即重新打开界面
            _open_ui()
            return True

        def openUI_(self, sender):
            _open_ui()

        def revealPath_(self, sender):
            # 在访达中定位目录：这些路径平时藏在 ~/Library 下，菜单里给个入口
            try:
                path = sender.representedObject()
                NSWorkspace.sharedWorkspace().activateFileViewerSelectingURLs_(
                    [NSURL.fileURLWithPath_(path)]
                )
            except Exception:
                pass

    ns_app = NSApplication.sharedApplication()
    ns_app.setActivationPolicy_(NSApplicationActivationPolicyRegular)
    delegate = _AppDelegate.alloc().init()
    ns_app.setDelegate_(delegate)

    # 极简菜单栏：⌘Q 与程序坞「退出」走同一条退出路径
    try:
        app_name = NSBundle.mainBundle().objectForInfoDictionaryKey_('CFBundleName') or 'ST Manager'
    except Exception:
        app_name = 'ST Manager'
    ns_app.setMainMenu_(build_macos_menu_bar(app_name, delegate, (
        ('打开数据目录', DATA_DIR),
        ('打开缓存目录', CACHE_DIR),
        ('打开日志', LOG_DIR),
    )))

    ns_app.activateIgnoringOtherApps_(True)
    ns_app.run()
    server.shutdown()


def is_running_in_docker():
    if os.path.exists('/.dockerenv'):
        return True

    cgroup_path = '/proc/1/cgroup'
    if not os.path.exists(cgroup_path):
        return False

    try:
        with open(cgroup_path, 'r', encoding='utf-8') as f:
            cgroup_content = f.read()
            return 'docker' in cgroup_content or 'containerd' in cgroup_content
    except OSError:
        return False


def parse_cli_args(argv=None):
    parser = argparse.ArgumentParser(
        description='Start ST-Manager. Command-line host/port overrides affect only the current run.'
    )
    parser.add_argument('--debug', action='store_true', help='Enable debug mode and auto reload for the current run')
    parser.add_argument('--host', help='Override the server host for the current run only')
    parser.add_argument('--port', type=int, help='Override the server port for the current run only')
    return parser.parse_args(argv)


def get_default_config_overrides(in_docker):
    return {'host': '0.0.0.0'} if in_docker else None


def ensure_startup_config(in_docker):
    ensure_config_file(default_overrides=get_default_config_overrides(in_docker))
    cfg = load_config()
    ensure_runtime_dirs(cfg)
    return cfg


def resolve_server_settings(cfg, cli_args):
    host = cli_args.host if cli_args.host is not None else cfg.get('host', '127.0.0.1')
    port = cli_args.port if cli_args.port is not None else cfg.get('port', 5000)
    debug = cli_args.debug or os.environ.get('FLASK_DEBUG') == '1'
    return host, port, debug

if __name__ == '__main__':
    cli_args = parse_cli_args()
    in_docker = is_running_in_docker()
    setup_frozen_logging()

    try:
        cfg = ensure_startup_config(in_docker)
    except Exception as exc:
        print(f'❌ 配置文件生成失败: {exc}')
        notify_startup_failure(f'配置文件生成失败: {exc}')
        if platform.system() == 'Windows':
            os.system('pause')
        sys.exit(1)

    # 1. 加载配置
    server_host, server_port, debug_mode = resolve_server_settings(cfg, cli_args)

    # 2. 端口占用检测
    # 如果端口被占用，给出友好提示并暂停（防止窗口闪退）
    # 注意：在 Flask Debug 模式(Reload)下，子进程启动时端口可能已被保留，因此仅在主进程检测
    if os.environ.get("WERKZEUG_RUN_MAIN") != "true":
        if not is_port_available(server_port, server_host):
            fallback_port = find_available_port(server_host, server_port + 1)
            if fallback_port is None:
                message = (f"地址 {server_host}:{server_port} 已被占用，且附近端口都不可用。"
                           "请修改 config.json 中的 'port' 设置。")
                print(f"\n{'='*60}")
                print(f"❌ 启动失败：{message}")
                print(f"{'='*60}\n")
                notify_startup_failure(message)
                if platform.system() == "Windows":
                    os.system("pause")
                sys.exit(1)

            # 自动顺延端口并写回 config.json，避免每次启动都换端口
            print(f"\n⚠️ 端口 {server_port} 已被占用，自动改用 {fallback_port}。")
            if platform.system() == "Darwin":
                print("（macOS 上 5000 端口默认被「AirPlay 接收器」占用）")
            print()
            server_port = fallback_port
            try:
                cfg['port'] = server_port
                save_config(cfg)
            except Exception as exc:
                print(f"⚠️ 端口写回 config.json 失败，本次运行仍使用 {server_port}: {exc}")

    # 3. 启动后台服务 
    # (数据库初始化 -> 加载缓存 -> 启动扫描器)
    # daemon=True 保证主程序退出时线程自动结束，防止僵尸进程

    # 3.0 数据目录独占锁：防止两个进程共用同一份 data/ 互相覆盖 ui_data.json。
    # 在 Debug 模式下，仅在真正的工作进程 (WERKZEUG_RUN_MAIN="true") 中加锁，
    # 避免 Watcher 进程与工作进程互相冲突。
    if not debug_mode or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        from core.config import DATA_DIR
        from core.data.data_dir_lock import acquire_data_directory_lock

        if not acquire_data_directory_lock(DATA_DIR):
            print(f"\n{'='*60}")
            print("❌ 启动失败：数据目录已被另一个 ST Manager 实例占用！")
            print(f"{'='*60}")
            print(f"数据目录: {DATA_DIR}")
            print("同时运行多个实例会互相覆盖本地备注、链接与标签分类等数据。")
            print("\n请尝试：")
            print(" - 关闭已运行的其他 ST Manager 窗口/进程。")
            print(" - 若确认没有实例在运行，可删除数据目录下的 st_manager.lock 后重试。")
            print(f"{'='*60}\n")
            notify_startup_failure(
                f"数据目录已被另一个 ST Manager 实例占用：\n{DATA_DIR}\n"
                "请先关闭已运行的 ST Manager。"
            )
            if platform.system() == "Windows":
                os.system("pause")
            sys.exit(1)

    # 在 Debug 模式下，仅在 Reload 子进程 (WERKZEUG_RUN_MAIN="true") 中启动后台服务
    # 避免在 Watcher 进程中重复启动
    if not debug_mode or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        threading.Thread(target=init_services, daemon=True).start()

    # 4. 自动打开浏览器
    # 仅在非 Reload 模式下执行，防止开发时每次保存代码都弹窗
    # WERKZEUG_RUN_MAIN 是 Flask debug 模式下的环境变量
    if os.environ.get("WERKZEUG_RUN_MAIN") != "true":
        # 延迟 0.5 秒打开，确保 Flask 已经开始监听
        threading.Timer(0.5, open_ui_in_browser, args=(server_host, server_port)).start()

    # 5. 创建并运行 Flask 应用
    print(f"🚀 服务器已启动: http://{server_host}:{server_port}")
    if debug_mode:
        print(f"🔧 Debug 模式: 开启 (Hot Reload enabled)")
    
    app = create_app()

    # 打包后的 macOS 应用走 Cocoa 事件循环：常驻程序坞，且程序坞「退出」/⌘Q
    # 能真正结束进程（连带 Flask 服务与后台扫描线程）。Debug 模式保留原行为。
    if getattr(sys, 'frozen', False) and sys.platform == 'darwin' and not debug_mode:
        try:
            run_macos_app(app, server_host, server_port)
            sys.exit(0)
        except ImportError as exc:
            print(f"⚠️ 未安装 pyobjc（{exc}），回退为无窗口模式：程序坞退出可能没有反应。")

    try:
        # use_reloader=False: 在生产或打包环境建议关闭，避免双进程导致 Context 初始化两次
        # debug=False: 生产环境关闭
        app.run(debug=debug_mode, host=server_host, port=server_port, use_reloader=debug_mode)
    except OSError as e:
        if "Address already in use" in str(e):
            print(f"❌ 端口 {server_port} 被占用。")
        else:
            print(f"❌ 服务器异常退出: {e}")
        notify_startup_failure(f"服务器启动失败: {e}")
        
        if platform.system() == "Windows":
            os.system("pause")
