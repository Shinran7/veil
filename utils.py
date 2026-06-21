"""Vector math and geometry helpers."""

from __future__ import annotations

import math
from typing import Iterable

Vec2 = tuple[float, float]


def vec_add(a: Vec2, b: Vec2) -> Vec2:
    return (a[0] + b[0], a[1] + b[1])


def vec_sub(a: Vec2, b: Vec2) -> Vec2:
    return (a[0] - b[0], a[1] - b[1])


def vec_scale(v: Vec2, s: float) -> Vec2:
    return (v[0] * s, v[1] * s)


def vec_len(v: Vec2) -> float:
    return math.hypot(v[0], v[1])


def vec_norm(v: Vec2) -> Vec2:
    length = vec_len(v)
    if length < 1e-9:
        return (0.0, 0.0)
    return (v[0] / length, v[1] / length)


def vec_from_angle(angle: float, magnitude: float = 1.0) -> Vec2:
    return (math.cos(angle) * magnitude, math.sin(angle) * magnitude)


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def wrap_position(pos: Vec2, rect: tuple[float, float, float, float]) -> Vec2:
    """Toroidal wrap — exit one edge, enter the opposite."""
    x, y, w, h = rect
    px, py = pos
    if px < x:
        px += w
    elif px > x + w:
        px -= w
    if py < y:
        py += h
    elif py > y + h:
        py -= h
    return (px, py)


def wrapped_delta(
    from_pos: Vec2, to_pos: Vec2, rect: tuple[float, float, float, float]
) -> Vec2:
    """Shortest displacement from from_pos to to_pos across toroidal edges."""
    x, y, w, h = rect
    dx = to_pos[0] - from_pos[0]
    dy = to_pos[1] - from_pos[1]
    if dx > w * 0.5:
        dx -= w
    elif dx < -w * 0.5:
        dx += w
    if dy > h * 0.5:
        dy -= h
    elif dy < -h * 0.5:
        dy += h
    return (dx, dy)


def wrapped_distance(
    from_pos: Vec2, to_pos: Vec2, rect: tuple[float, float, float, float]
) -> float:
    return vec_len(wrapped_delta(from_pos, to_pos, rect))


def rotate_point(point: Vec2, angle: float, origin: Vec2 = (0.0, 0.0)) -> Vec2:
    ox, oy = origin
    px, py = point
    dx, dy = px - ox, py - oy
    c, s = math.cos(angle), math.sin(angle)
    return (ox + dx * c - dy * s, oy + dx * s + dy * c)


def world_polygon(hull: Iterable[Vec2], pos: Vec2, angle: float) -> list[Vec2]:
    return [vec_add(rotate_point(p, angle), pos) for p in hull]


def point_in_rect(point: Vec2, rect: tuple[float, float, float, float]) -> bool:
    x, y = point
    rx, ry, rw, rh = rect
    return rx <= x <= rx + rw and ry <= y <= ry + rh


def circle_rect_collision(
    center: Vec2, radius: float, rect: tuple[float, float, float, float]
) -> bool:
    rx, ry, rw, rh = rect
    nearest_x = clamp(center[0], rx, rx + rw)
    nearest_y = clamp(center[1], ry, ry + rh)
    return vec_len((center[0] - nearest_x, center[1] - nearest_y)) <= radius


def push_circle_out_of_rect(
    center: Vec2, radius: float, rect: tuple[float, float, float, float]
) -> Vec2:
    """Return a position nudged so the circle clears the rectangle."""
    cx, cy = center
    rx, ry, rw, rh = rect
    if not circle_rect_collision(center, radius, rect):
        return center
    if rx <= cx <= rx + rw and ry <= cy <= ry + rh:
        to_left = cx - rx
        to_right = rx + rw - cx
        to_top = cy - ry
        to_bottom = ry + rh - cy
        smallest = min(to_left, to_right, to_top, to_bottom)
        if smallest == to_left:
            return (rx - radius - 2, cy)
        if smallest == to_right:
            return (rx + rw + radius + 2, cy)
        if smallest == to_top:
            return (cx, ry - radius - 2)
        return (cx, ry + rh + radius + 2)
    nx = clamp(cx, rx, rx + rw)
    ny = clamp(cy, ry, ry + rh)
    dx, dy = cx - nx, cy - ny
    dist = vec_len((dx, dy))
    if dist < 1e-6:
        return center
    push = (radius - dist + 2) / dist
    return (cx + dx * push, cy + dy * push)


def segment_circle_intersect(
    start: Vec2, end: Vec2, center: Vec2, radius: float
) -> bool:
    """True if line segment intersects a circle."""
    ab = vec_sub(end, start)
    ac = vec_sub(center, start)
    ab_len_sq = ab[0] * ab[0] + ab[1] * ab[1]
    if ab_len_sq < 1e-9:
        return vec_len(vec_sub(center, start)) <= radius
    t = clamp((ac[0] * ab[0] + ac[1] * ab[1]) / ab_len_sq, 0.0, 1.0)
    closest = (start[0] + ab[0] * t, start[1] + ab[1] * t)
    return vec_len(vec_sub(center, closest)) <= radius


def push_circle_out_of_circle(
    pos: Vec2, radius: float, other_center: Vec2, other_radius: float
) -> Vec2:
    """Nudge a circle so it clears another circle."""
    dx, dy = vec_sub(pos, other_center)
    dist = vec_len((dx, dy))
    min_dist = radius + other_radius + 2
    if dist >= min_dist or dist < 1e-6:
        return pos
    push = (min_dist - dist) / dist
    return (pos[0] + dx * push, pos[1] + dy * push)


def line_circle_intersect(
    start: Vec2, end: Vec2, center: Vec2, radius: float
) -> bool:
    """Alias for segment-circle hit tests."""
    return segment_circle_intersect(start, end, center, radius)