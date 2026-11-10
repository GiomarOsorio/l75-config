"""Sección Pantalla: imagen o GIF para la pantalla de 240 × 135 del teclado."""

from __future__ import annotations

import os
import time

from PySide6.QtCore import QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QImage, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QFileDialog, QFrame, QSizePolicy, QWidget

from ... import lcd
from ... import protocol as P
from .. import widgets as W
from ..theme import font, theme
from ..window import Page
from .common import section_label

FITS = [("Ajustar", "contain", "ajustar", "Se ve entera, con bandas negras arriba y abajo."),
        ("Rellenar", "cover", "rellenar", "Llena la pantalla y recorta lo que sobra."),
        ("Estirar", "stretch", "estirar", "Llena la pantalla deformando la imagen.")]
IMAGE_FILTER = "Imágenes (*.gif *.png *.jpg *.jpeg *.webp *.bmp);;Todos los archivos (*)"


def _pixmap(frame, rgb565: bool) -> QPixmap:
    if rgb565:
        lut = [v & 0xF8 for v in range(256)] + [v & 0xFC for v in range(256)] + [v & 0xF8 for v in range(256)]
        frame = frame.point(lut)
    data = frame.tobytes("raw", "RGB")
    img = QImage(data, frame.width, frame.height, frame.width * 3, QImage.Format_RGB888).copy()
    return QPixmap.fromImage(img)


def _fmt_time(s: float) -> str:
    s = round(s)
    return f"{s // 60} min {s % 60} s" if s >= 60 else f"{s} s"


class LcdView(QWidget):
    """Pantalla física: marco de 14 px, esquinas de 20 px y reflejo de cristal."""

    fileDropped = Signal(str)
    clicked = Signal()

    def __init__(self):
        super().__init__()
        self.pm: QPixmap | None = None
        self.drag_over = False
        self.setAcceptDrops(True)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.setMinimumHeight(200)
        theme().changed.connect(self.update)

    def hasHeightForWidth(self):  # noqa: N802
        return True

    def heightForWidth(self, w):  # noqa: N802
        return min(298, round(min(w, 508) * 270 / 480) + 28)

    def _screen_rect(self) -> QRectF:
        w = min(self.width() - 28, 480)
        h = w * 135 / 240
        if h > self.height() - 28:
            h = self.height() - 28
            w = h * 240 / 135
        return QRectF((self.width() - w) / 2, (self.height() - h) / 2, w, h)

    def paintEvent(self, _e):
        t = theme()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        s = self._screen_rect()
        if self.pm is None:
            r = s.adjusted(-14, -14, 14, 14)
            pen = QPen(t.c("accent" if self.drag_over else "border-strong"), 1.5, Qt.DashLine)
            p.setPen(pen)
            p.setBrush(t.c("accent-soft") if self.drag_over else t.c("surface-2"))
            p.drawRoundedRect(r.adjusted(1, 1, -1, -1), 12, 12)
            ic = t.pixmap("imagen", "text-2", 28)
            p.drawPixmap(int(r.center().x() - 14), int(r.center().y() - 40), ic)
            p.setPen(t.c("text-1"))
            p.setFont(font(14, 600))
            p.drawText(QRectF(r.left(), r.center().y() - 4, r.width(), 22), Qt.AlignCenter,
                       "Arrastra aquí una imagen o un GIF")
            p.setPen(t.c("text-2"))
            p.setFont(font(12))
            p.drawText(QRectF(r.left(), r.center().y() + 18, r.width(), 20), Qt.AlignCenter,
                       "o haz clic para elegir un archivo · se ajusta a 240 × 135 px")
            return
        bez = s.adjusted(-14, -14, 14, 14)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 70))
        p.drawRoundedRect(bez.adjusted(0, 10, 0, 10), 20, 20)
        p.setPen(QPen(t.c("lcd-edge"), 1))
        p.setBrush(t.c("lcd-bezel"))
        p.drawRoundedRect(bez, 20, 20)
        path = QPainterPath()
        path.addRoundedRect(s, 3, 3)
        p.setClipPath(path)
        p.setRenderHint(QPainter.SmoothPixmapTransform, False)
        p.drawPixmap(s, self.pm, QRectF(self.pm.rect()))
        g = QLinearGradient(s.topLeft(), s.topLeft() + (s.bottomRight() - s.topLeft()) * 0.4)
        g.setColorAt(0, QColor(255, 255, 255, 20))
        g.setColorAt(1, QColor(255, 255, 255, 0))
        p.fillRect(s, g)

    def mousePressEvent(self, e):
        if self.pm is None:
            self.clicked.emit()

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
            self.drag_over = True
            self.update()

    def dragLeaveEvent(self, e):
        self.drag_over = False
        self.update()

    def dropEvent(self, e):
        self.drag_over = False
        self.update()
        urls = e.mimeData().urls()
        if urls:
            self.fileDropped.emit(urls[0].toLocalFile())


class Thumb(QWidget):
    def __init__(self):
        super().__init__()
        self.pm = None
        self.setFixedSize(64, 36)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, 64, 36), 4, 4)
        p.setClipPath(path)
        p.fillRect(self.rect(), theme().c("lcd-bezel"))
        if self.pm:
            p.drawPixmap(QRectF(0, 0, 64, 36), self.pm, QRectF(self.pm.rect()))


class ScreenPage(Page):
    def __init__(self, win):
        super().__init__(win)
        self.path: str | None = None
        self.anim: lcd.Animation | None = None
        self.pixmaps: list[QPixmap] = []
        self.frame_i = 0
        self.playing = True
        self.task = None
        self.t_start = 0.0
        self.src_info = ""

        header = W.PageHeader("Pantalla", "Pon tu imagen o GIF en la pantalla de 240 × 135 px del teclado.")
        header.add(W.button("Sincronizar fecha y hora", "secondary", "reloj", on_click=self.sync_time))
        self.lay.addWidget(header)

        # --- vista previa
        pv, pl = W.card(padding=(18, 14, 18, 16), spacing=12)
        self.real = W.Switch()
        self.real.setToolTip("Muestra los colores como los verá el teclado (RGB565)")
        self.real.toggled.connect(lambda _on: self._rebuild_pixmaps())
        pl.addLayout(W.hbox(W.label("Vista previa", "sub"), W.label("a 2× · 480 × 270", "cap"), "stretch",
                            W.label("Píxeles reales (RGB565)", "body2"), self.real, spacing=10))
        self.lcdv = LcdView()
        self.lcdv.fileDropped.connect(self.open_path)
        self.lcdv.clicked.connect(self.choose)
        pl.addWidget(self.lcdv)
        self.b_play = W.button("", "ghost", "pausa", size="sm", tip="Pausa", on_click=self.toggle_play)
        self.frame_lbl = W.label("", "mono2")
        self.frame_meter = W.Meter(260)
        self.player = QWidget()
        W.hbox(self.b_play, self.frame_lbl, self.frame_meter, "stretch", spacing=12, parent=self.player)
        pl.addWidget(self.player)
        tail = W.label("alterna entre tu imagen y la pantalla por defecto (hora y batería).", "body2", wrap=True)
        note = W.hbox(W.label("En el teclado,", "body2"), W.kbd("Fn"), W.label("+", "body2"), W.kbd("Ctrl"), spacing=6)
        note.addWidget(tail, 1)
        pl.addLayout(note)
        pl.addStretch(1)

        # --- panel derecho
        side, sl = W.card(padding=(16, 14, 16, 16), spacing=10)
        side.setFixedWidth(330)
        sl.addWidget(section_label("Archivo"))
        self.thumb = Thumb()
        self.f_name = W.label("Ningún archivo", "strong")
        self.f_meta = W.label("GIF, PNG, JPG o WebP", "cap")
        sl.addLayout(W.hbox(self.thumb, W.vbox(self.f_name, self.f_meta, spacing=0), "stretch", spacing=10))
        self.b_change = W.button("Elegir imagen o GIF…", "secondary", "imagen", size="sm", on_click=self.choose)
        self.b_remove = W.button("Quitar", "ghost", size="sm", on_click=self.remove)
        sl.addLayout(W.hbox(self.b_change, self.b_remove, "stretch", spacing=8))
        sl.addSpacing(4)
        sl.addWidget(section_label("Ajuste"))
        self.fit = W.Segmented(block=True)
        for text, key, icon, _h in FITS:
            self.fit.add(text, key, icon=icon)
        self.fit.changed.connect(lambda _v: self.reload())
        self.fit_hint = W.label(FITS[0][3], "cap", wrap=True)
        sl.addWidget(self.fit)
        sl.addWidget(self.fit_hint)
        sl.addSpacing(4)
        self.fps = W.label("", "mono2")
        sl.addLayout(W.hbox(section_label("Retardo entre cuadros"), "stretch", self.fps))
        self.delay_sl = W.TickSlider(20, 255, ticks=False)
        self.delay = W.Stepper(20, 255, 80, "ms", buttons=False, width=36)
        self.delay_sl.setValue(80)
        self.delay_sl.valueChanged.connect(lambda v: self.delay.setValue(v))
        self.delay.valueChanged.connect(self._delay_changed)
        sl.addLayout(W.hbox(self.delay_sl, self.delay, spacing=12))
        sl.addSpacing(2)
        self.frames_meter = W.Meter(56)
        self.kv_frames = W.label("—", "kv-v")
        self.kv_area = W.label("—", "kv-v")
        self.kv_time = W.label("—", "kv-v")
        kvs = W.vbox(spacing=0)
        for i, (name, val, extra) in enumerate((("Cuadros", self.kv_frames, self.frames_meter),
                                                ("Área usada", self.kv_area, None),
                                                ("Subida estimada", self.kv_time, None))):
            row = QFrame()
            row.setProperty("kv", "last" if i == 2 else "true")
            row.setFixedHeight(34)
            W.hbox(W.label(name, "kv-l"), "stretch", extra, val, spacing=8, parent=row)
            kvs.addWidget(row)
        sl.addLayout(kvs)
        sl.addSpacing(8)
        # subir / estado de subida / bloqueado por BT
        self.b_upload = W.button("Subir a la pantalla", "primary", "guardar", size="lg", on_click=self.upload)
        self.up_hint = W.label("Mantén el cable conectado durante la subida.", "cap", wrap=True)
        self.normal_box = QWidget()
        W.vbox(self.b_upload, self.up_hint, spacing=8, parent=self.normal_box)
        sl.addWidget(self.normal_box)
        # bloqueado
        self.bt_box, bl = W.card("inner", padding=(14, 12, 14, 14), spacing=8)
        self.bt_box.setStyleSheet("QFrame[card='inner']{border-style: dashed;}")
        bl.addLayout(W.hbox(W.icon_label("inalambrico", "warning", 16),
                            W.label("La subida solo funciona por cable", "strong"), "stretch", spacing=8))
        bl.addWidget(W.label("Conecta el L75 con el cable USB-C para subir imágenes. La fecha y la hora sí se "
                             "sincronizan por Bluetooth.", "cap", wrap=True))
        b_lock = W.button("Subir a la pantalla", "secondary", "candado")
        W.disable_with_reason(b_lock, "Solo por cable USB-C")
        bl.addWidget(b_lock)
        sl.addWidget(self.bt_box)
        # en curso
        self.up_box, ul = W.card("inner", padding=(14, 12, 14, 14), spacing=10)
        self.up_title = W.label("Subiendo…", "strong")
        ul.addLayout(W.hbox(W.Spinner(14, "accent"), self.up_title, "stretch", spacing=8))
        self.up_bar = W.RgbProgress(8)
        ul.addWidget(self.up_bar)
        self.up_pct = W.label("", "mono")
        self.up_eta = W.label("", "cap")
        ul.addLayout(W.hbox(self.up_pct, self.up_eta, "stretch",
                            W.button("Cancelar", "secondary", size="sm", on_click=self.cancel), spacing=8))
        ul.addWidget(W.label("No desconectes el cable ni cierres la app.", "cap", wrap=True))
        sl.addWidget(self.up_box)
        sl.addStretch(1)

        row = W.hbox(spacing=16)
        row.addWidget(pv, 1)
        row.addWidget(side, 0, Qt.AlignTop)
        self.lay.addLayout(row)
        self.lay.addStretch(1)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self._update_info()
        self._update_state()

    # ------------------------------------------------------------ archivo
    def choose(self):
        path, _ = QFileDialog.getOpenFileName(self, "Imagen o GIF", "", IMAGE_FILTER)
        if path:
            self.open_path(path)

    def open_path(self, path: str):
        self.path = path
        self.src_info = ""
        try:
            from PIL import Image
            with Image.open(path) as im:
                n = getattr(im, "n_frames", 1)
                size = os.path.getsize(path) / (1024 * 1024)
                self.src_info = f"{n} cuadro{'s' if n != 1 else ''} · {im.width} × {im.height} · " + \
                                (f"{size:.1f} MB".replace(".", ",") if size >= 0.1 else
                                 f"{os.path.getsize(path) // 1024} KB")
        except Exception:  # noqa: BLE001
            pass
        self.reload(reset_delay=True)

    def remove(self):
        self.path = None
        self.anim = None
        self.pixmaps = []
        self.timer.stop()
        self.lcdv.pm = None
        self.lcdv.update()
        self.thumb.pm = None
        self.thumb.update()
        self._update_info()
        self._update_state()

    def reload(self, reset_delay: bool = False):
        fit = self.fit.value()
        self.fit_hint.setText(next(h for _t, k, _i, h in FITS if k == fit))
        if not self.path:
            return
        try:
            delay = None if reset_delay else self.delay.value()
            self.anim = lcd.load_animation(self.path, fit=fit, delay_ms=delay)
        except Exception as e:  # noqa: BLE001
            self.win.toast("err", f"No pude abrir la imagen: {e}")
            return
        frames = self.anim.frames
        if len(frames) > P.LCD_MAX_FRAMES:
            self.win.toast("warn", f"El GIF tiene {len(frames)} cuadros; el teclado admite {P.LCD_MAX_FRAMES}.")
        d = max(20, min(255, self.anim.delay_ms))
        self.anim.delay_ms = d
        self.delay.setValue(d, emit=False)
        self.delay_sl.blockSignals(True)
        self.delay_sl.setValue(d)
        self.delay_sl.blockSignals(False)
        self.frame_i = 0
        self._rebuild_pixmaps()
        self.thumb.pm = self.pixmaps[0] if self.pixmaps else None
        self.thumb.update()
        self._update_info()
        self._update_state()
        self._restart_timer()

    def _rebuild_pixmaps(self):
        if not self.anim:
            return
        self.pixmaps = [_pixmap(f, self.real.isChecked()) for f in self.anim.frames]
        self._show_frame()

    def _update_info(self):
        name = os.path.basename(self.path) if self.path else "Ningún archivo"
        self.f_name.setText(name)
        self.f_meta.setText(self.src_info if self.path else "GIF, PNG, JPG o WebP")
        self.thumb.setVisible(bool(self.path))
        self.b_change.setText("Cambiar…" if self.path else "Elegir imagen o GIF…")
        self.b_remove.setVisible(bool(self.path))
        self.player.setVisible(bool(self.anim and len(self.anim.frames) > 1))
        d = self.delay.value()
        self.fps.setText(f"{1000 / d:.1f} fps".replace(".", ","))
        if not self.anim:
            for w in (self.kv_frames, self.kv_area, self.kv_time):
                w.setText("—")
            self.frames_meter.set(0)
            return
        n = len(self.anim.frames)
        self.kv_frames.setText(f"{n} / {P.LCD_MAX_FRAMES}")
        self.frames_meter.set(n / P.LCD_MAX_FRAMES, "error" if n > P.LCD_MAX_FRAMES else "accent")
        box = lcd.content_box(self.anim.frames)
        self.kv_area.setText(f"{box.width} × {box.height} px")
        pk = lcd.estimate_packets(self.anim)
        self.kv_time.setText("≈ " + _fmt_time(pk * 2.5 / 1000))

    def _update_state(self):
        uploading = self.task is not None
        bt = bool(self.kb and self.kb.bus == "bt")
        self.up_box.setVisible(uploading)
        self.bt_box.setVisible(bt and not uploading)
        self.normal_box.setVisible(not bt and not uploading)
        reason = None
        if not self.anim:
            reason = "Primero elige una imagen o un GIF"
        elif len(self.anim.frames) > P.LCD_MAX_FRAMES:
            reason = f"Máximo {P.LCD_MAX_FRAMES} cuadros"
        elif not self.kb:
            reason = "Conecta el teclado"
        W.disable_with_reason(self.b_upload, reason)
        for w in (self.fit, self.delay, self.delay_sl, self.b_change, self.b_remove):
            w.setEnabled(not uploading)

    # ------------------------------------------------------------ reproducción
    def _restart_timer(self):
        self.timer.stop()
        if self.anim and len(self.anim.frames) > 1 and self.playing:
            self.timer.start(max(20, self.anim.delay_ms))

    def _delay_changed(self, v):
        self.delay_sl.blockSignals(True)
        self.delay_sl.setValue(v)
        self.delay_sl.blockSignals(False)
        if self.anim:
            self.anim.delay_ms = v
        self._update_info()
        self._restart_timer()

    def _show_frame(self):
        if not self.pixmaps:
            return
        self.frame_i %= len(self.pixmaps)
        self.lcdv.pm = self.pixmaps[self.frame_i]
        self.lcdv.update()
        n = len(self.pixmaps)
        self.frame_lbl.setText(f"Cuadro {self.frame_i + 1} / {n}")
        self.frame_meter.set((self.frame_i + 1) / n, "text-3")

    def _tick(self):
        self.frame_i += 1
        self._show_frame()

    def toggle_play(self):
        self.playing = not self.playing
        W.set_icon(self.b_play, "pausa" if self.playing else "play")
        self.b_play.setToolTip("Pausa" if self.playing else "Reproducir")
        self._restart_timer()

    # ------------------------------------------------------------ teclado
    def on_connected(self):
        self._update_state()

    def upload(self):
        if not self.kb or not self.anim:
            return
        if self.kb.bus == "bt":
            self.win.toast("warn", "Por Bluetooth no se pueden subir imágenes. Conecta el cable.")
            return
        n = len(self.anim.frames)
        self.t_start = time.monotonic()

        def done(_):
            self.task = None
            self._update_state()
            secs = time.monotonic() - self.t_start
            self.win.toast("ok", f"Imagen subida en {_fmt_time(secs)}. Pulsa Fn + Ctrl si no la ves.")

        def fail(_m):
            self.task = None
            self._update_state()

        def prog(f, m):
            self.up_bar.set(f)
            cur = min(n, int(f * n) + 1)
            self.up_title.setText(f"Subiendo cuadro {cur} de {n}")
            self.up_pct.setText(f"{f * 100:.0f} %")
            el = time.monotonic() - self.t_start
            if f > 0.02:
                rest = el / f - el
                self.up_eta.setText(f"≈ {int(rest // 60)}:{int(rest % 60):02d} restantes")

        self.up_bar.set(0)
        self.up_title.setText(f"Subiendo cuadro 1 de {n}")
        self.up_pct.setText("0 %")
        self.up_eta.setText("")
        self.task = self.win.run(self.kb.upload_animation, self.anim, progress=True, on_done=done, on_error=fail,
                                 on_progress=prog, cancel=lambda: bool(self.task and self.task.cancelled),
                                 label="Subiendo imagen…", retry=self.upload,
                                 count_fmt=lambda f, m: f"{min(n, int(f * n) + 1)}/{n}")
        self._update_state()

    def cancel(self):
        if self.task:
            self.task.cancelled = True

    def sync_time(self):
        if self.kb:
            self.win.run(self.kb.sync_clock,
                         on_done=lambda t: self.win.toast("ok", "Hora sincronizada: " + t.strftime("%H:%M:%S")),
                         label="Sincronizando hora…", retry=self.sync_time)
