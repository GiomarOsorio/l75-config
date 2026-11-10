# Protocolo USB del ROYALAXE / ProtoArc L75

## Origen

El enlace "Windows" de la web de ProtoArc solo descarga el runtime de Visual C++, así que se usó el
**driver oficial para Mac** ("ROYALAXE Driver 1.0.0", `ROYALAXE Driver for Mac.dmg`, página
*Support → User Manual* de protoarc.com). Es una app Electron del fabricante OEM **Rongyuan** (autor
`rongyuan` en `package.json`), el mismo que hace drivers para Epomaker, Akko, MonsGeek y otros.

- `Contents/Resources/app/dist/index.js`: lógica en JavaScript (bundle Parcel). Aquí está todo el protocolo.
- `Contents/Resources/app/iot_driver`: binario Rust que abre el HID y expone gRPC (puerto 3814).
  Solo reenvía bytes (`sendMsg`, `readMsg`, `sendRawFeature`…) y aplica el checksum.

El L75 es el dispositivo `yc500_l75_soc` (id interno 1007), clase
`YC500_L75_SOC → YC500ROYALAXECommon → YC500Common → YC200Common → YZW_3098 → YZW_K68 → YZWCommon → RY108 → K68 → Dk2017 → USBDevice`.
Cuando una clase hija redefine un método, gana la versión más específica. Las tablas siguientes ya
reflejan esa resolución.

## Transporte

| | |
|---|---|
| VID:PID (cable) | `3151:4015` (compartido con otros teclados Rongyuan) |
| Interfaz | 2, usage page `0xFFFF`, usage `0x02` |
| Escritura | `SET_FEATURE`, report ID 0, 64 bytes de datos (65 con el ID) |
| Lectura | `GET_FEATURE`, report ID 0. Se lee justo después de enviar el comando de consulta |
| Checksum BIT7 (tipo 0) | `buf[7] = 0xFF - (sum(buf[0..6]) & 0xFF)` |
| Checksum BIT8 (tipo 1) | `buf[8] = 0xFF - (sum(buf[0..7]) & 0xFF)` (comandos de luz) |
| Pausas | unos 10 ms antes de cada escritura y 5 ms antes de leer. Los datos de imagen van cada 1 ms |

## Bluetooth (BLE). Verificado con un L75 real (firmware 1.17)

Por Bluetooth el L75 aparece como `3151:4012` ("L75 BT5.0"). Su descriptor HID incluye una colección
del fabricante con usage page `0xFF66` y usage `0x0202`, report ID 6, input y output de 65 bytes.
El formato se obtuvo desensamblando `iot_driver` (`BleHid::send_msg`, `HidBLE::send_feature`,
el hilo lector de `HidBLE::new`) y se confirmó con el teclado:

- **Enviar:** OUTPUT report `[0x06, 0x55, comando de 64 bytes]`. Es un `hid_write`, no un feature
  report. El comando y su checksum son idénticos a los de cable.
- **Respuesta:** INPUT report `[0x06, 0x55, comando en eco, datos…]` → `payload = r[2:]`.
- **Eventos:** `[0x06, 0x66, tipo, …]`, por ejemplo `66 03 00 09` o `66 0f 01`. Los manda el teclado
  por su cuenta (cambio de luz, despertar…) y se ignoran.
- Las lecturas `GET_REPORT`/`GET_FEATURE` no funcionan por BLE en Linux (EIO). La respuesta llega
  como input report.
- La pantalla/música usan otra cabecera, `[0x06, 0x56, 0x0C, …]`, no implementada.
- La app oficial bloquea por BT la subida de imágenes y la actualización de firmware.

## Comandos usados

Bytes indicados como `[posición]=valor`. Todos llevan checksum BIT7 salvo los marcados.

| Cmd | Nombre | Formato |
|---|---|---|
| `0x02` | reset fábrica | – |
| `0x04` / `0x84` | tasa de sondeo | `[1]=perfil [2]=código` (1=1000, 2=500, 4=250, 8=125 Hz). Respuesta `[2]` |
| `0x05` / `0x85` | perfil activo | `[1]=perfil 0..2`. Respuesta `[1]` |
| `0x06` / `0x86` | opciones | `[1]=perfil [2]=bits [3]=fn [4]=ahorro`. bits: 0 bloqueo Win, 2 Mac, 3 WASD↔flechas, 4 LED off, 5 tira off, 6 modo, 7 bloqueo |
| `0x07` / `0x87` | luz teclas (**BIT8**) | `[1]=modo [2]=4-velocidad [3]=brillo 0..4 [4]=(opción<<4)\|color [5..7]=RGB` |
| `0x08` / `0x88` | tira lateral (**BIT8**) | `[1]=modo [2]=velocidad [3]=brillo [4]=(opción<<4)\|color [5..7]=RGB` |
| `0x11` / `0x91` | debounce | `[2]=ms`. Respuesta `[2]` |
| `0x12` / `0x92` | reposo | escribir: `[8..15]` 4×uint16 LE (bt, 2.4G, profundo bt, profundo 2.4G) en segundos. Respuesta en `[1..8]` |
| `0x13` | tecla (simple) | `[1]=perfil [2]=slot [8..11]=acción` |
| `0x14` | color de tecla | `[1]=capa [2]=slot [8..10]=RGB` |
| `0x15` | tecla capa Fn | `[1]=capa Fn (0) [2]=slot [8..11]=acción` |
| `0x16` | macro | `[1]=índice 0..49 [2]=página [3]=56 [4]=última?1:0 [8..63]=56 bytes` |
| `0x25` | datos de pantalla | ver más abajo |
| `0x28` | reloj | `[8]=año>>8 [9]=año&255 [10]=mes [11]=día [12]=h [13]=min [14]=s` |
| `0x80` | versión firmware | respuesta `[1..2]` uint16 LE |
| `0x83` | batería | respuesta `[1]=%` `[2]=0 descargando / 1 cargando / 2 lleno` |
| `0x89` | leer matriz | `[1]=perfil [2]=página 0..7`. Cada respuesta = 64 bytes de matriz |
| `0x8B` | leer macro | `[1]=índice [2]=página 0..3`. 4×64 = 256 bytes |
| `0x8C` | leer colores | `[1]=0 [2]=página 0..5`. 128 slots × RGB |
| `0x90` | leer matriz Fn | `[1]=capa [2]=página 0..7` |
| `0xA5` | preparar imagen | ver más abajo. Respuesta `[1]==1` = lista |

**Comandos bloqueados** en esta app (firmware/bootloader): `0x7F`, `0x30/0x31/0xB0/0xB1`,
`0x40/0x41/0xC0/0xC1`, `0xAC`.

## Matriz de teclas

512 bytes = 128 posiciones × 4 bytes. Orden por columnas físicas, 6 filas por columna. La matriz por
defecto está en `l75ctl/l75_data.py`.

| Bytes | Acción |
|---|---|
| `0,0,hid,0` | tecla |
| `0,m,hid,hid2` | combinación (m suele ser modificador `0xE0`–`0xE7`) |
| `1,0,240..248,x` | ratón (240 izq, 241 der, 242 centro, 243 atrás, 244 adelante, 245 rueda±) |
| `3,0,lo,hi` | consumer/multimedia (p. ej. `3,0,205,0` play/pausa) |
| `9,modo,n,0` | macro n (modo 0 = N veces, 1 = on/off, 2 = mientras se mantiene) |
| `10,1,0,0` | Fn |
| `0,0,0,0` | desactivada |

## Macros (buffer de 256 bytes, máximo útil 248)

```
[rep_lo, rep_hi]  luego eventos:
[código, attr]          código 0x04–0xEF tecla, 0xF0–0xF8 ratón, 0xF9 mover (+dx, dy)
                        attr bit7 = pulsar; bits0–6 = retardo siguiente si ≤127 ms
[lo, hi]                retardo uint16 si no cupo en attr (0,0 si no hay retardo)
```
Se envía en páginas de 56 bytes (solo las que tienen datos).

## Luces: modos de teclas (cmd 0x07)

0 apagado, 1 fijo, 2 respiración, 3 neón, 4 ola (opción dir.: der/izq/abajo/arriba), 5 onda,
6 gotas, 7 serpiente (z/ida-vuelta), 8 reactivo, 9 convergencia, 10 senoidal, 11 caleidoscopio
(fuera/dentro), 12 línea (der/izq), 13 imagen de usuario (`[4]` = capa×16, RGB `0,200,200`),
14 láser, 15 círculo (antihorario/horario), 16 deslumbrante, 17 lluvia, 18 meteoro,
19 reactivo inverso, 20 música 1, 21 color de pantalla, 22 música 2.

Nibble bajo de `[4]`: `8` = arcoíris, `7` = color RGB, `0..6` = color predefinido (rojo, naranja,
amarillo, verde, cian, azul, morado). Para los modos de música es `0` = arcoíris y `4` = color.
El driver cambia el blanco `FFFFFF` por `FAFFFA`.

## Pantalla TFT (240×135, RGB565)

1. Cabecera `0xA5`:
   `[1]=cuadro actual (0) [2]=nº cuadros [3]=retardo ms [4,5,16,17]=bytes por cuadro (uint32 LE)
   [8..11]=left,top,right,bottom (low) [12..15]=(high)`.
   Leer: si `[1]==1` la pantalla está lista. Si no, reintentar hasta 10 veces cada 100 ms.
2. Por cada cuadro, paquetes `0x25`:
   `[1]=cuadro [2]=nº cuadros [3]=retardo [4..5]=nº paquete LE [6]=bytes válidos (≤56) [8..63]=datos`.
3. Datos: solo el rectángulo con píxeles no negros (unión de todos los cuadros). Se recorre por
   **columnas** (x por fuera, y por dentro) y cada píxel va en RGB565 **big-endian**.
4. Límite: 122 cuadros (8 MiB de flash / 64 KiB por cuadro − 5).

## Pendiente / no verificado

- Por cable USB aún no se ha probado en el teclado real. Por Bluetooth sí: lectura de info, luces,
  matriz, y escritura de luz confirmada leyendo de vuelta.
- Receptor 2.4 GHz (`3151:4011/4014/4017`): el driver usa un envoltorio "dongle_common" distinto. No implementado.
- `0x8F` devuelve el ID de modelo en `[1..2]` LE. Un L75 real devolvió 820, que en la tabla del driver también es "L75".
- La capa por defecto de Fn no se conoce. Por eso `keys set --fn ... default` no está permitido.

## Capa Fn: funciones del sistema

Leídas de un L75 real (firmware 1.17); los nombres salen del manual oficial. El driver oficial
no deja cambiar estas teclas: las pinta en rojo y avisa «tecla del sistema» (`系统按键无法修改`).
Lo mismo con la propia tecla Fn (`[10, 1, 0, 0]`). Regla del driver: en la capa Fn se bloquea
todo valor de tipo 2, 8, 10, 13, 14, 18 o 19 que no sea una función multimedia básica.

| Valor | Tecla (Fn +) | Función |
|---|---|---|
| `[10, 2, 0, 0]` | Esc | Restablecer el teclado |
| `[10, 3, 0, 0]` | Win | Bloquear la tecla Windows (sin confirmar) |
| `[10, 5, 2/1/0, 0]` | I / O / P | Distribución iOS / Mac / Windows |
| `[10, 8, 0, 0]` | = | Indicador de batería |
| `[10, 12, 0, 0]` | Del | Encender / apagar la luz |
| `[13, 1, 0, 0]` | Ins | Cambiar el efecto de luz |
| `[13, 2, 1/2, 0]` | ↑ / ↓ | Subir / bajar el brillo de la luz |
| `[13, 3, 1/2, 0]` | ← / → | Bajar / subir la velocidad de la luz |
| `[13, 5, 1, 0]` | Backspace | Cambiar el color de la luz (monocromo) |
| `[13, 8, 0, 0]` | PgUp | Modo de la tira lateral / apagarla (sin confirmar) |
| `[14, 0, 0/1/2, 0]` | Q / W / E | Bluetooth canal 1 / 2 / 3 (mantener: emparejar) |
| `[14, 0, 5, 0]` | R | Canal 2.4 GHz (sin confirmar) |
| `[19, 0, 0, 0]` | Ctrl, RCtrl | Pantalla: tu imagen o el estilo por defecto |
| `[19, 2, 0, 0]` | PgDn | Pantalla: otra vista (sin confirmar) |

Las demás teclas de la capa Fn (F1–F12, 4, ;) son acciones normales (multimedia y combinaciones)
y sí se pueden cambiar.
