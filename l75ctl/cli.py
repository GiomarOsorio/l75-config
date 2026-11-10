"""Linea de comandos: ``l75 <comando>``. Ejecuta ``l75 -h`` para ver la ayuda."""

from __future__ import annotations

import argparse
import sys

from . import __version__
from . import lighting as L
from . import protocol as P
from .keyboard import L75, SleepTimes
from .keymap import FUNCTIONS, KEYS, MOUSE, find_key, is_system, parse_action
from .macros import Macro, parse_macro_text
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
        print("No se encontro ningun L75 (ni por cable ni por Bluetooth).")
        return 1
    for d in devs:
        tipo = {"usb": "cable", "bt": "Bluetooth", "dongle": "receptor 2.4G (no soportado aun)"}[d.bus]
        print(f"{d.path.decode(errors='replace')}  {d.vid:04x}:{d.pid:04x}  if={d.interface}  "
              f"{d.manufacturer} {d.product}  [{tipo}]")
    return 0


def cmd_info(args):
    with _open(args) as kb:
        print(f"Conexion:      {'Bluetooth' if kb.bus == 'bt' else 'demo' if kb.is_demo else 'cable USB'}")
        fw = kb.firmware_version()
        print(f"Firmware:      {fw >> 8}.{fw & 0xFF:02d} (0x{fw:04X})")
        did = kb.device_id()
        print(f"ID modelo:     {did}" + (" (L75)" if did in P.DEVICE_IDS_L75 else "  ⚠ no es un L75 conocido"))
        print(f"Perfil activo: {kb.profile + 1}")
        pct, st = kb.battery()
        print(f"Bateria:       {pct}% ({st})")
        print(f"Tasa sondeo:   {kb.get_report_rate()} Hz")
        print(f"Debounce:      {kb.get_debounce()} ms")
        print(f"Luz teclas:    {kb.get_light().describe()}")
        print(f"Tira lateral:  {kb.get_side_light().describe(side=True)}")
    return 0


def cmd_profile(args):
    with _open(args) as kb:
        if args.value is None:
            print(f"Perfil activo: {kb.get_profile() + 1}")
        else:
            kb.set_profile(args.value - 1)
            print(f"Perfil {args.value} activado")
    return 0


def _light_from_args(args, side: bool) -> L.LightSetting:
    table = L.SIDE_MODE_BY_KEY if side else L.MODE_BY_KEY
    if args.mode not in table:
        raise SystemExit("modo invalido. Usa 'l75 light modes'")
    m = table[args.mode]
    opt = args.option
    if opt is not None and m.kind != "picture" and opt not in m.options:
        raise SystemExit(f"opcion invalida para {m.key}: {', '.join(m.options) or '(ninguna)'}")
    return L.LightSetting(mode=args.mode, brightness=args.brightness, speed=args.speed,
                          color=L.parse_color(args.color), rainbow=args.rainbow, option=opt)


def cmd_light(args):
    side = args.target == "side"
    if args.action == "modes":
        for m in (L.SIDE_MODES if side else L.MODES):
            extra = []
            if m.speed:
                extra.append("velocidad")
            if m.color:
                extra.append("color/arcoiris")
            if m.options:
                extra.append("opciones: " + "|".join(m.options))
            if m.kind == "picture":
                extra.append("opcion: capa 1..5")
            print(f"  {m.key:<13} {m.label:<40} {', '.join(extra)}")
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
        print("Teclas fisicas del L75 (usa estos nombres en 'l75 keys set'):")
        print("  " + ", ".join(k.name for k in KEYS))
        print("\nFunciones (fn:<nombre>):")
        for k, label, _ in FUNCTIONS:
            print(f"  {k:<11} {label}")
        print("\nRaton (mouse:<nombre>):  " + ", ".join(k for k, _, _ in MOUSE))
        print("\nEjemplos de acciones: Esc | key:F5 | combo:ctrl+shift+t | fn:vol+ | mouse:left |"
              " macro:0 | macro:0:hold | off | default")
        return 0
    with _open(args) as kb:
        if args.action == "list":
            acts = kb.read_matrix(fn=args.fn, progress=None)
            capa = "Fn" if args.fn else f"perfil {kb.profile + 1}"
            print(f"Asignaciones ({capa}):")
            for k in KEYS:
                a = acts[k.slot]
                mark = "" if (args.fn or a == k.default_action) else "   <- cambiada"
                print(f"  {k.name:<12} slot {k.slot:>3}  {a.describe()}{mark}")
        elif args.action == "set":
            key = find_key(args.key)
            if args.value.lower() == "default":
                if args.fn:
                    raise ValueError("en la capa Fn no hay valor 'default' conocido; usa una accion concreta")
                act = key.default_action
            else:
                act = parse_action(args.value)
            if key.default_action.raw == (10, 1, 0, 0):
                raise ValueError("la tecla Fn no se puede reasignar")
            if args.fn:
                cur = kb.read_matrix(fn=True)[key.slot]
                if is_system(cur.raw):
                    raise ValueError(f"Fn + {key.name} es una tecla del sistema ({cur.describe()}): "
                                     "el driver oficial no deja cambiarla")
            kb.set_key(key, act, fn=args.fn)
            print(f"{key.name} -> {act.describe()}" + (" (capa Fn)" if args.fn else f" (perfil {kb.profile + 1})"))
        elif args.action == "reset":
            for k in KEYS:
                kb.set_key(k, k.default_action)
            print(f"Teclas del perfil {kb.profile + 1} restauradas")
    return 0


def cmd_macro(args):
    if args.action == "help":
        print("Formato: down:<tecla>, up:<tecla>, tap:<tecla>, delay:<ms>, down:mouse-left, move:dx,dy")
        print('Ejemplo: l75 macro set 0 "down:ctrl, tap:c, up:ctrl, delay:50, tap:enter" --repeat 1')
        print("Luego asignala: l75 keys set F1 macro:0        (o macro:0:hold / macro:0:toggle)")
        return 0
    with _open(args) as kb:
        if args.action == "get":
            m = kb.read_macro(args.index)
            print(f"Macro {args.index}: repetir {m.repeat} vez/veces, {len(m.events)} eventos")
            for e in m.events:
                print("  " + e.describe())
            print("Texto:", m.to_text())
        elif args.action == "set":
            m = Macro(parse_macro_text(args.events), args.repeat)
            kb.write_macro(args.index, m)
            print(f"Macro {args.index} guardada ({len(m.events)} eventos)")
        elif args.action == "clear":
            kb.write_macro(args.index, Macro([], 0))
            print(f"Macro {args.index} borrada")
    return 0


def cmd_lcd(args):
    from . import lcd
    if args.action == "time":
        with _open(args) as kb:
            t = kb.sync_clock()
        print("Hora sincronizada:", t.strftime("%Y-%m-%d %H:%M:%S"))
        return 0
    anim = lcd.load_animation(args.file, fit=args.fit, delay_ms=args.delay)
    box = lcd.content_box(anim.frames)
    print(f"{len(anim.frames)} cuadro(s), retardo {anim.delay_ms} ms, area {box.width}x{box.height}, "
          f"{lcd.estimate_packets(anim)} paquetes")
    if args.preview:
        out = args.preview
        if len(anim.frames) > 1:
            anim.frames[0].save(out, save_all=True, append_images=anim.frames[1:],
                                duration=anim.delay_ms or 100, loop=0)
        else:
            anim.frames[0].save(out)
        print("Vista previa guardada en", out)
        return 0
    if args.dry_run:
        print("(dry-run: no se muestran los paquetes de imagen, solo la cabecera)")
        print("TX " + lcd.header_packet(len(anim.frames), anim.delay_ms,
                                        box.width * box.height * 2, box).hex(" "))
        return 0
    with _open(args) as kb:
        kb.upload_animation(anim, progress=_progress)
        print("Listo. En el teclado: Fn+Ctrl alterna entre tu animacion y el estilo por defecto.")
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
            print(f"Tasa de sondeo: {kb.get_report_rate()} Hz")
            print(f"Debounce:       {kb.get_debounce()} ms")
            print(f"Reposo:         BT {s.bt // 60} min / 2.4G {s.rf24 // 60} min; profundo BT "
                  f"{s.deep_bt // 60} min / 2.4G {s.deep_rf24 // 60} min")
            print(f"Bloqueo Win:    {'si' if o.win_lock else 'no'}")
            print(f"Modo Mac:       {'si' if o.mac_mode else 'no'}")
            print(f"WASD<->flechas: {'si' if o.wasd_arrows_swap else 'no'}")
        else:
            print("Ajustes guardados")
    return 0


def cmd_reset(args):
    if not args.yes:
        print("Esto restaura TODO el teclado a valores de fabrica (teclas, macros, luces).")
        if input("Escribe 'si' para continuar: ").strip().lower() not in ("si", "sí", "yes"):
            print("Cancelado")
            return 1
    with _open(args) as kb:
        kb.factory_reset()
    print("Teclado restaurado a fabrica")
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
            print("enviado")
    return 0


def cmd_gui(args):
    from .gui import run
    return run(demo=args.demo)


# ------------------------------------------------------------------ parser
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="l75", description="Configurador para Linux del teclado ROYALAXE / ProtoArc L75")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    p.add_argument("--demo", action="store_true", help="usar un teclado simulado (sin hardware)")
    p.add_argument("--dry-run", action="store_true", help="no enviar nada: mostrar los paquetes que se enviarian")
    p.add_argument("--profile", type=lambda s: int(s) - 1, help="perfil 1..3 (por defecto el activo)")
    p.add_argument("--via", choices=["auto", "usb", "bt"], default="auto",
                   help="conexion: auto (cable si esta, si no Bluetooth), usb o bt")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="listar teclados conectados").set_defaults(func=cmd_list)
    sub.add_parser("info", help="estado del teclado").set_defaults(func=cmd_info)
    sub.add_parser("gui", help="abrir la interfaz grafica").set_defaults(func=cmd_gui)

    sp = sub.add_parser("profile", help="ver/cambiar perfil activo (1..3)")
    sp.add_argument("value", nargs="?", type=int, choices=[1, 2, 3])
    sp.set_defaults(func=cmd_profile)

    for target, helptext in (("light", "iluminacion de las teclas"), ("side", "tira de luz lateral")):
        sp = sub.add_parser(target, help=helptext)
        sp.set_defaults(func=cmd_light, target=target)
        ss = sp.add_subparsers(dest="action", required=True)
        ss.add_parser("get", help="ver efecto actual")
        ss.add_parser("modes", help="listar modos")
        st = ss.add_parser("set", help="aplicar efecto")
        st.add_argument("mode")
        st.add_argument("-b", "--brightness", type=int, default=4, help="brillo 0..4 (4)")
        st.add_argument("-s", "--speed", type=int, default=2, help="velocidad 0..4 (2)")
        st.add_argument("-c", "--color", default="#ffffff", help="color #RRGGBB o nombre")
        st.add_argument("-r", "--rainbow", action="store_true", help="colores arcoiris")
        st.add_argument("-o", "--option", help="direccion/variante (ver 'modes')")

    sp = sub.add_parser("keys", help="reasignar teclas")
    sp.set_defaults(func=cmd_keys)
    ss = sp.add_subparsers(dest="action", required=True)
    sl = ss.add_parser("list", help="ver asignaciones")
    sl.add_argument("--fn", action="store_true", help="capa Fn")
    ss.add_parser("names", help="nombres de teclas, funciones y ejemplos")
    st = ss.add_parser("set", help="asignar accion a una tecla")
    st.add_argument("key", help="tecla fisica (ej: CapsLock, F1, r_Alt, slot:3)")
    st.add_argument("value", help="accion (ej: Esc, combo:ctrl+c, fn:vol+, macro:0, off, default)")
    st.add_argument("--fn", action="store_true", help="modificar la capa Fn (Fn + tecla)")
    ss.add_parser("reset", help="restaurar todas las teclas del perfil")

    sp = sub.add_parser("macro", help="macros (0..49)")
    sp.set_defaults(func=cmd_macro)
    ss = sp.add_subparsers(dest="action", required=True)
    ss.add_parser("help", help="formato de macros")
    g = ss.add_parser("get")
    g.add_argument("index", type=int)
    st = ss.add_parser("set")
    st.add_argument("index", type=int)
    st.add_argument("events", help='ej: "down:ctrl, tap:c, up:ctrl"')
    st.add_argument("--repeat", type=int, default=1, help="repeticiones (modo 'repetir N veces')")
    c = ss.add_parser("clear")
    c.add_argument("index", type=int)

    sp = sub.add_parser("lcd", help="pantalla: subir imagen/GIF o sincronizar hora")
    sp.set_defaults(func=cmd_lcd)
    ss = sp.add_subparsers(dest="action", required=True)
    ss.add_parser("time", help="sincronizar fecha y hora con el PC")
    up = ss.add_parser("upload", help="subir imagen o GIF (solo por cable, no por Bluetooth)")
    up.add_argument("file")
    up.add_argument("--fit", choices=["contain", "cover", "stretch"], default="contain",
                    help="contain=bandas negras, cover=recortar, stretch=estirar")
    up.add_argument("--delay", type=int, help="ms entre cuadros (20..255). Por defecto el del GIF")
    up.add_argument("--preview", metavar="SALIDA", help="solo guardar vista previa 240x135 (no sube nada)")

    sp = sub.add_parser("settings", help="tasa de sondeo, debounce, reposo, opciones")
    sp.set_defaults(func=cmd_settings)
    sp.add_argument("--show", action="store_true")
    sp.add_argument("--report-rate", type=int, choices=[125, 250, 500, 1000])
    sp.add_argument("--debounce", type=int, help="ms (0..50)")
    sp.add_argument("--sleep", type=int, help="minutos hasta reposo (inalambrico), 0 = nunca")
    sp.add_argument("--deep-sleep", type=int, help="minutos hasta reposo profundo")
    sp.add_argument("--win-lock", choices=["on", "off"])
    sp.add_argument("--mac", choices=["on", "off"], help="distribucion Mac")
    sp.add_argument("--wasd-swap", choices=["on", "off"], help="intercambiar WASD y flechas")

    sp = sub.add_parser("reset", help="restaurar valores de fabrica")
    sp.add_argument("--yes", action="store_true")
    sp.set_defaults(func=cmd_reset)

    sp = sub.add_parser("raw", help="(avanzado) enviar un paquete hex")
    sp.add_argument("hex")
    sp.add_argument("--checksum", choices=["bit7", "bit8", "none"], default="bit7")
    sp.add_argument("--read", action="store_true", help="leer respuesta")
    sp.set_defaults(func=cmd_raw)
    return p


def main(argv=None) -> int:
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
