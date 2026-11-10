"""Pantalla TFT del L75 (240x135, RGB565).

Subida de imagen/animacion (segun el driver oficial):

1. Cabecera, cmd 0xA5 (checksum BIT7) y luego leer respuesta (byte1 == 1 = listo):
     [0xA5, cuadro_actual, num_cuadros, retardo_ms, len0, len1, 0, chk,
      left, top, right, bottom, left>>8, top>>8, right>>8, bottom>>8, len2, len3]
   ``len`` = bytes de UN cuadro (uint32 LE repartido en 4,5,16,17).
   left/top/right/bottom = rectangulo con contenido (right/bottom exclusivos).
2. Por cada cuadro, paquetes cmd 0x25 (checksum BIT7):
     [0x25, cuadro, num_cuadros, retardo_ms, idx_lo, idx_hi, n_bytes, chk] + 56 bytes
   Los pixeles van por COLUMNAS (x exterior, y interior), RGB565 big-endian.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass

from . import protocol as P
from .i18n import t

W, H = P.LCD_WIDTH, P.LCD_HEIGHT


@dataclass
class Box:
    left: int
    top: int
    right: int   # exclusivo
    bottom: int  # exclusivo

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top


@dataclass
class Animation:
    frames: list  # list[PIL.Image.Image] RGB 240x135
    delay_ms: int


def _pil():
    try:
        from PIL import Image, ImageSequence  # noqa: F401
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(t("Pillow is missing: pip install Pillow (or sudo dnf install python3-pillow)")) from exc
    from PIL import Image, ImageSequence
    return Image, ImageSequence


def fit_image(img, mode: str = "contain", background=(0, 0, 0)):
    """Ajusta una imagen a 240x135. mode: contain | cover | stretch."""
    Image, _ = _pil()
    img = img.convert("RGBA")
    if mode == "stretch":
        fitted, ox, oy = img.resize((W, H), Image.LANCZOS), 0, 0
    else:
        sw, sh = img.size
        scale = (min if mode == "contain" else max)(W / sw, H / sh)
        nw, nh = max(1, round(sw * scale)), max(1, round(sh * scale))
        fitted = img.resize((nw, nh), Image.LANCZOS)
        ox, oy = (W - nw) // 2, (H - nh) // 2  # negativo = recorte (cover)
    canvas = Image.new("RGBA", (W, H), tuple(background) + (255,))
    canvas.paste(fitted, (ox, oy), fitted)
    return canvas.convert("RGB")


def load_animation(path: str, fit: str = "contain", delay_ms: int | None = None,
                   max_frames: int = P.LCD_MAX_FRAMES) -> Animation:
    """Carga PNG/JPG/GIF/WebP animado y lo prepara para la pantalla."""
    Image, ImageSequence = _pil()
    im = Image.open(path)
    frames, durations = [], []
    for fr in ImageSequence.Iterator(im):
        durations.append(int(fr.info.get("duration", im.info.get("duration", 100)) or 100))
        frames.append(fit_image(fr.copy(), fit))
    if not frames:
        raise ValueError(t("the image has no frames"))
    if delay_ms is None:
        delay_ms = int(statistics.median(durations)) if len(frames) > 1 else 0
    if len(frames) > max_frames:
        step = len(frames) / max_frames
        idx = [int(i * step) for i in range(max_frames)]
        frames = [frames[i] for i in idx]
        delay_ms = int(delay_ms * step)
    delay_ms = max(0, min(255, delay_ms))
    if len(frames) > 1:
        delay_ms = max(20, delay_ms)
    return Animation(frames, delay_ms)


def content_box(frames) -> Box:
    """Rectangulo que contiene todos los pixeles no negros (union de cuadros)."""
    boxes = [f.getbbox() for f in frames]
    boxes = [b for b in boxes if b]
    if not boxes:
        return Box(0, 0, W, H)
    return Box(min(b[0] for b in boxes), min(b[1] for b in boxes),
               max(b[2] for b in boxes), max(b[3] for b in boxes))


def rgb565_be(r: int, g: int, b: int) -> bytes:
    v = ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)
    return bytes(((v >> 8) & 0xFF, v & 0xFF))


def frame_to_rgb565(frame, box: Box) -> bytes:
    """Pixeles del rectangulo, por columnas, RGB565 big-endian."""
    px = frame.load()
    out = bytearray()
    for x in range(box.left, box.right):
        for y in range(box.top, box.bottom):
            r, g, b = px[x, y][:3]
            v = ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)
            out.append((v >> 8) & 0xFF)
            out.append(v & 0xFF)
    return bytes(out)


def header_packet(frame_count: int, delay_ms: int, data_len: int, box: Box, current_frame: int = 0) -> bytearray:
    b = P.packet(P.Cmd.GET_TFTLCD_DATA, current_frame, frame_count, delay_ms,
                 data_len & 0xFF, (data_len >> 8) & 0xFF, 0)
    b[8] = box.left & 0xFF
    b[9] = box.top & 0xFF
    b[10] = box.right & 0xFF
    b[11] = box.bottom & 0xFF
    b[12] = box.left >> 8
    b[13] = box.top >> 8
    b[14] = box.right >> 8
    b[15] = box.bottom >> 8
    b[16] = (data_len >> 16) & 0xFF
    b[17] = (data_len >> 24) & 0xFF
    return P.apply_checksum(b, P.Checksum.BIT7)


def data_packets(data: bytes, frame: int, frame_count: int, delay_ms: int):
    total = math.ceil(len(data) / 56)
    for i in range(total):
        chunk = data[i * 56:(i + 1) * 56]
        b = P.packet(P.Cmd.SET_TFTLCD_DATA, frame, frame_count, delay_ms, i & 0xFF, (i >> 8) & 0xFF, len(chunk),
                     data=chunk)
        yield P.apply_checksum(b, P.Checksum.BIT7)


def estimate_packets(anim: Animation) -> int:
    box = content_box(anim.frames)
    per = math.ceil(box.width * box.height * 2 / 56)
    return per * len(anim.frames)
