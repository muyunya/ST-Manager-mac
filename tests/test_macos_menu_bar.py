"""macOS 菜单栏构建的契约测试。

这些菜单是打包版唯一能触达「数据 / 缓存 / 日志」目录的入口（这些路径在
~/Library 下，访达默认看不到），因此标题、动作与目标目录都值得固定住。
"""

import os
import sys

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform != 'darwin', reason='macOS 专用（AppKit）'
)

AppKit = pytest.importorskip('AppKit')


class _DelegateStub:
    """占位 target：只需要能被 setTarget_ 接受。"""


def _build(folders):
    import app as app_module

    return app_module.build_macos_menu_bar('ST Manager Pro', _DelegateStub(), folders)


def test_menu_bar_has_app_and_folder_menus():
    menu_bar = _build([('打开数据目录', '/tmp/data')])
    assert menu_bar.numberOfItems() == 2

    app_menu = menu_bar.itemAtIndex_(0).submenu()
    titles = [app_menu.itemAtIndex_(i).title() for i in range(app_menu.numberOfItems())]
    assert titles == ['打开界面', '退出 ST Manager Pro']

    folder_menu = menu_bar.itemAtIndex_(1).submenu()
    assert folder_menu.title() == '文件夹'
    assert folder_menu.itemAtIndex_(0).title() == '打开数据目录'


def test_folder_items_carry_target_path_and_action():
    data_dir = os.path.expanduser('~/Library/Application Support/ST-Manager/data')
    cache_dir = os.path.expanduser('~/Library/Caches/ST-Manager')
    log_dir = os.path.expanduser('~/Library/Logs/ST-Manager')
    menu_bar = _build([
        ('打开数据目录', data_dir),
        ('打开缓存目录', cache_dir),
        ('打开日志', log_dir),
    ])

    folder_menu = menu_bar.itemAtIndex_(1).submenu()
    items = [folder_menu.itemAtIndex_(i) for i in range(folder_menu.numberOfItems())]
    assert [item.title() for item in items] == ['打开数据目录', '打开缓存目录', '打开日志']
    assert [item.representedObject() for item in items] == [data_dir, cache_dir, log_dir]
    assert all(item.action() == 'revealPath:' for item in items)


def test_quit_item_uses_terminate_action():
    menu_bar = _build([])
    app_menu = menu_bar.itemAtIndex_(0).submenu()
    quit_item = app_menu.itemAtIndex_(1)
    assert quit_item.action() == 'terminate:'
    assert quit_item.keyEquivalent() == 'q'
