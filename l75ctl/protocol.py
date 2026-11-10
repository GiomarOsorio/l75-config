"""Protocolo HID del ROYALAXE / ProtoArc L75 (firmware Rongyuan "YC500").

Todo lo de este archivo se obtuvo leyendo el driver oficial "ROYALAXE Driver"
(app Electron de Rongyuan). Ver docs/PROTOCOLO.md para el detalle.

Resumen del transporte:
  * Interfaz HID 2, usage page 0xFFFF, usage 0x02.
  * Cada comando es un "feature report" de 64 bytes (report ID 0).
  * El primer byte es el comando. Los comandos de lectura tienen el bit 7
    puesto (0x80 | cmd) y la respuesta se lee con GET_FEATURE.
  * Checksum "BIT7": byte[7] = 0xFF - (suma(bytes[0..6]) & 0xFF).
    Checksum "BIT8": byte[8] = 0xFF - (suma(bytes[0..7]) & 0xFF)
    (se usa en comandos de luz, porque el byte 7 lleva el color azul).
"""

from __future__ import annotations

from enum import Enum, IntEnum

VID = 0x3151
PID_WIRED = 0x4015
# Receptores 2.4 GHz de Rongyuan (protocolo "dongle", aun no soportado).
PID_DONGLES = (0x4011, 0x4014, 0x4017)
# Bluetooth (BLE / HOGP). Los PID son los que el driver oficial marca como
# "isblue". El L75 usa 0x4012 (nombre "L75 BT5.0").
PID_BLUETOOTH = (0x4012, 0x4013, 0x401C, 0x401D, 0x401F, 0x4020, 0x4023, 0x4024)
BLE_USAGE_PAGES = (0xFF66, 0xFF55)
BLE_USAGE = 0x0202
BLE_REPORT_ID = 6
BLE_REPORT_SIZE = 66      # report ID + 65 bytes
BLE_CMD_MARKER = 0x55     # [0x06, 0x55, comando...] (envio y respuesta)
BLE_EVENT_MARKER = 0x66   # [0x06, 0x66, ...] -> evento del teclado, no respuesta
USAGE_PAGE = 0xFFFF
USAGE = 0x02
INTERFACE = 2

# ID de modelo que devuelve el comando 0x8F (bytes 1-2, LE). El driver oficial
# tiene dos entradas para el L75: 1007 y 820 (verificado: un L75 real devuelve 820).
DEVICE_ID_L75 = 1007
DEVICE_IDS_L75 = (1007, 820)

PACKET_SIZE = 64
REPORT_ID = 0

# Pantalla TFT del L75
LCD_WIDTH = 240
LCD_HEIGHT = 135
LCD_MAX_FRAMES = 122  # calculado como el driver: 8 MiB de flash / 64 KiB por cuadro - 5

NUM_PROFILES = 3
NUM_FN_LAYERS = 1
MACRO_MAX = 50
MACRO_BUFFER = 256
MACRO_MAX_BYTES = 248
MATRIX_SLOTS = 128


class Checksum(Enum):
    BIT7 = 0
    BIT8 = 1
    NONE = 2


class Cmd(IntEnum):
    # --- escritura ---
    SET_RESET = 0x02            # restaurar valores de fabrica
    SET_REPORT = 0x04           # tasa de sondeo
    SET_PROFILE = 0x05          # perfil activo
    SET_KBOPTION = 0x06         # opciones del teclado (bloqueo Win, Mac, WASD...)
    SET_LEDPARAM = 0x07         # efecto de luz de las teclas
    SET_SLEDPARAM = 0x08        # efecto de la tira lateral
    SET_DEBOUNCE = 0x11
    SET_SLEEPTIME = 0x12
    SET_KEYMATRIX_SIMPLE = 0x13  # reasignar UNA tecla
    SET_USERPIC_SIMPLE = 0x14    # color de UNA tecla (modo imagen de usuario)
    SET_FN_SIMPLE = 0x15         # reasignar UNA tecla en la capa Fn
    SET_MACRO_SIMPLE = 0x16      # escribir una macro (paginas de 56 bytes)
    SET_TFTLCD_DATA = 0x25       # datos de imagen para la pantalla
    SET_OLED_CLOCK = 0x28        # fecha/hora de la pantalla
    # --- lectura ---
    GET_REV = 0x80
    GET_BATTERY = 0x83
    GET_REPORT = 0x84
    GET_PROFILE = 0x85
    GET_KBOPTION = 0x86
    GET_LEDPARAM = 0x87
    GET_SLEDPARAM = 0x88
    GET_KEYMATRIX = 0x89
    GET_MACRO = 0x8B
    GET_USERPIC = 0x8C
    GET_INFOR = 0x8F
    GET_FN_KEYMATRIX = 0x90
    GET_DEBOUNCE = 0x91
    GET_SLEEPTIME = 0x92
    GET_TFTLCD_DATA = 0xA5       # cabecera/preparacion de subida de imagen


# Comandos que NUNCA se deben enviar desde esta herramienta: entran en modo
# bootloader / borran flash / actualizan firmware. Un error aqui puede dejar
# el teclado inutilizable.
FORBIDDEN_CMDS = frozenset({
    0x7F,  # bootloader MCU
    0x30, 0x31, 0xB0, 0xB1,  # bootloader / checksum OLED
    0x40, 0x41, 0xC0, 0xC1,  # bootloader / checksum MLED
    0xAC,  # borrar chip de flash
})


def apply_checksum(buf: bytearray, kind: Checksum) -> bytearray:
    """Escribe el checksum en su lugar (modifica y devuelve ``buf``)."""
    if kind is Checksum.BIT7:
        buf[7] = 0xFF - (sum(buf[0:7]) & 0xFF)
    elif kind is Checksum.BIT8:
        buf[8] = 0xFF - (sum(buf[0:8]) & 0xFF)
    return buf


def packet(*head: int, data: bytes | list[int] | None = None, at: int = 8) -> bytearray:
    """Construye un paquete de 64 bytes.

    ``head`` son los primeros bytes (comando y parametros). ``data`` se copia a
    partir de la posicion ``at`` (por defecto 8, despues del checksum BIT7).
    """
    buf = bytearray(PACKET_SIZE)
    if len(head) > PACKET_SIZE:
        raise ValueError("cabecera demasiado larga")
    for i, b in enumerate(head):
        buf[i] = b & 0xFF
    if data is not None:
        data = bytes(data)
        if at + len(data) > PACKET_SIZE:
            raise ValueError("datos demasiado largos para un paquete")
        buf[at:at + len(data)] = data
    return buf


def u16le(value: int) -> tuple[int, int]:
    return value & 0xFF, (value >> 8) & 0xFF


REPORT_RATE_CODES = {1000: 1, 500: 2, 250: 4, 125: 8}
REPORT_RATE_FROM_CODE = {v: k for k, v in REPORT_RATE_CODES.items()}
