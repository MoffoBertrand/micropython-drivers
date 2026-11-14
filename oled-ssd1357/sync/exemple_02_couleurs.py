"""
exemple_02_couleurs.py
=========================================================
Exemple 2 — Couleurs, degrades et contraste
Module  : RGB OLED 0.96" SSD1357 (Waveshare)
Cible   : ESP32-S3 — MicroPython v1.21+
=========================================================
"""
import time, math
from ssd1357 import (SSD1357, color565,
                     BLACK, WHITE, RED, GREEN, BLUE,
                     YELLOW, CYAN, MAGENTA)

oled = SSD1357()

# ── 1 : Roue chromatique en cercles concentriques ────────
oled.fill(BLACK)
for r in range(28, 0, -4):
    hue = (28 - r) * 45          # 0..315 degres
    h = hue // 60
    f = (hue % 60) / 60.0
    if   h == 0: rv,gv,bv = 1,   f,   0
    elif h == 1: rv,gv,bv = 1-f, 1,   0
    elif h == 2: rv,gv,bv = 0,   1,   f
    elif h == 3: rv,gv,bv = 0,   1-f, 1
    elif h == 4: rv,gv,bv = f,   0,   1
    else:        rv,gv,bv = 1,   0,   1-f
    c = color565(int(rv*255), int(gv*255), int(bv*255))
    oled.fill_circle(32, 64, r, c)
oled.show(); time.sleep(2)

# ── 2 : Degrade vertical (3 zones) ───────────────────────
oled.fill(BLACK)
oled.gradient_fill(0,   0, 64, 43, RED,   YELLOW)
oled.gradient_fill(0,  43, 64, 42, YELLOW, GREEN)
oled.gradient_fill(0,  85, 64, 43, GREEN,  BLUE)
oled.show(); time.sleep(2)

# ── 3 : Degrade noir -> blanc ─────────────────────────────
oled.gradient_fill(0, 0, 64, 128,
                   color565(0,0,0), color565(255,255,255))
oled.show(); time.sleep(1.5)

# ── 4 : Inversion d'affichage ────────────────────────────
oled.fill(BLACK)
oled.fill_circle(32, 40, 30, color565(255, 140, 0))
oled.fill_rect(0, 80, 64, 48, color565(0, 160, 255))
oled.text("Normal  ", 0, 90, WHITE)
oled.show(); time.sleep(1)
for _ in range(6):
    oled.invert(True);  time.sleep_ms(400)
    oled.invert(False); time.sleep_ms(400)

# ── 5 : Niveaux de contraste ─────────────────────────────
oled.fill(BLACK)
oled.text("Contraste", 0, 0, WHITE)
for level in range(0, 16, 2):
    oled.set_master_contrast(level)
    oled.fill_rect(0, 14, 64, 100, color565(255, 180, 50))
    oled.text("Niv {:2d}".format(level), 4, 56, BLACK)
    oled.show(); time.sleep_ms(400)
oled.set_master_contrast(15)

# ── Fin ──────────────────────────────────────────────────
oled.fill(BLACK)
oled.text("Exemple2", 0, 56, GREEN)
oled.show()
print("Exemple 2 termine.")
