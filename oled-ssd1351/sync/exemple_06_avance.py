"""
exemple_06_avance.py — SSD1351 RGB OLED 1.5" (128x128)
Exemple 6 : Fonctions avancees — arc, secteur, polygone,
            defilement texte, sinusoide, scrolling materiel
"""
import time, math
from ssd1351 import (SSD1351, color565, hsv_to_rgb565,
                     BLACK, WHITE, RED, GREEN, BLUE,
                     YELLOW, CYAN, MAGENTA, ORANGE, GRAY)

oled = SSD1351()
W, H = oled.width, oled.height

# 1 : Arcs et secteurs (jauge circulaire)
def draw_gauge(cx, cy, r, pct, label, value_str, c_fg, c_bg=GRAY):
    oled.fill_circle(cx, cy, r, color565(20,20,20))
    oled.draw_circle(cx, cy, r, c_bg)
    # Arc fond (gris)
    oled.draw_arc(cx, cy, r-4, 135, 405, c_bg, step=2)
    # Arc valeur (couleur)
    end_angle = 135 + pct * 2.7
    oled.draw_arc(cx, cy, r-4, 135, end_angle, c_fg, step=1)
    # Arc plus epais
    oled.draw_arc(cx, cy, r-5, 135, end_angle, c_fg, step=1)
    oled.draw_arc(cx, cy, r-6, 135, end_angle, c_fg, step=1)
    # Valeur centre
    oled.fill_circle(cx, cy, r-12, color565(15,15,15))
    oled.text(value_str[:4], cx-16, cy-4, c_fg)
    oled.text(label[:4], cx-16, cy+8, GRAY)

oled.fill(BLACK)
draw_gauge(32,  38, 30, 72, "TEMP", "72.0", RED)
draw_gauge(96,  38, 30, 45, "HUM ", "45.0", CYAN)
draw_gauge(32,  96, 30, 88, "BAT ", "88.0", GREEN)
draw_gauge(96,  96, 30, 33, "CPU ", "33.0", YELLOW)
oled.show(); time.sleep(3)

# 2 : Secteurs (camembert)
oled.fill(BLACK)
oled.text("Camembert       ", 0, 0, WHITE)
sectors = [
    (25, RED,    "25%"),
    (40, GREEN,  "40%"),
    (20, BLUE,   "20%"),
    (15, YELLOW, "15%"),
]
cx, cy, r = 64, 72, 50
start = -90
for pct, col, label in sectors:
    end = start + pct * 3.6
    oled.fill_arc(cx, cy, r, start, end, col)
    start = end
oled.fill_circle(cx, cy, 20, color565(20,20,20))  # trou central
oled.draw_circle(cx, cy, r, WHITE)
oled.show(); time.sleep(3)

# 3 : Polygones
oled.fill(BLACK)
oled.text("Polygones       ", 0, 0, WHITE)
# Hexagone
pts_hex = [(int(64 + 40*math.cos(math.radians(60*i-30))),
            int(38 + 40*math.sin(math.radians(60*i-30)))) for i in range(6)]
oled.draw_polygon(pts_hex, CYAN)
# Etoile 5 branches
pts_star = []
for i in range(10):
    r_s = 40 if i%2==0 else 18
    a_s = math.radians(36*i - 90)
    pts_star.append((int(64 + r_s*math.cos(a_s)),
                     int(90 + r_s*math.sin(a_s))))
oled.draw_polygon(pts_star, YELLOW)
oled.show(); time.sleep(3)

# 4 : Sinusoide multi-frequences
oled.fill(BLACK)
oled.text("Multi sinusoide ", 0, 0, WHITE)
oled.hline(0, 64, W, GRAY)
params = [
    (10, 1, RED,    0.0),
    (7,  2, GREEN,  1.0),
    (5,  3, BLUE,   2.0),
    (4,  5, YELLOW, 0.5),
]
for amp, freq, col, phase in params:
    oled.draw_sine_wave(0, 64, W, amp*3, freq, col, phase)
oled.show(); time.sleep(3)

# Sinusoide animee
phase = 0
for _ in range(120):
    oled.fill_rect(0, 12, W, 116, BLACK)
    oled.hline(0, 64, W, color565(30,30,30))
    oled.draw_sine_wave(0, 64, W, 40, 2, RED,   phase)
    oled.draw_sine_wave(0, 64, W, 30, 3, GREEN, phase + 1.0)
    oled.draw_sine_wave(0, 64, W, 20, 5, BLUE,  phase + 2.0)
    oled.show()
    phase += 0.08
    time.sleep_ms(30)

# 5 : Defilement texte (scroll_text)
oled.fill(BLACK)
oled.fill_rect(0, 0, W, 14, color565(0,60,0))
oled.text("Scroll text     ", 0, 3, WHITE)
oled.scroll_text("  Prof. MOFFO LONLA Bertrand -- UB COT / Labo GIA Douala  ",
                 56, GREEN, BLACK, delay_ms=40)
oled.scroll_text("  SSD1351 RGB OLED 1.5\" -- 128x128 -- ESP32-S3  ",
                 72, CYAN, BLACK, delay_ms=40)

# 6 : Scrolling materiel SSD1351
oled.fill(BLACK)
oled.text("Scroll materiel ", 0, 0, WHITE)
for i in range(16):
    oled.fill_rect(0, 8 + i*7, W, 7,
                   hsv_to_rgb565(i*22, 1.0, 1.0))
    oled.text("Ligne {:2d}".format(i+1), 0, 8+i*7, BLACK)
oled.show(); time.sleep(1)
oled.start_scroll(0, 127, speed=0x00)
time.sleep(4)
oled.stop_scroll()

# 7 : Rotation de l'affichage
oled.fill(BLACK)
oled.fill_triangle(10, 10, 118, 10, 64, 50, RED)
oled.fill_rect(10, 56, 108, 60, BLUE)
oled.text("Rotation test   ", 10, 70, WHITE)
oled.fill_circle(20, 110, 12, GREEN)
oled.show()
time.sleep(1)
for angle in [90, 180, 270, 0]:
    oled.rotate(angle)
    time.sleep(1.5)
oled.rotate(0)

# Fin
oled.fill(BLACK)
oled.text("Exemple 6  OK ! ", 0, 60, GREEN)
oled.show()
print("Exemple 6 termine.")
