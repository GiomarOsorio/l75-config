# Design brief: L75 Config

Document for **Claude Design**. It asks for a complete visual redesign of the **L75 Config** desktop app.
The result will be implemented in **Qt (PySide6) with QSS stylesheets**, on **Windows, macOS and Linux**.

> This brief was written in Spanish and sent to Claude Design. The deliverable is in
> [docs/design/](design/HANDOFF.md) and is already applied to the app (`l75ctl/ui/`).

Screenshots of the current app: [`docs/screenshots/`](screenshots/).

---

## 1. Product

- **What it is:** free configurator for the **ROYALAXE × ProtoArc L75** mechanical keyboard. It replaces
  the official driver, which only exists for Windows/Mac and barely works.
- **The keyboard:** 75 % layout (81 keys), per-key RGB, an RGB side light strip and a **240×135 px colour
  TFT screen** that shows the time, the battery or a user image/GIF. It has 3 profiles and connects by
  USB-C cable, Bluetooth or 2.4 GHz.
- **User:** mechanical-keyboard enthusiast and gamer. Wants to change the lighting, remap keys, create
  macros and put their own GIF on the screen. Not technical about protocols.
- **Interface language:** Spanish at the time of the brief (the app is now English and Spanish). Texts
  must be translatable, so avoid text baked into images.
- **Visual personality:** "premium but clean gamer hardware". Dark mode by default, subtle RGB accents and
  nothing cluttered. Tone references: Wootility, VIA/VIAL, Keychron Launcher, and **not** the overloaded
  style of Razer Synapse.

## 2. Technical constraints (important)

The design will be translated to **Qt Widgets + QSS**, not to the web. To be implementable:

- **Allowed:** solid colours and linear/radial gradients, borders and radii, padding, fonts (TTF/OTF can be
  bundled), SVG icons, `:hover`, `:pressed`, `:checked`, `:disabled` and `:focus` states, simple shadows
  (QGraphicsDropShadowEffect), hand-drawn widgets (the keyboard is already a custom QPainter canvas) and
  simple animations (opacity, colour, position).
- **Avoid or limit:** `backdrop-filter`/background blur, complex CSS grid, effects that depend on
  `::before`/`::after` pseudo-elements, advanced variable typography and more than 1–2 shadows per
  component.
- **Window size:** minimum **1000×640**, resizable. It must look good up to 1920×1080 and with 100–200 %
  HiDPI scaling.
- **Themes:** **dark (default) and light**, with the same tokens.
- **Cross-platform:** do not imitate any system's native controls. Own, consistent look on all three.

## 3. Structure and screens

### Top bar (global, always visible)
- **Connection status** with an icon:
  - "Connected by cable"
  - "Connected by Bluetooth" (warning: uploading images to the screen only works by cable)
  - "Demo mode (simulated keyboard)"
  - "Keyboard not found" (with "Retry" and "Try demo mode" actions)
- **Profile selector:** 1 / 2 / 3. Changing it reloads the data.
- **Battery:** percentage and whether it is charging.
- **Activity indicator:** "Reading keys…", "Applying lighting…", with progress when there is some.

### Navigation
Six sections. Today they are tabs; the design may propose a **sidebar with icons**.
Recommended: icon, name and the active section highlighted.

### 3.1 Keys (remapping)
- **Central element:** drawing of the L75 keyboard with its real layout. The coordinates of the 81 keys are
  in `l75ctl/l75_data.py` (`LAYOUT`): name, x, y, width and height in driver units. The **1u key is
  25×26**; the others vary (Space 207, Backspace 59, etc.).
- **Key states:** normal · hover · selected · **remapped** (shows the original name small and the new
  action large, highlighted) · disabled.
- **Layer selector:** "Normal" / "Fn (Fn + key)".
- **Edit panel for the selected key:** key name, current action, action type and controls for that type,
  plus **Apply** and **Restore this key** buttons.
  - Types: Key · Combination (up to 3 keys) · Media/function (list: play/pause, volume, calculator, lock
    session…) · Mouse (left click, right click, wheel…) · Macro (no. 0–49 and mode: repeat N times / while
    held / on-off) · Disabled · Default value.
- **Global actions:** "Read from keyboard" and "Restore all" (with confirmation).

### 3.2 Lighting
Two blocks: **Key lighting** and **Side strip**. Each has:
- **Mode:** 23 for the keys (Off, Static, Breathing, Neon, Wave, Ripple, Raindrops, Snake, Reactive,
  Converge, Sine wave, Kaleidoscope, Line, User picture, Laser, Circle, Dazzling, Rain, Meteor, Reverse
  reactive, Music 1, Screen colour, Music 2) and 6 for the side strip. Propose **cards or a grid with an
  animated mini preview** instead of a drop-down.
- **Brightness:** 0–4. **Speed:** 0–4 (only in some modes). **Colour:** RGB picker plus quick swatches.
  **Rainbow:** switch. **Option:** direction/variant (left, right, up, down, clockwise…), only in some modes.
- Controls that do not apply to the chosen mode are **hidden or disabled**.
- "Read" and "Apply" buttons. Consider whether to apply live while moving the controls.

### 3.3 Per-key colours
- The same keyboard drawing, now as a **painting canvas**. Each key shows its real colour.
- Tools: brush colour, quick palette, "Paint all", "Read colours" and "Turn on user picture mode".
- Each click is sent to the keyboard instantly.

### 3.4 Macros
- List of **50 slots** (0–49) showing empty or used.
- Editor for the selected macro. Today it is text (`down:ctrl, tap:c, up:ctrl, delay:50`); propose a
  **visual sequence editor**: a row of events "press X", "release X", "wait N ms" and "mouse click",
  reorderable, with a "+ event" button and a "record" mode (capture real keys).
- **Repeats:** number.
- **Capacity indicator:** "N / 248 bytes", with a warning if it goes over.
- Buttons: Read from keyboard · Delete · Save to keyboard.
- Visible hint: "Assign it to a key in the Keys section".

### 3.5 Screen (240×135 LCD)
- **Preview** at 2× (480×270) that looks like a "physical screen": black bezel and rounded corners. Plays
  the GIF in a loop.
- Controls: Choose image or GIF (also drag and drop) · Fit (Fit with bars, Fill by cropping, Stretch) ·
  Delay between frames (20–255 ms).
- Information: number of frames (max. 122), area used and estimated upload time.
- **Upload:** long progress bar (it can take 1–5 min) with the current frame and a Cancel button.
- **Over Bluetooth** the upload is blocked: show a disabled state with an explanation.
- "Sync date and time" works by cable and by Bluetooth.
- Visible note: on the keyboard, **Fn + Ctrl** switches between your image and the default screen.

### 3.6 Settings
- **Performance:** polling rate (125/250/500/1000 Hz), debounce (0–50 ms).
- **Sleep (wireless mode):** minutes until sleep (0 = never) and until deep sleep.
- **Options:** lock Windows key · Mac mode · swap WASD and arrows.
- **Information:** firmware, model ID and connection type.
- **Danger zone:** "Factory reset", with strong confirmation.

## 4. States to design

- No keyboard, searching, connected by cable, connected by Bluetooth and demo mode.
- Operation in progress: non-blocking indicator and long progress for the image upload.
- Error, for example "the keyboard did not answer" or "missing permission (udev rule on Linux)", with a
  suggested action.
- Short success (toast/snackbar): "Caps Lock → Esc", "Macro 3 saved".
- Disabled elements with their reason (tooltip or text).

## 5. Deliverables we ask Claude Design for

1. **Design-system tokens**, in dark and light theme:
   - colours: background, surfaces 1–3, border, primary/secondary/disabled text, accent, accent-hover,
     success, warning, error;
   - typography: family, sizes and weights;
   - spacing (scale), radii and shadows.
2. **Components with all their states:** primary/secondary/danger/ghost button, toggle, 0–4 slider with
   ticks, colour picker, drop-down, number field, lighting-mode card, profile chip, sidebar, toast, progress
   bar, confirmation dialog and **keyboard key** (normal/hover/selected/remapped/painted/disabled).
3. **Screens** at 1280×800: the six sections of §3 with realistic data, plus the §4 states for the top bar.
4. **Iconography:** a coherent set (SVG, uniform stroke) for navigation and actions.
5. Format: navigable HTML prototype **plus** a list of tokens as text (JSON or table). With that I
   translate them to QSS.

## 6. Useful data

- L75 key names: `Esc, F1–F12, \`, 1–0, -, =, Backspace, Ins, Tab, Q…P, [, ], \\, Del, CapsLock, A…L, ;, ',
  Enter, PgUp, Shift, Z…M, ,, ., /, RShift, PgDn, Ctrl, Win, Alt, Space, RAlt, Fn, RCtrl, ↑, ←, ↓, →`.
- Keyboard screen: 240×135 px, RGB565.
- Profiles: 3. Macros: 50. Fn layer: 1.
- Typical values read from a real L75: firmware 1.17, "Rain" lighting brightness 4 speed 4 colour green,
  side strip "Wave" rainbow, 1000 Hz polling rate, 1 ms debounce.
