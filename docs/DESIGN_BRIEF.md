# Brief de diseño: L75 Config

Documento para **Claude Design**. Pide un rediseño visual completo de la app de escritorio
**L75 Config**. El resultado se implementará en **Qt (PySide6) con hojas de estilo QSS**, en
**Windows, macOS y Linux**.

Capturas de la versión actual (funcional, sin diseño): [`docs/screenshots/`](screenshots/).

---

## 1. Producto

- **Qué es:** configurador libre del teclado mecánico **ROYALAXE × ProtoArc L75**. Sustituye el driver
  oficial, que solo existe para Windows/Mac y apenas funciona.
- **El teclado:** formato 75 % (81 teclas), RGB por tecla, tira de luz lateral RGB y una **pantalla TFT
  a color de 240×135 px** que muestra hora, batería o una imagen/GIF del usuario. Tiene 3 perfiles y
  se conecta por cable USB-C, Bluetooth o 2.4 GHz.
- **Usuario:** entusiasta de teclados mecánicos y gamer. Quiere cambiar luces, reasignar teclas, crear
  macros y poner su propio GIF en la pantalla. No es técnico en protocolos.
- **Idioma de la interfaz:** español. Los textos deben poder traducirse después, así que conviene
  evitar texto incrustado en imágenes.
- **Personalidad visual buscada:** "hardware gamer premium pero limpio". Modo oscuro por defecto,
  acentos RGB sutiles y nada recargado. Referencias de tono: Wootility, VIA/VIAL, Keychron Launcher,
  y **no** el estilo sobrecargado de Razer Synapse.

## 2. Restricciones técnicas (importante)

El diseño se traducirá a **Qt Widgets + QSS**, no a la web. Para que sea implementable:

- **Se puede:** colores sólidos y degradados lineales/radiales, bordes y radios, padding, fuentes
  (se pueden empaquetar TTF/OTF), iconos SVG, estados `:hover`, `:pressed`, `:checked`,
  `:disabled` y `:focus`, sombras sencillas (QGraphicsDropShadowEffect), widgets dibujados a mano
  (el teclado ya es un canvas propio con QPainter) y animaciones simples (opacidad, color, posición).
- **Evitar o limitar:** `backdrop-filter`/blur de fondo, CSS grid complejo, efectos que dependan de
  pseudo-elementos `::before`/`::after`, tipografía variable avanzada y más de 1–2 sombras por
  componente.
- **Tamaño de ventana:** mínimo **1000×640**, redimensionable. Debe verse bien hasta 1920×1080 y con
  escalado HiDPI de 100–200 %.
- **Temas:** **oscuro (por defecto) y claro**, con los mismos tokens.
- **Multiplataforma:** no imitar los controles nativos de ningún sistema. Look propio y consistente
  en los tres.

## 3. Estructura y pantallas

### Barra superior (global, siempre visible)
- **Estado de conexión** con icono:
  - "Conectado por cable"
  - "Conectado por Bluetooth" (aviso: subir imágenes a la pantalla solo funciona por cable)
  - "Modo demo (teclado simulado)"
  - "Teclado no encontrado" (con acción "Reintentar" y "Probar en modo demo")
- **Selector de perfil:** 1 / 2 / 3. Al cambiarlo se recargan los datos.
- **Batería:** porcentaje y si está cargando.
- **Indicador de actividad:** "Leyendo teclas…", "Aplicando luz…", con progreso cuando lo hay.

### Navegación
Seis secciones. Hoy son pestañas; el diseño puede proponer **barra lateral con iconos**.
Recomendado: icono, nombre y la sección activa resaltada.

### 3.1 Teclas (reasignación)
- **Elemento central:** dibujo del teclado L75 con su disposición real. Las coordenadas de las 81
  teclas están en `l75ctl/l75_data.py` (`LAYOUT`): nombre, x, y, ancho y alto en unidades del
  driver. La **tecla unitaria mide 25×26**; las demás varían (Espacio 207, Backspace 59, etc.).
- **Estados de cada tecla:** normal · hover · seleccionada · **reasignada** (muestra el nombre
  original pequeño y la nueva acción grande, resaltada) · desactivada.
- **Selector de capa:** "Normal" / "Fn (Fn + tecla)".
- **Panel de edición de la tecla seleccionada:** nombre de la tecla, acción actual, tipo de acción y
  controles según el tipo, más los botones **Aplicar** y **Restaurar esta tecla**.
  - Tipos: Tecla · Combinación (hasta 3 teclas) · Multimedia/función (lista: reproducir/pausa,
    volumen, calculadora, bloquear sesión…) · Ratón (clic izquierdo, derecho, rueda…) · Macro (n.º
    0–49 y modo: repetir N veces / mientras se mantiene / on-off) · Desactivada · Valor por defecto.
- **Acciones globales:** "Leer del teclado" y "Restaurar todas" (con confirmación).

### 3.2 Iluminación
Dos bloques: **Luz de teclas** y **Tira lateral**. Cada uno tiene:
- **Modo:** 23 en teclas (Apagado, Fijo, Respiración, Neón, Ola, Onda expansiva, Gotas de lluvia,
  Serpiente, Reactivo, Convergencia, Onda senoidal, Caleidoscopio, Línea, Imagen de usuario,
  Láser, Círculo, Deslumbrante, Lluvia, Meteoro, Reactivo inverso, Música 1, Color de pantalla,
  Música 2) y 6 en la tira lateral. Proponer **tarjetas o cuadrícula con mini-previsualización
  animada** en lugar de un desplegable.
- **Brillo:** 0–4. **Velocidad:** 0–4 (solo en algunos modos). **Color:** selector RGB más
  muestras rápidas. **Arcoíris:** interruptor. **Opción:** dirección/variante (izquierda, derecha,
  arriba, abajo, horario…), solo en algunos modos.
- Los controles que no aplican al modo elegido se **ocultan o desactivan**.
- Botones "Leer" y "Aplicar". Valorad si conviene aplicar en vivo al mover los controles.

### 3.3 Colores por tecla
- El mismo teclado dibujado, ahora como **lienzo para pintar**. Cada tecla muestra su color real.
- Herramientas: color del pincel, paleta rápida, "Pintar todas", "Leer colores" y "Activar modo
  imagen de usuario".
- Cada clic se envía al teclado al instante.

### 3.4 Macros
- Lista de **50 posiciones** (0–49) con indicación de vacía o usada.
- Editor de la macro seleccionada. Hoy es texto (`down:ctrl, tap:c, up:ctrl, delay:50`); proponer un
  **editor visual de secuencia**: fila de eventos "pulsar X", "soltar X", "esperar N ms" y "clic
  ratón", reordenables, con botón "+ evento" y un modo "grabar" (capturar teclas reales).
- **Repeticiones:** número.
- **Indicador de capacidad:** "N / 248 bytes", con aviso si se pasa.
- Botones: Leer del teclado · Borrar · Guardar en el teclado.
- Pista visible: "Asígnala a una tecla en la sección Teclas".

### 3.5 Pantalla (LCD 240×135)
- **Previsualización** a 2× (480×270) con aspecto de "pantalla física": marco negro y esquinas
  redondeadas. Reproduce el GIF en bucle.
- Controles: Elegir imagen o GIF (también arrastrar y soltar) · Ajuste (Ajustar con bandas, Rellenar
  recortando, Estirar) · Retardo entre cuadros (20–255 ms).
- Información: n.º de cuadros (máx. 122), área usada y tiempo estimado de subida.
- **Subida:** barra de progreso larga (puede tardar 1–5 min) con cuadro actual y botón Cancelar.
- **Por Bluetooth** la subida está bloqueada: mostrar un estado deshabilitado con explicación.
- "Sincronizar fecha y hora" funciona por cable y por Bluetooth.
- Nota visible: en el teclado, **Fn + Ctrl** alterna entre tu imagen y la pantalla por defecto.

### 3.6 Ajustes
- **Rendimiento:** tasa de sondeo (125/250/500/1000 Hz), debounce (0–50 ms).
- **Reposo (modo inalámbrico):** minutos hasta reposo (0 = nunca) y hasta reposo profundo.
- **Opciones:** bloquear tecla Windows · modo Mac · intercambiar WASD y flechas.
- **Información:** firmware, ID de modelo y tipo de conexión.
- **Zona peligrosa:** "Restaurar de fábrica", con confirmación fuerte.

## 4. Estados que hay que diseñar

- Sin teclado, buscando, conectado por cable, conectado por Bluetooth y modo demo.
- Operación en curso: indicador no bloqueante y progreso largo en la subida de imagen.
- Error, por ejemplo "el teclado no respondió" o "falta permiso (regla udev en Linux)", con acción
  sugerida.
- Éxito breve (toast/snackbar): "Caps Lock → Esc", "Macro 3 guardada".
- Elementos deshabilitados con su motivo (tooltip o texto).

## 5. Entregables que pedimos a Claude Design

1. **Tokens del sistema de diseño**, en tema oscuro y claro:
   - colores: fondo, superficies 1–3, borde, texto primario/secundario/deshabilitado, acento,
     acento-hover, éxito, aviso, error;
   - tipografía: familia, tamaños y pesos;
   - espaciado (escala), radios y sombras.
2. **Componentes con todos sus estados:** botón primario/secundario/peligro/fantasma, toggle,
   slider 0–4 con marcas, selector de color, desplegable, campo numérico, tarjeta de modo de luz,
   chip de perfil, barra lateral, toast, barra de progreso, diálogo de confirmación y **tecla del
   teclado** (normal/hover/seleccionada/reasignada/pintada/deshabilitada).
3. **Pantallas** a 1280×800: las seis secciones de la §3 con datos realistas, más los estados de la
   §4 para la barra superior.
4. **Iconografía:** un set coherente (SVG, trazo uniforme) para navegación y acciones.
5. Formato: prototipo HTML navegable **más** una lista de tokens en texto (JSON o tabla). Con eso los
   traduzco a QSS.

## 6. Datos útiles

- Nombres de las teclas del L75: `Esc, F1–F12, \`, 1–0, -, =, Backspace, Ins, Tab, Q…P, [, ], \\,
  Del, CapsLock, A…L, ;, ', Enter, PgUp, Shift, Z…M, ,, ., /, RShift, PgDn, Ctrl, Win, Alt, Space,
  RAlt, Fn, RCtrl, ↑, ←, ↓, →`.
- Pantalla del teclado: 240×135 px, RGB565.
- Perfiles: 3. Macros: 50. Capa Fn: 1.
- Valores típicos leídos de un L75 real: firmware 1.17, luz "Lluvia" brillo 4 velocidad 4 color
  verde, tira lateral "Ola" arcoíris, tasa 1000 Hz, debounce 1 ms.
