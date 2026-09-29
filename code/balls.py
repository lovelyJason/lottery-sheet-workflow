"""Mark-six ball color, year zodiac, and number sprites."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPixmap

ASSETS = Path(__file__).resolve().parent / "assets" / "balls"
ANIMALS = "鼠牛虎兔龙蛇马羊猴鸡狗猪"
# Lunar new year. 2020 is 鼠; before that day's festival the previous animal still applies.
NEW_YEAR = {
    2024: date(2024, 2, 10),
    2025: date(2025, 1, 29),
    2026: date(2026, 2, 17),
    2027: date(2027, 2, 6),
    2028: date(2028, 1, 26),
    2029: date(2029, 2, 13),
    2030: date(2030, 2, 3),
    2031: date(2031, 1, 23),
    2032: date(2032, 2, 11),
}
RED_NUMBERS = {1, 2, 7, 8, 12, 13, 18, 19, 23, 24, 29, 30, 34, 35, 40, 45, 46}
BLUE_NUMBERS = {3, 4, 9, 10, 14, 15, 20, 25, 26, 31, 36, 37, 41, 42, 47, 48}
GREEN_NUMBERS = {5, 6, 11, 16, 17, 21, 22, 27, 28, 32, 33, 38, 39, 43, 44, 49}
HOT = "#E03131"
BALL_SIZE = 24
_BASES: dict[str, QPixmap] = {}
_SPRITES: dict[int, QPixmap] = {}


def ball_color(number: int) -> str:
    if number in BLUE_NUMBERS:
        return "blue"
    if number in GREEN_NUMBERS:
        return "green"
    return "red"


def is_hot(text: object) -> bool:
    """双 and 大 are red in the results table; 单 and 小 stay dark."""
    return text in ("双", "大")


def zodiac_year(day: date) -> str:
    year = day.year
    festival = NEW_YEAR.get(year)
    if festival is not None and day < festival:
        year -= 1
    elif festival is None and day.month == 1:
        year -= 1
    return ANIMALS[(year - 2020) % 12]


def number_zodiac(number: int, day: date) -> str:
    start = ANIMALS.index(zodiac_year(day))
    return ANIMALS[(start - (number - 1)) % 12]


def draw_day(record: dict) -> date:
    value = record.get("open_time")
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(value).date()
        except (OverflowError, OSError, ValueError):
            pass
    return date.today()


def parse_numbers(value: object) -> list[int]:
    if isinstance(value, str):
        parts = value.replace(" ", ",").split(",")
    elif isinstance(value, list):
        parts = value
    else:
        return []
    numbers = []
    for part in parts:
        try:
            number = int(str(part).strip())
        except ValueError:
            continue
        if 1 <= number <= 49:
            numbers.append(number)
    return numbers


def ball_pixmap(number: int) -> QPixmap:
    cached = _SPRITES.get(number)
    if cached is not None:
        return cached
    ratio = 2
    side = BALL_SIZE * ratio
    sprite = QPixmap(side, side)
    sprite.setDevicePixelRatio(ratio)
    sprite.fill(Qt.transparent)
    painter = QPainter(sprite)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setRenderHint(QPainter.SmoothPixmapTransform)
    painter.drawPixmap(0, 0, BALL_SIZE, BALL_SIZE, _base(ball_color(number)))
    font = QFont("PingFang SC", 8)
    font.setBold(True)
    painter.setFont(font)
    painter.setPen(Qt.white)
    painter.drawText(QRect(0, 0, BALL_SIZE, BALL_SIZE), Qt.AlignCenter, f"{number:02d}")
    painter.end()
    _SPRITES[number] = sprite
    return sprite


def _base(color: str) -> QPixmap:
    cached = _BASES.get(color)
    if cached is not None:
        return cached
    path = ASSETS / f"{color}.png"
    if path.exists():
        image = QImage(str(path))
        pixmap = QPixmap.fromImage(image)
    else:
        pixmap = _flat_ball(color)
    _BASES[color] = pixmap
    return pixmap


def _flat_ball(color: str) -> QPixmap:
    fills = {"red": "#E23B3B", "blue": "#2F6FE0", "green": "#1F9D55"}
    side = 128
    pixmap = QPixmap(side, side)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(fills.get(color, fills["red"])))
    painter.drawEllipse(0, 0, side - 1, side - 1)
    painter.setBrush(QColor(255, 255, 255, 90))
    painter.drawEllipse(28, 18, 36, 28)
    painter.end()
    return pixmap
