"""APNG（多帧 PNG）角色卡的元数据读取契约。

Pillow 在多帧 PNG 上只把帧信息放进 ``img.info``（loop / duration / fcTL…），
取不到 chara / ccv3 文本块，于是这类卡会被判成「不是卡片」而漏出索引。
SillyTavern 自己的解析器是按块读的，同样的文件在 ST 里完全正常 —— 所以这里
用逐块扫描做兜底。
"""

import base64
import json
import sys
from pathlib import Path

from PIL import Image, PngImagePlugin

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.utils.image import (
    CARD_INFO_NOT_A_CARD,
    CARD_INFO_OK,
    extract_card_info_with_status,
    read_png_card_text,
)

CARD = {
    'spec': 'chara_card_v3',
    'spec_version': '3.0',
    'name': '测试卡',
    'description': '用于测试的卡片',
    'first_mes': '你好',
    'data': {'name': '测试卡', 'description': '用于测试的卡片', 'first_mes': '你好'},
}
CARD_B64 = base64.b64encode(json.dumps(CARD, ensure_ascii=False).encode('utf-8')).decode('ascii')


def _append_text_chunks(path, texts):
    """把 tEXt 块插到 IEND 之前 —— 与 SillyTavern 自身 write() 的落块位置一致。

    真实数据里出问题的卡正是这种布局：文本块在图像数据之后，Pillow 在 APNG 上
    不会读到它们。
    """
    data = path.read_bytes()
    assert data[:8] == b'\x89PNG\r\n\x1a\n'
    chunks, offset = [], 8
    while offset + 8 <= len(data):
        length = int.from_bytes(data[offset:offset + 4], 'big')
        chunks.append(data[offset:offset + 12 + length])
        offset += 12 + length
        if chunks[-1][4:8] == b'IEND':
            break

    extra = b''
    for keyword, text in texts:
        body = keyword.encode('latin-1') + b'\x00' + text.encode('latin-1')
        extra += len(body).to_bytes(4, 'big') + b'tEXt' + body + b'\x00\x00\x00\x00'

    out = data[:8] + b''.join(chunks[:-1]) + extra + chunks[-1]
    path.write_bytes(out)


def _write_apng(path, with_card=True, chunks_at_end=True):
    """写一个两帧的 APNG；with_card 时带上 chara / ccv3 文本块。"""
    frames = [
        Image.new('RGBA', (64, 64), (200, 60, 60, 255)),
        Image.new('RGBA', (64, 64), (60, 120, 200, 255)),
    ]
    info = PngImagePlugin.PngInfo()
    if with_card and not chunks_at_end:
        info.add_text('chara', CARD_B64)
        info.add_text('ccv3', CARD_B64)
    frames[0].save(
        path, 'PNG', save_all=True, append_images=frames[1:],
        duration=100, loop=0, pnginfo=info,
    )
    if with_card and chunks_at_end:
        _append_text_chunks(path, [('chara', CARD_B64), ('ccv3', CARD_B64)])


def test_pillow_info_really_loses_card_data_on_apng(tmp_path):
    """前提校验：尾部数据块的 APNG 上 Pillow 拿不到卡数据，兜底才有意义。"""
    path = tmp_path / 'anim.png'
    _write_apng(path)

    with Image.open(path) as img:
        img.load()
        assert getattr(img, 'n_frames', 1) > 1
        assert 'chara' not in (img.info or {})

    assert read_png_card_text(str(path)) == CARD_B64


def test_extract_card_info_accepts_apng_card(tmp_path):
    path = tmp_path / 'anim.png'
    _write_apng(path)

    info, status = extract_card_info_with_status(str(path))

    assert status == CARD_INFO_OK
    assert info and info.get('name') == '测试卡'


def test_apng_without_card_data_is_still_not_a_card(tmp_path):
    path = tmp_path / 'plain_anim.png'
    _write_apng(path, with_card=False)

    info, status = extract_card_info_with_status(str(path))

    assert info is None
    assert status == CARD_INFO_NOT_A_CARD


def test_read_png_card_text_ignores_non_png(tmp_path):
    path = tmp_path / 'not_a_png.png'
    path.write_bytes(b'not a png at all')

    assert read_png_card_text(str(path)) is None
