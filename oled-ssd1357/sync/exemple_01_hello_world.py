"""
exemple_01_hello_world.py
=========================================================
Exemple 1 — Hello World & primitives geometriques
Module  : RGB OLED 0.96" SSD1357 (Waveshare)
Cible   : ESP32-S3 — MicroPython v1.21+
Ecran   : 64 x 128 px, portrait, RGB565
=========================================================
"""
import time
from ssd1357 import (SSD1357, color565,
                     BLACK, WHITE, RED, GREEN, BLUE,
                     YELLOW, CYAN, MAGENTA, ORANGE, GRAY)

oled = SSD1357()
print(oled)

# ── 1 : Ecran blanc ──────────────────────────────────────
oled.fill(WHITE); oled.show(); time.sleep_ms(600)

# ── 2 : Texte 8x8 (8 car max par ligne sur 64 px) ───────
oled.fill(BLACK)
oled.text("Hello!  ", 0,   0, WHITE)
oled.text("SSD1357 ", 0,  12, YELLOW)
oled.text("Waveshar", 0,  24, CYAN)
oled.text("ESP32-S3", 0,  36, GREEN)
oled.text("64x128  ", 0,  48, ORANGE)
oled.text("RGB565  ", 0,  60, MAGENTA)
oled.text("UB COT  ", 0,  72, RED)
oled.text("Douala  ", 0,  84, BLUE)
oled.text("v6.0.0  ", 0,  96, GRAY)
oled.show(); time.sleep(2)

# ── 3 : Bandes couleurs (8 x 16 px) ─────────────────────
oled.fill(BLACK)
palette = [RED, GREEN, BLUE, YELLOW, CYAN, MAGENTA, ORANGE, WHITE]
for i, c in enumerate(palette):
    oled.fill_rect(0, i * 16, 64, 16, c)
oled.show(); time.sleep(2)

# ── 4 : Cadre + croix centrale + coins colores ───────────
oled.fill(BLACK)
oled.rect(0, 0, 64, 128, WHITE)          # cadre complet
oled.hline(0,  64, 64, GRAY)            # ligne mediane H
oled.vline(32,  0, 128, GRAY)           # ligne mediane V
oled.fill_rect( 1,   1, 10, 10, RED)    # coin haut-gauche
oled.fill_rect(53,   1, 10, 10, GREEN)  # coin haut-droite
oled.fill_rect( 1, 117, 10, 10, BLUE)   # coin bas-gauche
oled.fill_rect(53, 117, 10, 10, YELLOW) # coin bas-droite
oled.fill_circle(32, 64, 5, WHITE)      # centre
oled.show(); time.sleep(2)

# ── 5 : Lignes et diagonales ─────────────────────────────
oled.fill(BLACK)
oled.line(0, 0,  63, 127, RED)
oled.line(63, 0,  0, 127, BLUE)
oled.hline(0, 63, 64, GREEN)
oled.vline(31, 0, 128, YELLOW)
oled.show(); time.sleep(2)

# ── 6 : Cercles ──────────────────────────────────────────
oled.fill(BLACK)
oled.draw_circle(32,  32, 28, WHITE)
oled.fill_circle(32,  96, 28, RED)
oled.fill_circle(32,  96, 18, BLUE)
oled.fill_circle(32,  96,  8, WHITE)
oled.show(); time.sleep(2)

# ── 7 : Triangles et coins arrondis ──────────────────────
oled.fill(BLACK)
oled.draw_triangle(4, 4, 60, 4, 32, 60, CYAN)
oled.draw_rounded_rect(4, 68, 56, 56, 8, YELLOW)
oled.show(); time.sleep(2)

# ── Fin ──────────────────────────────────────────────────
oled.fill(BLACK)
oled.text("Exemple1", 0, 56, GREEN)
oled.show()
print("Exemple 1 termine.")
