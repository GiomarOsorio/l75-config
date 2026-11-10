"""Command line: ``l75 <command>``. Run ``l75 -h`` for help."""

from __future__ import annotations

import argparse
import sys

from . import __version__
from . import lighting as L
from . import protocol as P
from .keyboard import L75, SleepTimes
from .keymap import FUNCTIONS, KEYS, MOUSE, find_key, is_system, parse_action
from .macros import Macro, parse_macro_text
from .i18n import set_language
from .i18n import t as tr
from .transport import TransportError, list_devices


def _open(args) -> L75:
    kb = L75.open(demo=args.demo, dry_run=args.dry_run, prefer=args.via)
    if args.profile is not None:
        kb.profile = args.profile
    elif not kb.is_dry_run:
        kb.get_profile()
    return kb


def _progress(frac: float, msg: str) -> None:
    bar = int(frac * 30)
    sys.stderr.write(f"\r[{'#' * bar}{'.' * (30 - bar)}] {frac * 100:5.1f}% {msg}   ")
    sys.stderr.flush()
    if frac >= 1:
        sys.stderr.write("\n")


# ------------------------------------------------------------------ comandos
def cmd_list(args):
    devs = list_devices(include_dongles=True)
    if not devs:
        print(tr("No L75 found (neither by cable nor by Bluetooth)."))
        return 1
    for d in devs:
        tipo = {"usb": tr("cable"), "bt": "Bluetooth", "dongle": tr("2.4G receiver (not supported yet)")}[d.bus]
        print(f"{d.path.decode(errors='replace')}  {d.vid:04x}:{d.pid:04x}  if={d.interface}  "
              f"{d.manufacturer} {d.product}  [{tipo}]")
    return 0


def cmd_info(args):
    with _open(args) as kb:
        conn = "Bluetooth" if kb.bus == "bt" else "demo" if kb.is_demo else tr("USB cable")
        fw = kb.firmware_version()
        did = kb.device_id()
        pct, st = kb.battery()
        rows = [
            (tr("Connection"), conn),
            (tr("Firmware"), f"{fw >> 8}.{fw & 0xFF:02d} (0x{fw:04X})"),
            (tr("Model ID"), f"{did}" + (" (L75)" if did in P.DEVICE_IDS_L75 else "  ⚠ " + tr("not a known L75"))),
            (tr("Active profile"), str(kb.profile + 1)),
            (tr("Battery"), f"{pct}% ({tr(st)})"),
            (tr("Polling rate"), f"{kb.get_report_rate()} Hz"),
            (tr("Debounce"), f"{kb.get_debounce()} ms"),
            (tr("Key lighting"), kb.get_light().describe()),
            (tr("Side strip"), kb.get_side_light().describe(side=True)),
        ]
        width = max(len(k) for k, _v in rows) + 2
        for k, v in rows:
            print(f"{k + ':':<{width}} {v}")
    return 0


def cmd_profile(args):
    with _open(args) as kb:
        if args.value is None:
            print(tr("Active profile") + f": {kb.get_profile() + 1}")
        else:
            kb.set_profile(args.value - 1)
            print(tr("Profile {n} activated").format(n=args.value))
    return 0


def _light_from_args(args, side: bool) -> L.LightSetting:
    table = L.SIDE_MODE_BY_KEY if side else L.MODE_BY_KEY
    if args.mode not in table:
        raise SystemExit(tr("invalid mode. Use 'l75 light modes'"))
    m = table[args.mode]
    opt = args.option
    if opt is not None and m.kind != "picture" and opt not in m.options:
        raise SystemExit(tr("invalid option for {mode}: {options}").format(
            mode=m.key, options=", ".join(m.options) or tr("(none)")))
    return L.LightSetting(mode=args.mode, brightness=args.brightness, speed=args.speed,
                          color=L.parse_color(args.color), rainbow=args.rainbow, option=opt)


def cmd_light(args):
    side = args.target == "side"
    if args.action == "modes":
        for m in (L.SIDE_MODES if side else L.MODES):
            extra = []
            if m.speed:
                extra.append(tr("speed"))
            if m.color:
                extra.append(tr("colour/rainbow"))
            if m.options:
                extra.append(tr("options: ") + "|".join(m.options))
            if m.kind == "picture":
                extra.append(tr("option: picture 1..5"))
            print(f"  {m.key:<13} {tr(m.label):<24} {', '.join(extra)}")
        return 0
    with _open(args) as kb:
        if args.action == "get":
            s = kb.get_side_light() if side else kb.get_light()
            print(s.describe(side=side))
        else:
            s = _light_from_args(args, side)
            (kb.set_side_light if side else kb.set_light)(s)
            print("OK:", s.describe(side=side))
    return 0


def cmd_keys(args):
    if args.action == "names":
        print(tr("Physical keys of the L75 (use these names in 'l75 keys set'):"))
        print("  " + ", ".join(k.name for k in KEYS))
        print("\n" + tr("Functions (fn:<name>):"))
        for k, label, _ in FUNCTIONS:
            print(f"  {k:<11} {tr(label)}")
        print("\n" + tr("Mouse (mouse:<name>):") + "  " + ", ".join(k for k, _, _ in MOUSE))
        print("\n" + tr("Action examples:") + " Esc | key:F5 | combo:ctrl+shift+t | fn:vol+ | mouse:left |"
              " macro:0 | macro:0:hold | off | default")
        return 0
    with _open(args) as kb:
        if args.action == "list":
            acts = kb.read_matrix(fn=args.fn, progress=None)
            capa = tr("Fn layer") if args.fn else tr("profile {n}").format(n=kb.profile + 1)
            print(tr("Assignments ({layer}):").format(layer=capa))
            for k in KEYS:
                a = acts[k.slot]
                mark = "" if (args.fn or a == k.default_action) else "   <- " + tr("changed")
                print(f"  {k.name:<12} slot {k.slot:>3}  {a.describe()}{mark}")
        elif args.action == "set":
            key = find_key(args.key)
            if args.value.lower() == "default":
                if args.fn:
                    raise ValueError(tr("the Fn layer has no known 'default'; use a specific action"))
                act = key.default_action
            else:
                act = parse_action(args.value)
            if key.default_action.raw == (10, 1, 0, 0):
                raise ValueError(tr("the Fn key cannot be remapped"))
            if args.fn:
                cur = kb.read_matrix(fn=True)[key.slot]
                if is_system(cur.raw):
                    raise ValueError(tr("Fn + {key} is a system key ({what}): the official driver does not let "
                                        "you change it").format(key=key.name, what=cur.describe()))
            kb.set_key(key, act, fn=args.fn)
            print(f"{key.name} -> {act.describe()} (" + (tr("Fn layer") if args.fn else
                                                         tr("profile {n}").format(n=kb.profile + 1)) + ")")
        elif args.action == "reset":
            for k in KEYS:
                kb.set_key(k, k.default_action)
            print(tr("Keys of profile {n} restored").format(n=kb.profile + 1))
    return 0


def cmd_macro(args):
    if args.action == "help":
        print(tr("Format:") + " down:<key>, up:<key>, tap:<key>, delay:<ms>, down:mouse-left, move:dx,dy")
        print(tr("Example:") + ' l75 macro set 0 "down:ctrl, tap:c, up:ctrl, delay:50, tap:enter" --repeat 1')
        print(tr("Then assign it:") + " l75 keys set F1 macro:0        (" + tr("or") + " macro:0:hold / macro:0:toggle)")
        return 0
    with _open(args) as kb:
        if args.action == "get":
            m = kb.read_macro(args.index)
            print(tr("Macro {n}: repeat {r} time(s), {e} events").format(n=args.index, r=m.repeat, e=len(m.events)))
            for e in m.events:
                print("  " + e.describe())
            print(tr("Text:"), m.to_text())
        elif args.action == "set":
            m = Macro(parse_macro_text(args.events), args.repeat)
            kb.write_macro(args.index, m)
            print(tr("Macro {n} saved ({e} events)").format(n=args.index, e=len(m.events)))
        elif args.action == "clear":
            kb.write_macro(args.index, Macro([], 0))
            print(tr("Macro {n} deleted").format(n=args.index))
    return 0


def cmd_lcd(args):
    from . import lcd
    if args.action == "time":
        with _open(args) as kb:
            when = kb.sync_clock()
        print(tr("Time synced: ") + when.strftime("%Y-%m-%d %H:%M:%S"))
        return 0
    anim = lcd.load_animation(args.file, fit=args.fit, delay_ms=args.delay)
    box = lcd.content_box(anim.frames)
    print(tr("{n} frame(s), delay {d} ms, area {w}x{h}, {p} packets").format(
        n=len(anim.frames), d=anim.delay_ms, w=box.width, h=box.height, p=lcd.estimate_packets(anim)))
    if args.preview:
        out = args.preview
        if len(anim.frames) > 1:
            anim.frames[0].save(out, save_all=True, append_images=anim.frames[1:],
                                duration=anim.delay_ms or 100, loop=0)
        else:
            anim.frames[0].save(out)
        print(tr("Preview saved to"), out)
        return 0
    if args.dry_run:
        print(tr("(dry-run: image packets are not shown, only the header)"))
        print("TX " + lcd.header_packet(len(anim.frames), anim.delay_ms,
                                        box.width * box.height * 2, box).hex(" "))
        return 0
    with _open(args) as kb:
        kb.upload_animation(anim, progress=_progress)
        print(tr("Done. On the keyboard, Fn+Ctrl switches between your animation and the default style."))
    return 0


def cmd_settings(args):
    with _open(args) as kb:
        changed = False
        if args.report_rate:
            kb.set_report_rate(args.report_rate)
            changed = True
        if args.debounce is not None:
            kb.set_debounce(args.debounce)
            changed = True
        if any(v is not None for v in (args.sleep, args.deep_sleep)):
            s = kb.get_sleep() if not kb.is_dry_run else SleepTimes()
            if args.sleep is not None:
                s.bt = s.rf24 = args.sleep * 60
            if args.deep_sleep is not None:
                s.deep_bt = s.deep_rf24 = args.deep_sleep * 60
            kb.set_sleep(s)
            changed = True
        opts_map = {"win_lock": args.win_lock, "mac_mode": args.mac, "wasd_arrows_swap": args.wasd_swap}
        if any(v is not None for v in opts_map.values()):
            o = kb.get_options()
            for k, v in opts_map.items():
                if v is not None:
                    setattr(o, k, v == "on")
            kb.set_options(o)
            changed = True
        if not changed or args.show:
            o = kb.get_options()
            s = kb.get_sleep()
            yes, no = tr("yes"), tr("no")
            rows = [
                (tr("Polling rate"), f"{kb.get_report_rate()} Hz"),
                (tr("Debounce"), f"{kb.get_debounce()} ms"),
                (tr("Sleep"), f"BT {s.bt // 60} min / 2.4G {s.rf24 // 60} min; " + tr("deep") +
                 f" BT {s.deep_bt // 60} min / 2.4G {s.deep_rf24 // 60} min"),
                (tr("Lock Windows key"), yes if o.win_lock else no),
                (tr("Mac mode"), yes if o.mac_mode else no),
                (tr("Swap WASD and arrows"), yes if o.wasd_arrows_swap else no),
            ]
            width = max(len(k) for k, _v in rows) + 2
            for k, v in rows:
                print(f"{k + ':':<{width}} {v}")
        else:
            print(tr("Settings saved"))
    return 0


def cmd_reset(args):
    if not args.yes:
        print(tr("This restores the WHOLE keyboard to factory values (keys, macros, lighting)."))
        if input(tr("Type 'yes' to continue: ")).strip().lower() not in ("si", "sí", "yes", "y"):
            print(tr("Cancelled"))
            return 1
    with _open(args) as kb:
        kb.factory_reset()
    print(tr("Keyboard reset to factory"))
    return 0


def cmd_raw(args):
    data = bytes.fromhex(args.hex.replace(":", " "))
    with _open(args) as kb:
        ck = {"bit7": P.Checksum.BIT7, "bit8": P.Checksum.BIT8, "none": None}[args.checksum]
        if args.read:
            r = kb.query(data, checksum=ck or P.Checksum.NONE)
            print("RX " + r.hex(" "))
        else:
            kb.send(data, checksum=ck)
            print(tr("sent"))
    return 0


def cmd_gui(args):
    from .gui import run
    return run(demo=args.demo, language=args.lang)


# ------------------------------------------------------------------ parser
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="l75", description=tr("Configurator for the ROYALAXE / ProtoArc L75 keyboard"))
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    p.add_argument("--demo", action="store_true", help=tr("use a simulated keyboard (no hardware)"))
    p.add_argument("--dry-run", action="store_true", help=tr("send nothing: show the packets that would be sent"))
    p.add_argument("--profile", type=lambda s: int(s) - 1, help=tr("profile 1..3 (default: the active one)"))
    p.add_argument("--via", choices=["auto", "usb", "bt"], default="auto",
                   help=tr("connection: auto (cable if present, otherwise Bluetooth), usb or bt"))
    p.add_argument("--lang", choices=["auto", "en", "es"], default=None,
                   help=tr("language: auto (system), en or es"))
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help=tr("list connected keyboards")).set_defaults(func=cmd_list)
    sub.add_parser("info", help=tr("keyboard status")).set_defaults(func=cmd_info)
    sub.add_parser("gui", help=tr("open the graphical interface")).set_defaults(func=cmd_gui)

    sp = sub.add_parser("profile", help=tr("show/change the active profile (1..3)"))
    sp.add_argument("value", nargs="?", type=int, choices=[1, 2, 3])
    sp.set_defaults(func=cmd_profile)

    for target, helptext in (("light", tr("key lighting")), ("side", tr("side light strip"))):
        sp = sub.add_parser(target, help=helptext)
        sp.set_defaults(func=cmd_light, target=target)
        ss = sp.add_subparsers(dest="action", required=True)
        ss.add_parser("get", help=tr("show the current effect"))
        ss.add_parser("modes", help=tr("list modes"))
        st = ss.add_parser("set", help=tr("apply an effect"))
        st.add_argument("mode")
        st.add_argument("-b", "--brightness", type=int, default=4, help=tr("brightness 0..4 (4)"))
        st.add_argument("-s", "--speed", type=int, default=2, help=tr("speed 0..4 (2)"))
        st.add_argument("-c", "--color", default="#ffffff", help=tr("colour #RRGGBB or name"))
        st.add_argument("-r", "--rainbow", action="store_true", help=tr("rainbow colours"))
        st.add_argument("-o", "--option", help=tr("direction/variant (see 'modes')"))

    sp = sub.add_parser("keys", help=tr("remap keys"))
    sp.set_defaults(func=cmd_keys)
    ss = sp.add_subparsers(dest="action", required=True)
    sl = ss.add_parser("list", help=tr("show assignments"))
    sl.add_argument("--fn", action="store_true", help=tr("Fn layer"))
    ss.add_parser("names", help=tr("key names, functions and examples"))
    st = ss.add_parser("set", help=tr("assign an action to a key"))
    st.add_argument("key", help=tr("physical key (e.g. CapsLock, F1, r_Alt, slot:3)"))
    st.add_argument("value", help=tr("action (e.g. Esc, combo:ctrl+c, fn:vol+, macro:0, off, default)"))
    st.add_argument("--fn", action="store_true", help=tr("change the Fn layer (Fn + key)"))
    ss.add_parser("reset", help=tr("restore every key of the profile"))

    sp = sub.add_parser("macro", help="macros (0..49)")
    sp.set_defaults(func=cmd_macro)
    ss = sp.add_subparsers(dest="action", required=True)
    ss.add_parser("help", help=tr("macro format"))
    g = ss.add_parser("get")
    g.add_argument("index", type=int)
    st = ss.add_parser("set")
    st.add_argument("index", type=int)
    st.add_argument("events", help=tr("e.g.") + ' "down:ctrl, tap:c, up:ctrl"')
    st.add_argument("--repeat", type=int, default=1, help=tr("repetitions ('repeat N times' mode)"))
    c = ss.add_parser("clear")
    c.add_argument("index", type=int)

    sp = sub.add_parser("lcd", help=tr("screen: upload an image/GIF or sync the time"))
    sp.set_defaults(func=cmd_lcd)
    ss = sp.add_subparsers(dest="action", required=True)
    ss.add_parser("time", help=tr("sync date and time with the computer"))
    up = ss.add_parser("upload", help=tr("upload an image or GIF (cable only, not Bluetooth)"))
    up.add_argument("file")
    up.add_argument("--fit", choices=["contain", "cover", "stretch"], default="contain",
                    help=tr("contain=black bars, cover=crop, stretch=distort"))
    up.add_argument("--delay", type=int, help=tr("ms between frames (20..255). Default: the GIF's"))
    up.add_argument("--preview", metavar="OUT", help=tr("only save a 240x135 preview (uploads nothing)"))

    sp = sub.add_parser("settings", help=tr("polling rate, debounce, sleep, options"))
    sp.set_defaults(func=cmd_settings)
    sp.add_argument("--show", action="store_true")
    sp.add_argument("--report-rate", type=int, choices=[125, 250, 500, 1000])
    sp.add_argument("--debounce", type=int, help="ms (0..50)")
    sp.add_argument("--sleep", type=int, help=tr("minutes until sleep (wireless), 0 = never"))
    sp.add_argument("--deep-sleep", type=int, help=tr("minutes until deep sleep"))
    sp.add_argument("--win-lock", choices=["on", "off"])
    sp.add_argument("--mac", choices=["on", "off"], help=tr("Mac layout"))
    sp.add_argument("--wasd-swap", choices=["on", "off"], help=tr("swap WASD and arrows"))

    sp = sub.add_parser("reset", help=tr("restore factory values"))
    sp.add_argument("--yes", action="store_true")
    sp.set_defaults(func=cmd_reset)

    sp = sub.add_parser("raw", help=tr("(advanced) send a hex packet"))
    sp.add_argument("hex")
    sp.add_argument("--checksum", choices=["bit7", "bit8", "none"], default="bit7")
    sp.add_argument("--read", action="store_true", help=tr("read the answer"))
    sp.set_defaults(func=cmd_raw)
    return p


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    # el idioma tiene que estar listo antes de crear la ayuda de argparse
    for i, a in enumerate(argv):
        if a.startswith("--lang="):
            set_language(a.split("=", 1)[1])
        elif a == "--lang" and i + 1 < len(argv):
            set_language(argv[i + 1])
    args = build_parser().parse_args(argv)
    try:
        return args.func(args) or 0
    except (TransportError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
