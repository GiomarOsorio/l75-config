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
from ...i18n import t as tr
from ..theme import font, theme
from ..window import Page
from .common import section_label

FITS = [("Fit", "contain", "ajustar", "Shown whole, with black bars above and below."),
        ("Fill", "cover", "rellenar", "Fills the screen and crops what does not fit."),
        ("Stretch", "stretch", "estirar", "Fills the screen by distorting the image.")]


def _image_filter() -> str:
    return tr("Images") + " (*.gif *.png *.jpg *.jpeg *.webp *.bmp);;" + tr("All files") + " (*)"


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
                       tr("Drop an image or a GIF here"))
            p.setPen(t.c("text-2"))
            p.setFont(font(12))
            p.drawText(QRectF(r.left(), r.center().y() + 18, r.width(), 20), Qt.AlignCenter,
                       tr("or click to choose a file · it is fitted to 240 × 135 px"))
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

        header = W.PageHeader(tr("Screen"), tr("Put your image or GIF on the keyboard's 240 × 135 px screen."))
        header.add(W.button(tr("Sync date and time"), "secondary", "reloj", on_click=self.sync_time))
        self.lay.addWidget(header)

        # --- vista previa
        pv, pl = W.card(padding=(18, 14, 18, 16), spacing=12)
        self.real = W.Switch()
        self.real.setToolTip(tr("Shows the colours as the keyboard will (RGB565)"))
        self.real.toggled.connect(lambda _on: self._rebuild_pixmaps())
        pl.addLayout(W.hbox(W.label(tr("Preview"), "sub"), W.label(tr("at 2× · 480 × 270"), "cap"), "stretch",
                            W.label(tr("Real pixels (RGB565)"), "body2"), self.real, spacing=10))
        self.lcdv = LcdView()
        self.lcdv.fileDropped.connect(self.open_path)
        self.lcdv.clicked.connect(self.choose)
        pl.addWidget(self.lcdv)
        self.b_play = W.button("", "ghost", "pausa", size="sm", tip=tr("Pause"), on_click=self.toggle_play)
        self.frame_lbl = W.label("", "mono2")
        self.frame_meter = W.Meter(260)
        self.player = QWidget()
        W.hbox(self.b_play, self.frame_lbl, self.frame_meter, "stretch", spacing=12, parent=self.player)
        pl.addWidget(self.player)
        tail = W.label(tr("switches between your image and the default screen (time and battery)."), "body2",
                       wrap=True)
        note = W.hbox(W.label(tr("On the keyboard,"), "body2"), W.kbd("Fn"), W.label("+", "body2"), W.kbd("Ctrl"), spacing=6)
        note.addWidget(tail, 1)
        pl.addLayout(note)
        pl.addStretch(1)

        # --- panel derecho
        side, sl = W.card(padding=(16, 14, 16, 16), spacing=10)
        side.setFixedWidth(330)
        sl.addWidget(section_label(tr("File")))
        self.thumb = Thumb()
        self.f_name = W.label(tr("No file"), "strong")
        self.f_meta = W.label(tr("GIF, PNG, JPG or WebP"), "cap")
        sl.addLayout(W.hbox(self.thumb, W.vbox(self.f_name, self.f_meta, spacing=0), "stretch", spacing=10))
        self.b_change = W.button(tr("Choose image or GIF…"), "secondary", "imagen", size="sm", on_click=self.choose)
        self.b_remove = W.button(tr("Remove"), "ghost", size="sm", on_click=self.remove)
        sl.addLayout(W.hbox(self.b_change, self.b_remove, "stretch", spacing=8))
        sl.addSpacing(4)
        sl.addWidget(section_label(tr("Fit")))
        self.fit = W.Segmented(block=True)
        for text, key, icon, _h in FITS:
            self.fit.add(tr(text), key, icon=icon)
        self.fit.changed.connect(lambda _v: self.reload())
        self.fit_hint = W.label(tr(FITS[0][3]), "cap", wrap=True)
        sl.addWidget(self.fit)
        sl.addWidget(self.fit_hint)
        sl.addSpacing(4)
        self.fps = W.label("", "mono2")
        sl.addLayout(W.hbox(section_label(tr("Delay between frames")), "stretch", self.fps))
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
        for i, (name, val, extra) in enumerate(((tr("Frames"), self.kv_frames, self.frames_meter),
                                                (tr("Area used"), self.kv_area, None),
                                                (tr("Estimated upload"), self.kv_time, None))):
            row = QFrame()
            row.setProperty("kv", "last" if i == 2 else "true")
            row.setFixedHeight(34)
            W.hbox(W.label(name, "kv-l"), "stretch", extra, val, spacing=8, parent=row)
            kvs.addWidget(row)
        sl.addLayout(kvs)
        sl.addSpacing(8)
        # subir / estado de subida / bloqueado por BT
        self.b_upload = W.button(tr("Upload to the screen"), "primary", "guardar", size="lg", on_click=self.upload)
        self.up_hint = W.label(tr("Keep the cable connected during the upload."), "cap", wrap=True)
        self.normal_box = QWidget()
        W.vbox(self.b_upload, self.up_hint, spacing=8, parent=self.normal_box)
        sl.addWidget(self.normal_box)
        # bloqueado
        self.bt_box, bl = W.card("inner", padding=(14, 12, 14, 14), spacing=8)
        self.bt_box.setStyleSheet("QFrame[card='inner']{border-style: dashed;}")
        bl.addLayout(W.hbox(W.icon_label("inalambrico", "warning", 16),
                            W.label(tr("Upload only works by cable"), "strong"), "stretch", spacing=8))
        bl.addWidget(W.label(tr("Connect the L75 with the USB-C cable to upload images. Date and time do sync "
                                "over Bluetooth."), "cap", wrap=True))
        b_lock = W.button(tr("Upload to the screen"), "secondary", "candado")
        W.disable_with_reason(b_lock, tr("USB-C cable only"))
        bl.addWidget(b_lock)
        sl.addWidget(self.bt_box)
        # en curso
        self.up_box, ul = W.card("inner", padding=(14, 12, 14, 14), spacing=10)
        self.up_title = W.label(tr("Uploading…"), "strong")
        ul.addLayout(W.hbox(W.Spinner(14, "accent"), self.up_title, "stretch", spacing=8))
        self.up_bar = W.RgbProgress(8)
        ul.addWidget(self.up_bar)
        self.up_pct = W.label("", "mono")
        self.up_eta = W.label("", "cap")
        ul.addLayout(W.hbox(self.up_pct, self.up_eta, "stretch",
                            W.button(tr("Cancel"), "secondary", size="sm", on_click=self.cancel), spacing=8))
        ul.addWidget(W.label(tr("Do not unplug the cable or close the app."), "cap", wrap=True))
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
        path, _ = QFileDialog.getOpenFileName(self, tr("Image or GIF"), "", _image_filter())
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
                frames = (tr("{n} frames") if n != 1 else tr("{n} frame")).format(n=n)
                self.src_info = f"{frames} · {im.width} × {im.height} · " + \
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
        self.fit_hint.setText(tr(next(h for _t, k, _i, h in FITS if k == fit)))
        if not self.path:
            return
        try:
            delay = None if reset_delay else self.delay.value()
            self.anim = lcd.load_animation(self.path, fit=fit, delay_ms=delay)
        except Exception as e:  # noqa: BLE001
            self.win.toast("err", tr("Could not open the image: {error}").format(error=e))
            return
        frames = self.anim.frames
        if len(frames) > P.LCD_MAX_FRAMES:
            self.win.toast("warn", tr("The GIF has {n} frames; the keyboard accepts {max}.").format(
                n=len(frames), max=P.LCD_MAX_FRAMES))
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
        name = os.path.basename(self.path) if self.path else tr("No file")
        self.f_name.setText(name)
        self.f_meta.setText(self.src_info if self.path else tr("GIF, PNG, JPG or WebP"))
        self.thumb.setVisible(bool(self.path))
        self.b_change.setText(tr("Change…") if self.path else tr("Choose image or GIF…"))
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
            reason = tr("First choose an image or a GIF")
        elif len(self.anim.frames) > P.LCD_MAX_FRAMES:
            reason = tr("Maximum {n} frames").format(n=P.LCD_MAX_FRAMES)
        elif not self.kb:
            reason = tr("Connect the keyboard")
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
        self.frame_lbl.setText(tr("Frame {i} / {n}").format(i=self.frame_i + 1, n=n))
        self.frame_meter.set((self.frame_i + 1) / n, "text-3")

    def _tick(self):
        self.frame_i += 1
        self._show_frame()

    def toggle_play(self):
        self.playing = not self.playing
        W.set_icon(self.b_play, "pausa" if self.playing else "play")
        self.b_play.setToolTip(tr("Pause") if self.playing else tr("Play"))
        self._restart_timer()

    # ------------------------------------------------------------ teclado
    def on_connected(self):
        self._update_state()

    def upload(self):
        if not self.kb or not self.anim:
            return
        if self.kb.bus == "bt":
            self.win.toast("warn", tr("Images cannot be uploaded over Bluetooth. Plug in the cable."))
            return
        n = len(self.anim.frames)
        self.t_start = time.monotonic()

        def done(_):
            self.task = None
            self._update_state()
            secs = time.monotonic() - self.t_start
            self.win.toast("ok", tr("Image uploaded in {time}. Press Fn + Ctrl if you do not see it.").format(
                time=_fmt_time(secs)))

        def fail(_m):
            self.task = None
            self._update_state()

        def prog(f, m):
            self.up_bar.set(f)
            cur = min(n, int(f * n) + 1)
            self.up_title.setText(tr("Uploading frame {i} of {n}").format(i=cur, n=n))
            self.up_pct.setText(f"{f * 100:.0f} %")
            el = time.monotonic() - self.t_start
            if f > 0.02:
                rest = el / f - el
                self.up_eta.setText(tr("≈ {time} left").format(time=f"{int(rest // 60)}:{int(rest % 60):02d}"))

        self.up_bar.set(0)
        self.up_title.setText(tr("Uploading frame {i} of {n}").format(i=1, n=n))
        self.up_pct.setText("0 %")
        self.up_eta.setText("")
        self.task = self.win.run(self.kb.upload_animation, self.anim, progress=True, on_done=done, on_error=fail,
                                 on_progress=prog, cancel=lambda: bool(self.task and self.task.cancelled),
                                 label=tr("Uploading image…"), retry=self.upload,
                                 count_fmt=lambda f, m: f"{min(n, int(f * n) + 1)}/{n}")
        self._update_state()

    def cancel(self):
        if self.task:
            self.task.cancelled = True

    def sync_time(self):
        if self.kb:
            self.win.run(self.kb.sync_clock,
                         on_done=lambda t: self.win.toast("ok", tr("Time synced: ") + t.strftime("%H:%M:%S")),
                         label=tr("Syncing time…"), retry=self.sync_time)
