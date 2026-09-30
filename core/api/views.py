import os
import platform
from flask import Blueprint, render_template, send_from_directory

# === 基础设施 ===
from core.config import INTERNAL_DIR

# 定义蓝图
bp = Blueprint('views', __name__)


def _platform_ui_hints():
    """给模板用的路径示例与文件管理器名称：各平台显示各自的写法。

    设置页里有不少「照着填」的目录示例。之前一律给 Windows 写法（D:/...），
    macOS 用户照着填只会得到一个本机不存在的路径。
    """
    home = os.path.expanduser('~')
    if platform.system() == 'Darwin':
        return {
            'file_manager': '访达',
            'home': home,
            'st_root': f'{home}/SillyTavern',
            'st_openai': f'{home}/SillyTavern/data/default-user/OpenAI Settings',
            'tt_data': f'{home}/Library/Application Support/TauriTavern/data',
            'abs_roots': f'{home}/SillyTavern/assets\n/Volumes/Data/resources',
        }
    if platform.system() == 'Windows':
        return {
            'file_manager': '资源管理器',
            'home': home,
            'st_root': 'D:/SillyTavern',
            'st_openai': 'D:/SillyTavern/data/default-user/OpenAI Settings',
            'tt_data': 'D:/TauriTavern/data',
            'abs_roots': 'D:\\SillyTavern\\assets\nE:\\resources',
        }
    return {
        'file_manager': '文件管理器',
        'home': home,
        'st_root': f'{home}/SillyTavern',
        'st_openai': f'{home}/SillyTavern/data/default-user/OpenAI Settings',
        'tt_data': f'{home}/TauriTavern/data',
        'abs_roots': f'{home}/SillyTavern/assets\n/opt/resources',
    }


@bp.route('/')
def index():
    """
    渲染单页应用入口 (index.html)。
    Flask 会自动在 App 初始化时配置的 template_folder 中查找此文件。
    """
    return render_template('index.html', ui_hints=_platform_ui_hints())

@bp.route('/favicon.ico')
def favicon():
    """
    处理网站图标请求。
    显式指向内部资源目录，兼容 PyInstaller 打包后的临时路径 (sys._MEIPASS)。
    """
    # 确保路径分隔符在 Windows/Linux 下均正确
    static_brand_dir = os.path.join(INTERNAL_DIR, 'static', 'images', 'brand')
    
    return send_from_directory(
        static_brand_dir,
        'stm-mark.png',
        mimetype='image/png'
    )


@bp.route('/img/<path:filename>')
def sillytavern_preview_image(filename):
    """Serve the relative image paths used by the vendored ST preview shell."""
    preview_image_dir = os.path.join(INTERNAL_DIR, 'static', 'vendor', 'sillytavern', 'img')
    return send_from_directory(preview_image_dir, filename)
