"""
exemple_02_couleurs.py — SSD1351 RGB OLED 1.5" (128x128)
Exemple 2 : Couleurs avancees, degrades, roue HSV, fondu
"""
import time, math
from ssd1351 import (SSD1351, color565, hsv_to_rgb565, blend,
                     BLACK, WHITE, RED, GREEN, BLUE,
                     YELLOW, CYAN, MAGENTA)

oled = SSD1351()

# 1 : Roue chromatique complete (disque HSV)
oled.fill(BLACK)
oled.draw_colorwheel(64, 64, 60, 0)
oled.show(); time.sleep(2)

# 2 : Roue chromatique annulaire
oled.fill(BLACK)
oled.draw_colorwheel(64, 64, 62, 30)
oled.fill_circle(64, 64, 28, color565(20, 20, 20))
oled.text("  HSV   ", 16, 58, WHITE)
oled.text(" Colour ", 16, 70, WHITE)
oled.show(); time.sleep(2)

# 3 : Degrade vertical (3 transitions)
oled.fill(BLACK)
oled.gradient_fill(0,   0, 128, 43, RED,   YELLOW)
oled.gradient_fill(0,  43, 128, 42, YELLOW, GREEN)
oled.gradient_fill(0,  85, 128, 43, GREEN,  BLUE)
oled.show(); time.sleep(2)

# 4 : Degrade horizontal
oled.gradient_fill_h(0, 0, 128, 64, RED,   BLUE)
oled.gradient_fill_h(0,64, 128, 64, CYAN,  MAGENTA)
oled.show(); time.sleep(2)

# 5 : Degrade radial
oled.fill(BLACK)
oled.gradient_fill_radial(64, 64, 0, 60, WHITE, BLACK)
oled.show(); time.sleep(2)

# 6 : Damier
oled.fill(BLACK)
oled.draw_checkerboard(0, 0, 128, 128, 16,
                       color565(200, 50, 0),
                       color565(0, 50, 200))
oled.show(); time.sleep(2)

# 7 : Palette HSV complete (bandes teinte)
oled.fill(BLACK)
for x in range(128):
    hue = x * 360 / 128
    c = hsv_to_rgb565(hue, 1.0, 1.0)
    oled.vline(x, 0, 42, c)
    c2 = hsv_to_rgb565(hue, 0.5, 1.0)
    oled.vline(x, 43, 42, c2)
    c3 = hsv_to_rgb565(hue, 1.0, 0.5)
    oled.vline(x, 86, 42, c3)
oled.text("Saturation=1.0  ", 0,  14, BLACK)
oled.text("Saturation=0.5  ", 0,  57, BLACK)
oled.text("Valeur=0.5      ", 0, 100, BLACK)
oled.show(); time.sleep(2)

# 8 : Melange de couleurs (blend)
oled.fill(BLACK)
colors_pairs = [(RED, BLUE), (GREEN, YELLOW), (CYAN, MAGENTA), (WHITE, BLACK)]
for row, (c1, c2) in enumerate(colors_pairs):
    for col in range(128):
        t = col / 127.0
        oled.fill_rect(col, row * 32, 1, 30, blend(c1, c2, t))
oled.show(); time.sleep(2)

# 9 : Fondu entree / sortie
oled.fill(BLACK)
oled.fill_circle(64, 64, 55, RED)
oled.fill_circle(64, 64, 40, GREEN)
oled.fill_circle(64, 64, 25, BLUE)
oled.fill_circle(64, 64, 10, WHITE)
oled.set_master_contrast(0)
oled.show()
oled.fade_in(steps=15, delay_ms=40)
time.sleep(1)
oled.fade_out(steps=15, delay_ms=40)

# Fin
oled.fill(BLACK)
oled.text("Exemple 2  OK ! ", 0, 60, GREEN)
oled.show()
oled.set_master_contrast(15)
print("Exemple 2 termine.")
