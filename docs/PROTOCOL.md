# ROYALAXE / ProtoArc L75 USB and Bluetooth protocol

## Source

The "Windows" link on ProtoArc's website only downloads the Visual C++ runtime, so the **official Mac
driver** was used ("ROYALAXE Driver 1.0.0", `ROYALAXE Driver for Mac.dmg`, *Support → User Manual* page
on protoarc.com). It is an Electron app by the OEM **Rongyuan** (author `rongyuan` in `package.json`), the
same company that makes drivers for Epomaker, Akko, MonsGeek and others.

- `Contents/Resources/app/dist/index.js`: JavaScript logic (Parcel bundle). The whole protocol is here.
- `Contents/Resources/app/iot_driver`: Rust binary that opens the HID device and exposes gRPC (port 3814).
  It only forwards bytes (`sendMsg`, `readMsg`, `sendRawFeature`…) and applies the checksum.

The L75 is the `yc500_l75_soc` device (internal id 1007), class
`YC500_L75_SOC → YC500ROYALAXECommon → YC500Common → YC200Common → YZW_3098 → YZW_K68 → YZWCommon → RY108 → K68 → Dk2017 → USBDevice`.
When a child class redefines a method, the most specific version wins. The tables below already reflect
that resolution.

## Transport

| | |
|---|---|
| VID:PID (cable) | `3151:4015` (shared with other Rongyuan keyboards) |
| Interface | 2, usage page `0xFFFF`, usage `0x02` |
| Write | `SET_FEATURE`, report ID 0, 64 data bytes (65 with the ID) |
| Read | `GET_FEATURE`, report ID 0, read right after sending the query command |
| BIT7 checksum (type 0) | `buf[7] = 0xFF - (sum(buf[0..6]) & 0xFF)` |
| BIT8 checksum (type 1) | `buf[8] = 0xFF - (sum(buf[0..7]) & 0xFF)` (lighting commands) |
| Delays | about 10 ms before each write and 5 ms before reading. Image data goes every 1 ms |

## Bluetooth (BLE). Verified with a real L75 (firmware 1.17)

Over Bluetooth the L75 shows up as `3151:4012` ("L75 BT5.0"). Its HID descriptor includes a vendor
collection with usage page `0xFF66` and usage `0x0202`, report ID 6, 65-byte input and output.
The format was obtained by disassembling `iot_driver` (`BleHid::send_msg`, `HidBLE::send_feature`, the
reader thread in `HidBLE::new`) and confirmed with the keyboard:

- **Send:** OUTPUT report `[0x06, 0x55, 64-byte command]`. It is an `hid_write`, not a feature report.
  The command and its checksum are the same as over the cable.
- **Answer:** INPUT report `[0x06, 0x55, echoed command, data…]` → `payload = r[2:]`.
- **Events:** `[0x06, 0x66, type, …]`, for example `66 03 00 09` or `66 0f 01`. The keyboard sends them on
  its own (lighting change, wake-up…) and they are ignored.
- `GET_REPORT`/`GET_FEATURE` reads do not work over BLE on Linux (EIO). The answer arrives as an input
  report.
- Screen/music use another header, `[0x06, 0x56, 0x0C, …]`, not implemented.
- The official app blocks image upload and firmware updates over BT.

## Commands used

Bytes written as `[position]=value`. All use the BIT7 checksum except where marked.

| Cmd | Name | Format |
|---|---|---|
| `0x02` | factory reset | – |
| `0x04` / `0x84` | polling rate | `[1]=profile [2]=code` (1=1000, 2=500, 4=250, 8=125 Hz). Answer `[2]` |
| `0x05` / `0x85` | active profile | `[1]=profile 0..2`. Answer `[1]` |
| `0x06` / `0x86` | options | `[1]=profile [2]=bits [3]=fn [4]=power saving`. bits: 0 Win lock, 2 Mac, 3 WASD↔arrows, 4 LED off, 5 strip off, 6 mode, 7 lock |
| `0x07` / `0x87` | key lighting (**BIT8**) | `[1]=mode [2]=4-speed [3]=brightness 0..4 [4]=(option<<4)\|colour [5..7]=RGB` |
| `0x08` / `0x88` | side strip (**BIT8**) | `[1]=mode [2]=speed [3]=brightness [4]=(option<<4)\|colour [5..7]=RGB` |
| `0x11` / `0x91` | debounce | `[2]=ms`. Answer `[2]` |
| `0x12` / `0x92` | sleep | write: `[8..15]` 4×uint16 LE (bt, 2.4G, deep bt, deep 2.4G) in seconds. Answer in `[1..8]` |
| `0x13` | key (simple) | `[1]=profile [2]=slot [8..11]=action` |
| `0x14` | key colour | `[1]=layer [2]=slot [8..10]=RGB` |
| `0x15` | Fn-layer key | `[1]=Fn layer (0) [2]=slot [8..11]=action` |
| `0x16` | macro | `[1]=index 0..49 [2]=page [3]=56 [4]=last?1:0 [8..63]=56 bytes` |
| `0x25` | screen data | see below |
| `0x28` | clock | `[8]=year>>8 [9]=year&255 [10]=month [11]=day [12]=h [13]=min [14]=s` |
| `0x80` | firmware version | answer `[1..2]` uint16 LE |
| `0x83` | battery | answer `[1]=%` `[2]=0 discharging / 1 charging / 2 full` |
| `0x89` | read matrix | `[1]=profile [2]=page 0..7`. Each answer = 64 bytes of matrix |
| `0x8B` | read macro | `[1]=index [2]=page 0..3`. 4×64 = 256 bytes |
| `0x8C` | read colours | `[1]=0 [2]=page 0..5`. 128 slots × RGB |
| `0x90` | read Fn matrix | `[1]=layer [2]=page 0..7` |
| `0xA5` | prepare image | see below. Answer `[1]==1` = ready |

**Blocked commands** in this app (firmware/bootloader): `0x7F`, `0x30/0x31/0xB0/0xB1`,
`0x40/0x41/0xC0/0xC1`, `0xAC`.

## Key matrix

512 bytes = 128 slots × 4 bytes. Ordered by physical columns, 6 rows per column. The default matrix is in
`l75ctl/l75_data.py`.

| Bytes | Action |
|---|---|
| `0,0,hid,0` | key |
| `0,m,hid,hid2` | combination (m is usually a modifier `0xE0`–`0xE7`) |
| `1,0,240..248,x` | mouse (240 left, 241 right, 242 middle, 243 back, 244 forward, 245 wheel±) |
| `3,0,lo,hi` | consumer/media (e.g. `3,0,205,0` play/pause) |
| `9,mode,n,0` | macro n (mode 0 = N times, 1 = on/off, 2 = while held) |
| `10,1,0,0` | Fn |
| `0,0,0,0` | disabled |

## Macros (256-byte buffer, 248 usable)

```
[rep_lo, rep_hi]  then events:
[code, attr]            code 0x04–0xEF key, 0xF0–0xF8 mouse, 0xF9 move (+dx, dy)
                        attr bit7 = press; bits0–6 = next delay if ≤127 ms
[lo, hi]                uint16 delay if it did not fit in attr (0,0 if no delay)
```
It is sent in 56-byte pages (only the ones with data).

## Lighting: key modes (cmd 0x07)

0 off, 1 static, 2 breathing, 3 neon, 4 wave (direction option: right/left/down/up), 5 ripple,
6 raindrops, 7 snake (z/back and forth), 8 reactive, 9 converge, 10 sine wave, 11 kaleidoscope
(out/in), 12 line (right/left), 13 user picture (`[4]` = layer×16, RGB `0,200,200`),
14 laser, 15 circle (counter-clockwise/clockwise), 16 dazzling, 17 rain, 18 meteor,
19 reverse reactive, 20 music 1, 21 screen colour, 22 music 2.

Low nibble of `[4]`: `8` = rainbow, `7` = RGB colour, `0..6` = preset colour (red, orange, yellow, green,
cyan, blue, purple). For the music modes it is `0` = rainbow and `4` = colour.
The driver replaces white `FFFFFF` with `FAFFFA`.

## TFT screen (240×135, RGB565)

1. Header `0xA5`:
   `[1]=current frame (0) [2]=frame count [3]=delay ms [4,5,16,17]=bytes per frame (uint32 LE)
   [8..11]=left,top,right,bottom (low) [12..15]=(high)`.
   Read: if `[1]==1` the screen is ready. Otherwise retry up to 10 times every 100 ms.
2. For each frame, `0x25` packets:
   `[1]=frame [2]=frame count [3]=delay [4..5]=packet number LE [6]=valid bytes (≤56) [8..63]=data`.
3. Data: only the rectangle with non-black pixels (union of all frames). It is walked by **columns**
   (x outside, y inside) and each pixel is RGB565 **big-endian**.
4. Limit: 122 frames (8 MiB of flash / 64 KiB per frame − 5).

## Pending / not verified

- The USB cable path has not been tested on the real keyboard yet. Bluetooth has: reading info, lighting,
  the matrix, and a lighting write confirmed by reading it back.
- 2.4 GHz receiver (`3151:4011/4014/4017`): the driver uses a different "dongle_common" wrapper. Not
  implemented.
- `0x8F` returns the model ID in `[1..2]` LE. A real L75 returned 820, which the driver table also lists
  as "L75".
- The factory default of the Fn layer is only known from one real L75 (see below), so
  `keys set --fn ... default` is not allowed.

## Fn layer: system functions

Read from a real L75 (firmware 1.17); the names come from the official manual. The official driver does
not let you change these keys: it paints them red and warns "system key" (`系统按键无法修改`). The same
goes for the Fn key itself (`[10, 1, 0, 0]`). Driver rule: in the Fn layer, every value of type 2, 8, 10,
13, 14, 18 or 19 that is not a basic media function is locked.

| Value | Key (Fn +) | Function |
|---|---|---|
| `[10, 2, 0, 0]` | Esc | Reset the keyboard |
| `[10, 3, 0, 0]` | Win | Lock the Windows key (unconfirmed) |
| `[10, 5, 2/1/0, 0]` | I / O / P | iOS / Mac / Windows layout |
| `[10, 8, 0, 0]` | = | Battery indicator |
| `[10, 12, 0, 0]` | Del | Turn the lighting on / off |
| `[13, 1, 0, 0]` | Ins | Next lighting effect |
| `[13, 2, 1/2, 0]` | ↑ / ↓ | Lighting brightness up / down |
| `[13, 3, 1/2, 0]` | ← / → | Lighting speed down / up |
| `[13, 5, 1, 0]` | Backspace | Next lighting colour (single colour) |
| `[13, 8, 0, 0]` | PgUp | Side strip mode / off (unconfirmed) |
| `[14, 0, 0/1/2, 0]` | Q / W / E | Bluetooth channel 1 / 2 / 3 (hold: pair) |
| `[14, 0, 5, 0]` | R | 2.4 GHz channel (unconfirmed) |
| `[19, 0, 0, 0]` | Ctrl, RCtrl | Screen: your image or the default style |
| `[19, 2, 0, 0]` | PgDn | Screen: another view (unconfirmed) |

The other Fn-layer keys (F1–F12, 4, ;) are normal actions (media and combinations) and can be changed.
