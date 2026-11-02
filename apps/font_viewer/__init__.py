badge.mode(HIRES | VSYNC)

screen.antialias = image.X2

APP_STATE = "font_viewer"
MIN_FONT_SIZE = 8
MAX_FONT_SIZE = 48
DEFAULT_FONT_SIZE = 24
SAMPLE_TEXT = "Aa Bb 123"

FONT_DEFINITIONS = (
    ("DynaPuff Medium", "/system/assets/fonts/DynaPuff-Medium.af"),
    ("IndieFlower Regular", "/system/assets/fonts/IndieFlower-Regular.af"),
    ("MonaSans Medium", "/system/assets/fonts/MonaSans-Medium.af"),
)

UI_FONT = font.sins


def normalise_size(value):
    try:
        return max(MIN_FONT_SIZE, min(MAX_FONT_SIZE, int(value)))
    except (TypeError, ValueError):
        return DEFAULT_FONT_SIZE


state = {"sizes": [DEFAULT_FONT_SIZE] * len(FONT_DEFINITIONS)}
State.load(APP_STATE, state)

saved_sizes = state.get("sizes", [])
if not isinstance(saved_sizes, list) or len(saved_sizes) != len(FONT_DEFINITIONS):
    saved_sizes = [DEFAULT_FONT_SIZE] * len(FONT_DEFINITIONS)

font_sizes = [normalise_size(value) for value in saved_sizes]
fonts = []
for display_name, font_path in FONT_DEFINITIONS:
    fonts.append({
        "name": display_name,
        "face": font.load(font_path),
    })

selected_font = 0

header_panel = shape.rounded_rectangle(8, 8, screen.width - 16, 38, 10)
preview_shadow = shape.rounded_rectangle(16, 78, screen.width - 24, 116, 15)
preview_panel = shape.rounded_rectangle(12, 74, screen.width - 24, 116, 15)
size_panel = shape.rounded_rectangle(94, 197, 132, 24, 12)


def draw_pixel_text(message, x, y, pen):
    screen.font = UI_FONT
    screen.pen = pen
    screen.text(message, x, y)


def draw_centered_pixel_text(message, y, pen):
    screen.font = UI_FONT
    width, _ = screen.measure_text(message)
    draw_pixel_text(message, (screen.width - width) / 2, y, pen)


def draw_font_indicators():
    spacing = 14
    start_x = (screen.width / 2) - (((len(fonts) - 1) * spacing) / 2)
    for index in range(len(fonts)):
        if index == selected_font:
            screen.pen = color.rgb(76, 201, 240)
            radius = 4
        else:
            screen.pen = color.rgb(115, 128, 150)
            radius = 2
        screen.circle(start_x + (index * spacing), 39, radius)


def draw_preview():
    current = fonts[selected_font]
    current_size = font_sizes[selected_font]

    screen.pen = color.rgb(8, 15, 28, 90)
    screen.shape(preview_shadow)
    screen.pen = color.rgb(250, 251, 253)
    screen.shape(preview_panel)

    screen.font = current["face"]
    sample_width, sample_height = screen.measure_text(SAMPLE_TEXT, current_size)
    sample_x = (screen.width - sample_width) / 2
    sample_y = 74 + ((116 - sample_height) / 2)
    screen.pen = color.rgb(20, 35, 58)
    screen.text(SAMPLE_TEXT, sample_x, sample_y, current_size)


def change_size(delta):
    new_size = normalise_size(font_sizes[selected_font] + delta)
    if new_size == font_sizes[selected_font]:
        return

    font_sizes[selected_font] = new_size
    state["sizes"] = font_sizes
    State.save(APP_STATE, state)


def init():
    state["sizes"] = font_sizes


def update():
    global selected_font

    if badge.pressed(BUTTON_UP):
        selected_font = (selected_font - 1) % len(fonts)

    if badge.pressed(BUTTON_DOWN):
        selected_font = (selected_font + 1) % len(fonts)

    if badge.pressed(BUTTON_A):
        change_size(-1)

    if badge.pressed(BUTTON_C):
        change_size(1)

    screen.pen = color.rgb(20, 35, 58)
    screen.clear()

    screen.pen = color.rgb(31, 53, 82)
    screen.shape(header_panel)
    draw_pixel_text("VECTOR FONT VIEWER", 20, 18, color.rgb(245, 247, 250))
    draw_pixel_text(
        "{}/{}".format(selected_font + 1, len(fonts)),
        screen.width - 39,
        18,
        color.rgb(185, 198, 218),
    )
    draw_font_indicators()

    draw_centered_pixel_text(fonts[selected_font]["name"], 57, color.rgb(210, 220, 235))
    draw_preview()

    screen.pen = color.rgb(247, 37, 133)
    screen.shape(size_panel)
    draw_centered_pixel_text(
        "SIZE: {} px".format(font_sizes[selected_font]),
        204,
        color.rgb(255, 255, 255),
    )

    draw_pixel_text("A  -", 18, 228, color.rgb(210, 220, 235))
    draw_centered_pixel_text("UP/DOWN: FONT", 228, color.rgb(150, 165, 188))
    draw_pixel_text("+  C", screen.width - 42, 228, color.rgb(210, 220, 235))


def on_exit():
    pass


init()
run(update)
