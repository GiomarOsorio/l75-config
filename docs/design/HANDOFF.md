# Diseño de L75 Config: guía para implementarlo en Qt

Rediseño completo hecho en Claude Design (lienzo «Rediseño L75 Config»), a partir de `docs/DESIGN_BRIEF.md`.
Esta carpeta trae todo lo necesario para implementarlo en PySide6 + QSS sin abrir el lienzo.

## Qué hay aquí

| Carpeta | Contenido | Uso |
|---|---|---|
| `capturas/` | PNG de cada tablero, a 1280 px de ancho | **Míralas primero.** Son la referencia visual. |
| `tokens/l75-tokens.json` | Colores de los dos temas, tipografía, espaciado, radios, medidas, movimiento y sombras | Generar la QSS |
| `iconos/` | 81 SVG (24 × 24, trazo 1,75) y `alias.json` | Iconos de navegación y acciones |
| `lienzo/` | Código fuente del lienzo: `l75.css` y un `.dc.html` por tablero | Valores exactos: medidas, textos y estados |

Los `.dc.html` no se abren en un navegador normal, porque necesitan el runtime de Claude Design. Léelos como especificación:

- El marcado dentro de `<x-dc>` da la estructura, los textos y las medidas.
- `l75.css` tiene todos los estilos. Cada clase equivale a un selector QSS (tabla de componentes, más abajo).
- El `<script>` de cada tablero es la lógica del **prototipo**, con datos simulados y retardos falsos. Sirve para entender el comportamiento; no hay que copiarlo.

Las capturas se generaron con Inter. La letra monoespaciada que se ve en ellas es la de respaldo: en la app va JetBrains Mono.

## Capturas

### Pantallas (1280 × 800; el tema oscuro es el de por defecto)

| Sección | Captura | Fuente |
|---|---|---|
| Teclas | `capturas/pantallas/1-teclas.png` | `lienzo/Main.dc.html` |
| Iluminación | `capturas/pantallas/2-iluminacion.png` | `lienzo/Iluminacion.dc.html` |
| Colores por tecla | `capturas/pantallas/3-colores-por-tecla.png` | `lienzo/Colores.dc.html` |
| Macros | `capturas/pantallas/4-macros.png` | `lienzo/Macros.dc.html` |
| Pantalla (LCD) | `capturas/pantallas/5-pantalla.png` | `lienzo/Pantalla.dc.html` |
| Ajustes | `capturas/pantallas/6-ajustes.png` | `lienzo/Ajustes.dc.html` |

`capturas/claro/` tiene las mismas seis pantallas en tema claro, con los mismos tokens.

### Estados

| Estado | Captura |
|---|---|
| Barra superior: conexión (cable, Bluetooth, demo, buscando, sin teclado), actividad, toasts y deshabilitados con motivo | `capturas/estados/barra-superior.png` |
| Teclado no encontrado | `capturas/estados/sin-teclado.png` |
| Buscando teclado | `capturas/estados/buscando.png` |
| Falta permiso en Linux (regla udev) | `capturas/estados/permiso-udev.png` |
| Subida de imagen en curso | `capturas/estados/pantalla-subiendo.png` |
| Pantalla por Bluetooth (subida bloqueada) | `capturas/estados/pantalla-bluetooth.png` |
| Confirmar «Restaurar todas» y toast | `capturas/estados/teclas-restaurar-todas.png` |
| Restaurar de fábrica (confirmación fuerte) | `capturas/estados/ajustes-restaurar-fabrica.png` |
| Error: el teclado no respondió | `capturas/estados/iluminacion-error.png` |

### Sistema de diseño

| Tablero | Captura |
|---|---|
| Tokens, oscuro y claro | `capturas/sistema/tokens.png` |
| Componentes y todos sus estados | `capturas/sistema/componentes-oscuro.png`, `capturas/sistema/componentes-claro.png` |
| Iconos | `capturas/sistema/iconos.png` |
| Teclado completo (lienzo) | `capturas/sistema/teclado.png` |
| Tecla: estados y medidas | `capturas/sistema/tecla-estados-y-medidas.png` |
| Selector de color | `capturas/sistema/selector-de-color.png` |
| Barra lateral y barra superior | `capturas/sistema/barra-lateral.png`, `capturas/sistema/barra-superior.png` |

## Cómo pasarlo a Qt

### 1. Tema: de tokens a QSS

- Carga `tokens/l75-tokens.json` y elige `colores.oscuro` o `colores.claro`. Los dos temas tienen los mismos nombres.
- Escribe una sola plantilla QSS con marcadores (por ejemplo `${accent}`) y rellénala con `string.Template` usando el campo `qss` de cada color. Aplícala con `app.setStyleSheet(...)`. Para cambiar de tema, vuelve a rellenarla y aplicarla.
- En QSS el alfa de `rgba()` va de 0 a 255; el campo `qss` ya viene así. Si usas hexadecimal de 8 dígitos, `QColor` espera `#AARRGGBB`, con el alfa delante.
- Fuentes: empaqueta Inter (400, 500, 600 y 700) y JetBrains Mono (400, 500 y 600), las dos con licencia OFL, como TTF estáticos. Regístralas con `QFontDatabase.addApplicationFont`. El texto base es de 13 px.
- Sombras: `QGraphicsDropShadowEffect` con `offsetX`, `offsetY`, `blurRadius` y `color` de `sombras.*`. Se usa una por widget; el anillo de foco va como borde, no como sombra.
- El diseño no usa desenfoque ni pseudo-elementos decorativos, como pedía el brief.

### 2. Componentes y widgets

Debajo de cada componente, el tablero de componentes indica el widget de Qt y el selector QSS que le corresponde:

| Componente | Qt / QSS |
|---|---|
| Botón primario, secundario, peligro y fantasma | `QPushButton[variant="primary\|secondary\|danger\|ghost"]` con `:hover`, `:pressed`, `:focus` y `:disabled` |
| Interruptor | `QCheckBox[role="switch"]::indicator`, con un SVG por estado |
| Slider 0–4 con marcas | `QSlider::groove`, `::sub-page` y `::handle`, más las marcas pintadas |
| Desplegable | `QComboBox`, `::drop-down` y `QAbstractItemView` |
| Campo numérico | `QSpinBox` (`::down-button { subcontrol-position: left }`) y `QLineEdit` |
| Selector de color | Botón y un `QWidget` emergente pintado con `QLinearGradient` |
| Control segmentado y chip de perfil | `QButtonGroup` exclusivo con `QToolButton:checked` |
| Tarjeta de modo de luz | `QToolButton` activable, con vista previa pintada con `QPainter` a 30 fps |
| Barra lateral | `QToolButton` activables en un `QVBoxLayout`; se compacta a 72 px por debajo de 1100 px de ancho |
| Toast | `QWidget` sin marco, `shadow-2` y `QPropertyAnimation` de opacidad y posición |
| Barra de progreso | `QProgressBar::chunk`; la de subida de imagen pinta el degradado RGB |
| Diálogo | `QDialog` sin marco, velo `scrim` sin desenfoque y `shadow-2` |
| Tecla del teclado | Lienzo propio con `QPainter` (sección 3) |
| Estado o aviso | `QLabel` con una propiedad de estado y `QToolTip` |

- En `l75.css`, las clases `.is-hover`, `.is-active`, `.is-focus` e `.is-disabled` solo fuerzan estados para dibujarlos en la hoja de componentes. En QSS son `:hover`, `:pressed`, `:focus` y `:disabled`.
- Las variantes van como propiedad dinámica: `boton.setProperty("variant", "primary")` aplica `QPushButton[variant="primary"]`. Si cambias la propiedad después de mostrar el widget, llama a `style().unpolish(w)` y `style().polish(w)`.

### 3. Teclado (lienzo propio)

- La app ya tiene un `KeyboardWidget` con `QPainter`: mantenlo y cambia cómo pinta. Las coordenadas salen de `l75ctl/l75_data.py` (`LAYOUT`).
- Los estados y las medidas de la tecla están en `capturas/sistema/tecla-estados-y-medidas.png` y `lienzo/Tecla.dc.html`:
  - normal y hover;
  - seleccionada: anillo de 2 px y halo de 4 px;
  - reasignada: nombre original pequeño arriba y acción nueva grande, en color de acento;
  - pintada: la cara es el color de la tecla y la falda, ese color oscurecido un 45 %;
  - desactivada: trama a 135° (`Qt::BDiagPattern`);
  - capa Fn: compara con la captura de Teclas.
- Los colores del teclado (`key-*`, `deck*`, `lcd-*`, `preview-*`) están en los tokens de cada tema.

### 4. Estructura de la ventana

- Barra lateral de 232 px, barra superior de 56 px y el contenido en un `QStackedWidget`. El contenido lleva 20 px de margen arriba y 28 px a los lados. La ventana mínima es de 1000 × 640.
- **Barra superior:** a la izquierda, el estado de la conexión y la actividad en curso, que no bloquea la ventana. A la derecha, el perfil (1, 2 o 3) y la batería. El texto de actividad puede salir del `label` que ya recibe `MainWindow.run(...)`; si hay progreso, se muestra una barra fina con el porcentaje.
- **Toasts:** abajo, centrados en el área de contenido. Los de éxito e información se cierran solos a los 3 s; los de error esperan a que el usuario los cierre. Sustituyen a `statusBar().showMessage`.
- **Diálogos:** sustituyen a los `QMessageBox`.
- **Deshabilitado, siempre con motivo:** el motivo va en un tooltip y, si cabe, en una línea de texto debajo del control.

### 5. Comportamiento de cada sección

- **Teclas:** capas «Normal» y «Fn + tecla». El panel de la tecla seleccionada muestra la acción actual y el tipo de acción (Tecla, Combinación, Multimedia, Ratón, Macro, Desactivada o Por defecto), con los botones «Aplicar» y «Restaurar esta tecla». «Restaurar todas» pide confirmación.
- **Iluminación:** pestañas «Luz de teclas» y «Tira lateral». Cada modo es una tarjeta con vista previa; solo se animan la seleccionada y la que tiene el ratón encima. Brillo y velocidad van de 0 a 4 con marcas. El color se elige con muestras y tiene interruptor de arcoíris. La opción de dirección o variante solo aparece en los modos que la tienen. Hay un interruptor «Aplicar en vivo». Los controles que no aplican a un modo se desactivan con su motivo.
- **Colores por tecla:** cada clic se envía al instante. Si la luz actual no es «Imagen de usuario», aparece un aviso con un botón para activarla. Hay pincel, cuentagotas, «Pintar todas» y «Deshacer»; el negro deja la tecla apagada.
- **Macros:**
  - Lista de las 50 posiciones.
  - Editor visual con eventos reordenables: pulsar, soltar, esperar y clic de ratón.
  - Vista «Texto» con la sintaxis actual (`down:ctrl, tap:c, …`).
  - Grabación, repeticiones y capacidad usada sobre 248 bytes.
  - Botones «Leer del teclado», «Borrar» y «Guardar en el teclado», y un enlace a Teclas.
- **Pantalla:**
  - Vista previa a 2× con marco de pantalla física.
  - Controles: ajuste (con bandas, recortando o estirando), retardo entre cuadros de 20 a 255 ms e interruptor «Píxeles reales (RGB565)».
  - Información: cuadros (máximo 122), área usada y tiempo estimado de subida.
  - La subida muestra una barra larga con el cuadro actual y un botón «Cancelar». Por Bluetooth la subida está bloqueada, con la explicación.
  - «Sincronizar fecha y hora» funciona por cable y por Bluetooth. Lleva la nota de Fn + Ctrl.
- **Ajustes:**
  - Tasa de sondeo y debounce.
  - Reposo (0 = nunca) y reposo profundo, que solo cuentan en modo inalámbrico.
  - Opciones e información del teclado.
  - Zona peligrosa con confirmación fuerte: hay que escribir RESTAURAR.
- **Sin teclado, buscando, permiso udev y demo:** pantalla vacía con «Reintentar» y «Probar en modo demo». El aviso de udev trae los mismos comandos que `install.sh`.

### 6. Iconos

- Los SVG usan `currentColor`. Al cargarlos en Qt, sustituye `currentColor` por el color del token y crea el `QIcon` a partir de ese SVG. Por ejemplo, `text-2` en reposo y `accent` en la sección activa.
- Se usan a 16, 20 y 24 px.
- `alias.json` lista los nombres alternativos que usa el lienzo.

## Orden sugerido

1. Tema y fuentes: tokens a QSS y cambio entre oscuro y claro.
2. Estructura: barra lateral, barra superior, toasts y diálogos.
3. Componentes base.
4. Teclado con todos sus estados.
5. Las seis secciones, una a una, comparando cada pantalla con su captura.
6. Estados: conexión, errores, progreso y deshabilitados con motivo.
