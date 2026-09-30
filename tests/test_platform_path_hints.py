"""目录示例与 SillyTavern 探测路径的平台契约。

背景：设置页里的目录示例以前一律是 Windows 写法（`D:/SillyTavern`），
探测候选里也只有 `D:\\`、`/opt` 这类路径 —— macOS 用户照着填只会得到
一个本机不存在的目录，自动探测也永远找不到 `~/st/SillyTavern` 这种位置。
"""

import os
import re
import sys
from pathlib import Path

import pytest
from flask import Flask

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.api import views as views_api
from core.config import BASE_DIR, _resolve_dir, normalize_user_path
from core.services import st_client as st_client_module

DRIVE_LETTER = re.compile(r'^[A-Za-z]:')


def _render_index():
    app = Flask(
        __name__,
        template_folder=str(ROOT / 'templates'),
        static_folder=str(ROOT / 'static'),
    )
    app.register_blueprint(views_api.bp)
    return app.test_client().get('/').get_data(as_text=True)


def test_detect_st_path_finds_install_root_via_candidates(tmp_path, monkeypatch):
    """探测逻辑应能通过候选列表找到真实的安装根目录。"""
    st_root = tmp_path / 'SillyTavern'
    (st_root / 'data' / 'default-user').mkdir(parents=True)
    monkeypatch.setattr(st_client_module, 'ST_PATH_CANDIDATES', [str(st_root)])

    client = st_client_module.STClient(st_data_dir='', st_user_handle='default-user')

    assert client.detect_st_path() == str(st_root)


def test_candidates_are_platform_specific():
    """候选路径应只包含当前平台的写法。"""
    candidates = st_client_module.ST_PATH_CANDIDATES

    assert candidates
    if sys.platform == 'win32':
        assert all('\\' in candidate for candidate in candidates)
    else:
        assert not any(':' in candidate or '\\' in candidate for candidate in candidates), candidates
        assert all(candidate.startswith('~') or candidate.startswith('/') for candidate in candidates), candidates


def test_normalize_user_path_expands_tilde_and_strips_quotes(tmp_path, monkeypatch):
    monkeypatch.setenv('HOME', str(tmp_path))

    assert normalize_user_path('~/SillyTavern') == f'{tmp_path}/SillyTavern'
    assert normalize_user_path('  "~/SillyTavern"  ') == f'{tmp_path}/SillyTavern'
    assert normalize_user_path('') == ''
    assert normalize_user_path(None) == ''


def test_directory_settings_accept_tilde_paths(tmp_path, monkeypatch):
    monkeypatch.setenv('HOME', str(tmp_path))

    # ~ 写法应被当作绝对路径，而不是拼到数据目录下面
    assert _resolve_dir({'cards_dir': '~/SillyTavern'}, 'cards_dir', 'x') == f'{tmp_path}/SillyTavern'
    # 相对路径行为保持不变
    assert _resolve_dir({'cards_dir': 'data/library/characters'}, 'cards_dir', 'x') == os.path.join(
        BASE_DIR, 'data/library/characters'
    )


def test_st_path_validation_accepts_tilde_paths(tmp_path, monkeypatch):
    monkeypatch.setenv('HOME', str(tmp_path))
    (tmp_path / 'SillyTavern' / 'data' / 'default-user').mkdir(parents=True)

    client = st_client_module.STClient(st_data_dir='', st_user_handle='default-user')

    assert client._validate_st_path('~/SillyTavern') is True
    assert client.get_install_root('~/SillyTavern') == str(tmp_path / 'SillyTavern')


@pytest.mark.skipif(sys.platform != 'darwin', reason='macOS 专用路径示例')
def test_macos_candidates_cover_common_install_locations():
    candidates = st_client_module.ST_PATH_CANDIDATES

    # 工作目录下与家目录下的克隆是最常见的两种放法
    assert '~/st/SillyTavern' in candidates
    assert '~/SillyTavern' in candidates
    assert '/Applications/SillyTavern' in candidates


@pytest.mark.skipif(sys.platform != 'darwin', reason='macOS 专用文案')
def test_macos_ui_hints_use_posix_examples():
    hints = views_api._platform_ui_hints()

    assert hints['file_manager'] == '访达'
    for key in ('st_root', 'st_openai', 'tt_data', 'abs_roots'):
        lines = hints[key].split('\n')
        assert lines
        for line in lines:
            assert line.startswith('/'), (key, line)
            assert not DRIVE_LETTER.match(line), (key, line)


@pytest.mark.skipif(sys.platform != 'darwin', reason='macOS 专用文案')
def test_index_page_renders_macos_examples():
    html = _render_index()

    assert '在访达中打开角色卡目录' in html
    assert 'D:/SillyTavern' not in html
    assert 'D:\\SillyTavern' not in html
    assert f'{os.path.expanduser("~")}/SillyTavern' in html
