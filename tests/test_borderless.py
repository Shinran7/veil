"""Borderless window drag and resize zones."""

from main import borderless_drag_zone, borderless_resize_zone


def test_resize_zone_edges() -> None:
    size = (800, 600)
    assert borderless_resize_zone((799, 300), size) == "r"
    assert borderless_resize_zone((400, 599), size) == "b"
    assert borderless_resize_zone((799, 599), size) == "br"
    assert borderless_resize_zone((400, 300), size) is None


def test_drag_zone_is_top_bar_only() -> None:
    size = (800, 600)
    assert borderless_drag_zone((200, 20), size) is True
    assert borderless_drag_zone((200, 80), size) is False
    assert borderless_drag_zone((799, 20), size) is False