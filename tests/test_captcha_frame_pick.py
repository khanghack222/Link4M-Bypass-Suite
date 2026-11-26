#!/usr/bin/env python3
"""Unit checks for the reCAPTCHA frame pick and token pick.

Trang link4m dựng **hai** widget reCAPTCHA. Bframe của widget ẩn nằm ở
`top:-9999px` và không có tile; chọn nhầm frame đó thì engine không mở được
chế độ audio, không chụp được lưới, và chờ index thủ công vô ích cho tới hết
hạn. Hai hàm dưới đây phải luôn chọn widget đang hiển thị.

Không cần Chrome: page/frame được giả lập đúng những method mà code gọi.
"""

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "src", "core"))

from captcha_audio import find_challenge, token_now  # noqa: E402

PASSED = []
FAILED = []


def check(name, condition, detail=""):
    if condition:
        PASSED.append(name)
        print(f"[PASS] {name}")
    else:
        FAILED.append(name)
        print(f"[FAIL] {name} {detail}")


class FakeBox:
    def __init__(self, x, y, width, height):
        self._box = {"x": x, "y": y, "width": width, "height": height}

    def bounding_box(self):
        return dict(self._box)


class FakeFrameElement:
    def __init__(self, box):
        self._box = box

    def bounding_box(self):
        return self._box.bounding_box() if self._box else None


class FakeLocator:
    def __init__(self, count):
        self._count = count

    def count(self):
        return self._count


class FakeFrame:
    def __init__(self, url, box, grid=0, audio=0, tiles=0):
        self.url = url
        self._box = box
        self._grid = grid
        self._audio = audio
        self._tiles = tiles

    def locator(self, selector):
        if "rc-imageselect-target" in selector:
            return FakeLocator(self._grid)
        if "rc-audiochallenge-response-field" in selector:
            return FakeLocator(self._audio)
        if "rc-imageselect-tile" in selector:
            return FakeLocator(self._tiles)
        return FakeLocator(0)

    def frame_element(self):
        return FakeFrameElement(self._box)


class FakePage:
    def __init__(self, frames, viewport=None, tokens=None):
        self.frames = frames
        self.viewport_size = viewport or {"width": 1280, "height": 800}
        self._tokens = tokens or []

    def evaluate(self, *_args, **_kwargs):
        return self._tokens


BFRAME = "https://www.google.com/recaptcha/api2/bframe?hl=en&v=x&k=y"


def visible_frame(**kwargs):
    return FakeFrame(BFRAME, FakeBox(532, 120, 400, 580), **kwargs)


def hidden_frame(**kwargs):
    return FakeFrame(BFRAME, FakeBox(532, -9999, 400, 580), **kwargs)


def main():
    # 1. Widget ẩn không có tile đứng trước trong DOM — frame hiển thị phải thắng.
    page = FakePage([hidden_frame(grid=1), visible_frame(audio=1)], tokens=[])
    picked = find_challenge(page)
    check("chọn frame hiển thị thay vì frame ẩn", picked is not None)
    check("frame chọn đúng là frame hiển thị", picked is page.frames[1])

    # 2. Lưới đã render tile trên frame hiển thị, frame ẩn cũng có tile.
    page = FakePage([hidden_frame(grid=1, tiles=9), visible_frame(grid=1, tiles=9)])
    picked = find_challenge(page)
    check("frame hiển thị có tile được ưu tiên", picked is page.frames[1])

    # 3. Chỉ còn widget ẩn (khung lưới rỗng, không tile, không ô audio).
    page = FakePage([hidden_frame(grid=1)])
    check("frame ẩn rỗng -> None", find_challenge(page) is None)

    # 3b. Thử thách thật bị đặt ngoài viewport (headless) vẫn phải được chọn.
    page = FakePage([hidden_frame(grid=1), hidden_frame(grid=1, tiles=9)])
    check("frame ngoài viewport có tile -> vẫn chọn", find_challenge(page) is page.frames[1])

    # 4. Không có bframe nào.
    page = FakePage([FakeFrame("https://link4m.net/go/abc", FakeBox(0, 0, 1280, 800))])
    check("không có bframe -> None", find_challenge(page) is None)

    # 5. Token: widget hiển thị rỗng, widget ẩn đã có token -> không lấy token ẩn.
    tokens = [
        {"v": "token-cua-widget-an-dai-hon-nhieu", "visible": False},
        {"v": "", "visible": True},
    ]
    check("bỏ token của widget ẩn", token_now(FakePage([], tokens=tokens)) == "")

    # 6. Token hiển thị tồn tại -> lấy nó, kể cả khi token ẩn dài hơn.
    tokens = [
        {"v": "x" * 100, "visible": False},
        {"v": "token-dung", "visible": True},
    ]
    check(
        "ưu tiên token của widget hiển thị",
        token_now(FakePage([], tokens=tokens)) == "token-dung",
    )

    # 7. Không widget nào trong viewport (reCAPTCHA vô hình) -> hành vi cũ.
    tokens = [{"v": "ngan", "visible": False}, {"v": "dai-hon-nhieu", "visible": False}]
    check(
        "fallback giữ textarea dài nhất",
        token_now(FakePage([], tokens=tokens)) == "dai-hon-nhieu",
    )

    # 8. Không có textarea nào.
    check("không có token -> rỗng", token_now(FakePage([], tokens=[])) == "")

    print()
    if FAILED:
        print(f"=== {len(FAILED)} FAIL / {len(PASSED) + len(FAILED)} CHECK ===")
        return 1
    print(f"=== CAPTCHA FRAME PICK: {len(PASSED)}/{len(PASSED)} PASSED ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
