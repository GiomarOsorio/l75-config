"""Pruebas sin hardware. Los vectores esperados se derivaron a mano leyendo el
codigo del driver oficial (ver docs/PROTOCOL.md).

Ejecutar:  python3 -m unittest discover -s tests -v
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from l75ctl import i18n  # noqa: E402
from l75ctl import lcd  # noqa: E402
from l75ctl import lighting as L  # noqa: E402

i18n.set_language("en")
from l75ctl import protocol as P  # noqa: E402
from l75ctl.keyboard import L75  # noqa: E402
from l75ctl.keymap import KEYS, Action, find_key, parse_action  # noqa: E402
from l75ctl.macros import Macro, MacroEvent, decode_macro, encode_macro, macro_pages, parse_macro_text  # noqa: E402
from l75ctl.transport import DryRunTransport, SimulatedTransport  # noqa: E402


def K(code, down):
    return MacroEvent("key", code, down)


def D(ms):
    return MacroEvent("delay", ms)


class ChecksumTest(unittest.TestCase):
    def test_bit7(self):
        b = P.apply_checksum(P.packet(0x80), P.Checksum.BIT7)
        self.assertEqual(b[7], 0x7F)

    def test_bit7_wraps(self):
        b = P.apply_checksum(P.packet(0x13, 0, 0x0C), P.Checksum.BIT7)
        self.assertEqual(b[7], 0xFF - 0x1F)

    def test_bit8(self):
        b = P.apply_checksum(P.packet(7, 1, 4, 3, 7, 0xFF, 0x88, 0), P.Checksum.BIT8)
        self.assertEqual(b[8], 0x62)


class MacroTest(unittest.TestCase):
    def test_short_delays_are_folded(self):
        m = Macro([K(4, True), D(50), K(4, False), D(50)], 1)
        buf = encode_macro(m)
        self.assertEqual(buf[:8], bytes([1, 0, 0x04, 0xB2, 0x04, 0x32, 0, 0]))
        self.assertEqual(len(buf), 256)

    def test_long_delays_and_gaps(self):
        m = Macro([K(0xE0, True), K(6, True), D(300), K(6, False), K(0xE0, False), D(1000)], 3)
        expected = bytes([3, 0, 0xE0, 0x80, 0, 0, 0x06, 0x80, 0x2C, 0x01, 0x06, 0x00,
                          0, 0, 0xE0, 0x00, 0xE8, 0x03, 0, 0])
        self.assertEqual(encode_macro(m)[:20], expected)

    def test_leading_delay_and_mouse(self):
        evs = [D(200), MacroEvent("mouse", 240, True), D(10), MacroEvent("mouse", 240, False), D(128),
               K(40, True), D(127), K(40, False)]
        expected = bytes([0, 0, 0, 0, 0xC8, 0, 0xF0, 0x8A, 0xF0, 0x00, 0x80, 0x00, 0x28, 0xFF, 0x28, 0x00, 0, 0])
        self.assertEqual(encode_macro(Macro(evs, 0))[:18], expected)

    def test_roundtrip(self):
        cases = [
            [K(4, True), D(50), K(4, False), D(50)],
            [K(0xE0, True), K(6, True), D(300), K(6, False), K(0xE0, False), D(1000)],
            [D(200), MacroEvent("mouse", 240, True), D(10), MacroEvent("mouse", 240, False), D(128),
             K(40, True), D(127), K(40, False)],
        ]
        for evs in cases:
            m = decode_macro(encode_macro(Macro(evs, 7)))
            self.assertEqual(m.repeat, 7)
            self.assertEqual([(e.type, e.value, e.down) for e in m.events],
                             [(e.type, e.value, e.down) for e in evs])

    def test_text_parser(self):
        evs = parse_macro_text("down:ctrl, tap:c, up:ctrl, delay:300, tap:enter")
        self.assertEqual(len(evs), 7)
        self.assertEqual(evs[1].value, 6)

    def test_too_long(self):
        evs = [K(4, True), D(500), K(4, False), D(500)] * 40
        with self.assertRaises(ValueError):
            encode_macro(Macro(evs, 1))

    def test_pages(self):
        buf = encode_macro(Macro([K(4, True), K(4, False)], 1))
        self.assertEqual(len(macro_pages(buf)), 1)
        big = encode_macro(Macro([K(4, True), D(300), K(4, False), D(300)] * 25, 1))
        self.assertEqual(len(macro_pages(big)), 4)


class LightTest(unittest.TestCase):
    def test_static(self):
        b = L.encode_light(L.LightSetting("static", brightness=3, color=0xFF8800))
        self.assertEqual(list(b[:9]), [7, 1, 4, 3, 7, 0xFF, 0x88, 0, 0x62])

    def test_wave_rainbow(self):
        b = L.encode_light(L.LightSetting("wave", brightness=4, speed=3, rainbow=True, option="left", color=0))
        self.assertEqual(list(b[:5]), [7, 4, 1, 4, (1 << 4) | 8])

    def test_white_correction(self):
        b = L.encode_light(L.LightSetting("static", color=0xFFFFFF))
        self.assertEqual(list(b[5:8]), [0xFA, 0xFF, 0xFA])

    def test_off(self):
        b = L.encode_light(L.LightSetting("off"))
        self.assertEqual(list(b[:5]), [7, 0, 4, 0, 7])

    def test_user_picture(self):
        b = L.encode_light(L.LightSetting("user", brightness=2, option="2"))
        self.assertEqual(list(b[:8]), [7, 13, 4, 2, 16, 0, 200, 200])

    def test_music(self):
        b = L.encode_light(L.LightSetting("music2", option="intersect", rainbow=False, color=0x00FF00))
        self.assertEqual(b[4], (2 << 4) | 4)

    def test_decode_roundtrip(self):
        for s in [L.LightSetting("breath", 2, 1, 0x123456, False),
                  L.LightSetting("snake", 4, 4, 0, True, "return"),
                  L.LightSetting("circle", 1, 0, 0xFF0000, False, "clockwise")]:
            d = L.decode_light(L.encode_light(s))
            self.assertEqual((d.mode, d.brightness, d.speed, d.rainbow, d.option),
                             (s.mode, s.brightness, s.speed, s.rainbow, s.option))
            if not s.rainbow:
                self.assertEqual(d.color, s.color)

    def test_preset_color_decoding(self):
        d = L.decode_light(bytes([0x87, 1, 4, 4, 3, 0, 0, 0]))
        self.assertEqual(d.color, 0x00FF00)

    def test_side(self):
        b = L.encode_side(L.LightSetting("wave", brightness=3, speed=2, option="up", color=0x0000FF))
        self.assertEqual(list(b[:8]), [8, 4, 2, 3, (3 << 4) | 7, 0, 0, 0xFF])
        d = L.decode_side(b)
        self.assertEqual((d.mode, d.option, d.speed), ("wave", "up", 2))


class KeymapTest(unittest.TestCase):
    def test_slots(self):
        self.assertEqual(find_key("Esc").slot, 0)
        self.assertEqual(find_key("Space").slot, 41)
        self.assertEqual(find_key("Fn").slot, 65)
        self.assertEqual(find_key("r_Alt").slot, 59)
        self.assertEqual(find_key("Caps Lock").slot, 3)
        self.assertEqual(len(KEYS), 81)
        self.assertEqual(len({k.slot for k in KEYS}), 81)

    def test_actions(self):
        self.assertEqual(parse_action("Esc").raw, (0, 0, 0x29, 0))
        self.assertEqual(parse_action("combo:ctrl+shift+t").raw, (0, 0xE0, 0xE1, 0x17))
        self.assertEqual(parse_action("ctrl+c").raw, (0, 0xE0, 0x06, 0))
        self.assertEqual(parse_action("fn:vol+").raw, (3, 0, 233, 0))
        self.assertEqual(parse_action("mouse:left").raw, (1, 0, 240, 0))
        self.assertEqual(parse_action("macro:3:hold").raw, (9, 2, 3, 0))
        self.assertEqual(parse_action("off").raw, (0, 0, 0, 0))
        self.assertEqual(Action((3, 0, 205, 0)).kind, "function")


class LcdTest(unittest.TestCase):
    def test_rgb565(self):
        self.assertEqual(lcd.rgb565_be(255, 255, 255), b"\xff\xff")
        self.assertEqual(lcd.rgb565_be(255, 0, 0), b"\xf8\x00")
        self.assertEqual(lcd.rgb565_be(0, 255, 0), b"\x07\xe0")

    def test_column_major(self):
        from PIL import Image
        img = Image.new("RGB", (lcd.W, lcd.H))
        img.putpixel((10, 20), (255, 0, 0))
        img.putpixel((11, 20), (0, 0, 255))
        img.putpixel((10, 21), (0, 255, 0))
        box = lcd.content_box([img])
        self.assertEqual((box.left, box.top, box.right, box.bottom), (10, 20, 12, 22))
        data = lcd.frame_to_rgb565(img, box)
        # columna x=10: (10,20) rojo, (10,21) verde; columna x=11: azul, negro
        self.assertEqual(data, b"\xf8\x00\x07\xe0\x00\x1f\x00\x00")

    def test_header(self):
        box = lcd.Box(0, 0, 240, 135)
        b = lcd.header_packet(3, 100, 64800, box)
        self.assertEqual(list(b[:7]), [0xA5, 0, 3, 100, 64800 & 255, 64800 >> 8, 0])
        self.assertEqual(list(b[8:18]), [0, 0, 240, 135, 0, 0, 0, 0, 0, 0])
        self.assertEqual(b[7], 0xFF - (sum(b[:7]) & 0xFF))

    def test_data_packets(self):
        data = bytes(range(100))
        pk = list(lcd.data_packets(data, 1, 2, 50))
        self.assertEqual(len(pk), 2)
        self.assertEqual(list(pk[0][:7]), [0x25, 1, 2, 50, 0, 0, 56])
        self.assertEqual(list(pk[1][:7]), [0x25, 1, 2, 50, 1, 0, 44])
        self.assertEqual(bytes(pk[1][8:8 + 44]), data[56:])


class DeviceSimTest(unittest.TestCase):
    def setUp(self):
        self.kb = L75(SimulatedTransport())
        self.kb.WRITE_DELAY_MS = 0
        self.kb.READ_DELAY_MS = 0

    def test_matrix_roundtrip(self):
        acts = self.kb.read_matrix()
        self.assertEqual(acts[0].raw, (0, 0, 41, 0))
        self.kb.set_key(find_key("CapsLock"), parse_action("Esc"))
        self.assertEqual(self.kb.read_matrix()[3].raw, (0, 0, 41, 0))

    def test_macro_roundtrip(self):
        m = Macro(parse_macro_text("down:ctrl, tap:c, up:ctrl, delay:300, tap:enter"), 2)
        self.kb.write_macro(5, m)
        back = self.kb.read_macro(5)
        self.assertEqual(back.repeat, 2)
        self.assertEqual(back.to_text(), m.to_text())

    def test_light(self):
        s = L.LightSetting("ripple", 3, 1, 0x00FF00)
        self.kb.set_light(s)
        self.assertEqual(self.kb.get_light().mode, "ripple")

    def test_forbidden(self):
        with self.assertRaises(ValueError):
            self.kb.send(P.packet(0x7F, 0x55, 0xAA))

    def test_upload(self):
        from PIL import Image
        frames = [Image.new("RGB", (lcd.W, lcd.H), (i * 40, 0, 0)) for i in range(1, 4)]
        self.kb.upload_animation(lcd.Animation(frames, 100))
        self.assertEqual(self.kb.t.lcd_frames_received, 3)

    def test_dry_run_prints(self):
        import io
        out = io.StringIO()
        kb = L75(DryRunTransport(out=out))
        kb.WRITE_DELAY_MS = 0
        kb.sync_clock()
        self.assertTrue(out.getvalue().startswith("TX 28 00"))


if __name__ == "__main__":
    unittest.main()


class FakeBleDev:
    def __init__(self, incoming, replies=()):
        self.incoming = list(incoming)
        self.replies = list(replies)  # se entregan despues de cada write
        self.written = []

    def write(self, data):
        self.written.append(bytes(data))
        if self.replies:
            self.incoming.append(self.replies.pop(0))

    def read(self, size, timeout=None):
        return self.incoming.pop(0) if self.incoming else b""


class SystemFunctionTest(unittest.TestCase):
    def test_fn_layer_names(self):
        from l75ctl.keymap import Action, is_system
        self.assertEqual(Action((10, 5, 2, 0)).kind, "system")
        self.assertEqual(Action((10, 5, 2, 0)).short(), "iOS")
        self.assertEqual(Action((14, 0, 0, 0)).short(), "BT1")
        self.assertIn("brightness", Action((13, 2, 1, 0)).describe())
        self.assertTrue(is_system((13, 9, 9, 0)))
        self.assertFalse(is_system((3, 0, 205, 0)))      # multimedia: se puede cambiar
        self.assertFalse(is_system((0, 0, 227, 43)))     # Win+Tab: se puede cambiar
        self.assertEqual(Action((10, 1, 0, 0)).describe(), "Fn")

    def test_demo_fn_layer(self):
        from l75ctl.keyboard import L75
        from l75ctl.keymap import find_key
        with L75.open(demo=True) as kb:
            acts = kb.read_matrix(fn=True)
        self.assertEqual(acts[find_key("I").slot].short(), "iOS")
        self.assertEqual(acts[find_key("Q").slot].short(), "BT1")


class BleTransportTest(unittest.TestCase):
    def make(self, incoming, replies=()):
        from l75ctl.transport import BleTransport
        t = BleTransport.__new__(BleTransport)
        t._dev = FakeBleDev(incoming, replies)
        t.path = b"/dev/fake"
        t.events = []
        return t

    def test_write_framing(self):
        t = self.make([])
        pkt = P.apply_checksum(P.packet(0x85), P.Checksum.BIT7)
        t.write(bytes(pkt))
        w = t._dev.written[0]
        self.assertEqual(len(w), P.BLE_REPORT_SIZE)
        self.assertEqual(w[:2], bytes([6, 0x55]))
        self.assertEqual(w[2:66], bytes(pkt))

    def test_read_skips_noise(self):
        key_report = bytes([1, 0, 0, 4, 0, 0, 0, 0, 0])
        event = bytes([6, 0x66, 2, 1]) + bytes(62)
        zeros = bytes(66)
        answer = bytes([6, 0x55, 0x85, 2]) + bytes(62)
        t = self.make([key_report, event, zeros, answer])
        r = t.read()
        self.assertEqual(r[:2], bytes([0x85, 2]))
        self.assertEqual(len(r), 64)
        self.assertEqual(len(t.events), 1)

    def test_keyboard_over_ble(self):
        stale = bytes([6, 0x55, 0x80, 9]) + bytes(62)
        t = self.make([stale], replies=[bytes([6, 0x55, 0x85, 1]) + bytes(62)])
        kb = L75(t)
        self.assertEqual(kb.bus, "bt")
        kb.WRITE_DELAY_MS = 0
        self.assertEqual(kb.get_profile(), 1)
        with self.assertRaises(Exception):
            kb.upload_animation(lcd.Animation([], 0))


if __name__ == "__main__":
    unittest.main()
