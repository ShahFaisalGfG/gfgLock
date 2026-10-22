"""Draw every gfgLock icon from code: the window, taskbar and About sizes, the splash logo, the readme
logo, and gfgLock.ico for the exe, the installers, and the Explorer menu.

gfgLock and CC-Gen-Ultimate share one icon family: a rounded tile with a diagonal gradient and a
bold white symbol, no text, so the icon stays recognisable at 16 px. Each app has its own colours
and symbol; CC-Gen-Ultimate's scripts/make_icons.py draws the same tile.

Run from the repository root:  python scripts/make_icons.py
"""

import os
import struct
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QPointF, QRectF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QGuiApplication, QImage, QImageWriter, QLinearGradient, QPainter, QPainterPath, QPen  # noqa: E402

ICON_DIR = os.path.join("gfglock", "assets", "icons")
TOP, BOTTOM = "#3b82f6", "#4338ca"  # blue to indigo
PNGS = {
    "Square44x44Logo.targetsize-16.png": 16,
    "Square44x44Logo.targetsize-20.png": 20,
    "Square44x44Logo.targetsize-24.png": 24,
    "Square44x44Logo.targetsize-32.png": 32,
    "Square44x44Logo.targetsize-48.png": 48,
    "Square44x44Logo.targetsize-256.png": 256,
    "Square71x71Logo.scale-100.png": 71,
    "Square150x150Logo.scale-100.png": 150,
    "Square310x310Logo.scale-100.png": 310,
    "StoreLogo.scale-150.png": 150,
    "gfgLock.png": 1024,
}
ICO_NAME = "gfgLock.ico"
ICO_SIZES = (16, 20, 24, 32, 40, 48, 64, 96, 128, 256)


def draw_tile(p: QPainter, size: float, top: str, bottom: str) -> None:
    """The shared shape: a rounded square with a diagonal gradient and a thin transparent margin."""
    grad = QLinearGradient(QPointF(0, 0), QPointF(size, size))
    grad.setColorAt(0, QColor(top))
    grad.setColorAt(1, QColor(bottom))
    inset = size * 0.04
    path = QPainterPath()
    path.addRoundedRect(QRectF(inset, inset, size - 2 * inset, size - 2 * inset), size * 0.22, size * 0.22)
    p.fillPath(path, grad)


def draw_padlock(p: QPainter, s: float) -> None:
    """A bold white padlock; the keyhole is cut out from 24 px up, where it can be seen."""
    white = QColor("white")
    p.setPen(QPen(white, s * 0.085, Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap))
    p.setBrush(Qt.BrushStyle.NoBrush)
    shackle = QPainterPath()
    shackle.moveTo(s * 0.355, s * 0.47)
    shackle.lineTo(s * 0.355, s * 0.36)
    shackle.arcTo(QRectF(s * 0.355, s * 0.215, s * 0.29, s * 0.29), 180, -180)
    shackle.lineTo(s * 0.645, s * 0.47)
    p.drawPath(shackle)
    body = QPainterPath()
    body.addRoundedRect(QRectF(s * 0.27, s * 0.45, s * 0.46, s * 0.34), s * 0.06, s * 0.06)
    if s >= 24:
        hole = QPainterPath()
        hole.addEllipse(QPointF(s * 0.5, s * 0.585), s * 0.045, s * 0.045)
        hole.addRect(QRectF(s * 0.485, s * 0.6, s * 0.03, s * 0.09))
        body = body.subtracted(hole)
    p.setPen(Qt.PenStyle.NoPen)
    p.fillPath(body, white)


def render(size: int) -> QImage:
    """The icon at one exact size, drawn as vectors so small sizes stay sharp."""
    img = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    draw_tile(p, size, TOP, BOTTOM)
    draw_padlock(p, size)
    p.end()
    return img.convertToFormat(QImage.Format.Format_ARGB32)


def png_bytes(img: QImage) -> bytes:
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    QImageWriter(buffer, QByteArray(b"png")).write(img)
    buffer.close()
    return bytes(data.data())


def write_ico(path: str, sizes: tuple[int, ...]) -> None:
    """A Windows .ico with one PNG-compressed image per size (supported since Windows Vista)."""
    images = [png_bytes(render(size)) for size in sizes]
    offset = 6 + 16 * len(sizes)
    header = struct.pack("<HHH", 0, 1, len(sizes))
    entries = b""
    for size, data in zip(sizes, images):
        dim = 0 if size >= 256 else size  # 0 means 256 in the directory entry
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
    with open(path, "wb") as fh:
        fh.write(header + entries + b"".join(images))


def main() -> None:
    QGuiApplication(sys.argv[:1])
    for name, size in PNGS.items():
        render(size).save(os.path.join(ICON_DIR, name))  # PNG, from the file name
    write_ico(os.path.join(ICON_DIR, ICO_NAME), ICO_SIZES)
    print(f"Wrote {len(PNGS)} PNGs and {ICO_NAME} to {ICON_DIR}")


if __name__ == "__main__":
    main()
