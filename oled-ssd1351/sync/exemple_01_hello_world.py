"""
exemple_01_hello_world.py — SSD1351 RGB OLED 1.5" (128x128)
Exemple 1 : Hello World, texte, formes de base
"""
import time
from ssd1351 import (SSD1351, color565,
                     BLACK, WHITE, RED, GREEN, BLUE,
                     YELLOW, CYAN, MAGENTA, ORANGE, GRAY)

oled = SSD1351()
print(oled)

# 1 : Blanc total
oled.fill(WHITE); oled.show(); time.sleep_ms(600)

# 2 : Texte 8x8 (16 car max par ligne sur 128px)
oled.fill(BLACK)
oled.text("Hello World!    ", 0,  0, WHITE)
oled.text("SSD1351 RGB OLED",  0, 12, YELLOW)
oled.text("128 x 128 pixels",  0, 24, CYAN)
oled.text("ESP32-S3        ",  0, 36, GREEN)
oled.text("MicroPython v1.2",  0, 48, ORANGE)
oled.text("RGB565 - 65K col",  0, 60, MAGENTA)
oled.text("UB COT / Douala ",  0, 72, RED)
oled.text("Prof. MOFFO L.  ",  0, 84, BLUE)
oled.text("v1.0.0          ",  0, 96, GRAY)
oled.show(); time.sleep(2)

# 3 : Palette couleurs (8 bandes de 16 px)
oled.fill(BLACK)
palette = [RED, GREEN, BLUE, YELLOW, CYAN, MAGENTA, ORANGE, WHITE]
for i, c in enumerate(palette):
    oled.fill_rect(0, i * 16, 128, 16, c)
    oled.text(["RED ", "GRN ", "BLU ", "YEL ",
               "CYN ", "MAG ", "ORG ", "WHT "][i], 2, i*16+4, BLACK)
oled.show(); time.sleep(2)

# 4 : Cadre + croix + coins colores
oled.fill(BLACK)
oled.rect(0, 0, 128, 128, WHITE)
oled.hline(0, 64, 128, GRAY)
oled.vline(64, 0, 128, GRAY)
oled.fill_rect( 1,  1, 14, 14, RED)
oled.fill_rect(113, 1, 14, 14, GREEN)
oled.fill_rect( 1,113, 14, 14, BLUE)
oled.fill_rect(113,113, 14, 14, YELLOW)
oled.fill_circle(64, 64, 8, WHITE)
oled.text("64x64", 40, 60, BLACK)
oled.show(); time.sleep(2)

# 5 : Lignes et diagonales
oled.fill(BLACK)
oled.line(0,   0, 127, 127, RED)
oled.line(127, 0,   0, 127, BLUE)
oled.hline(0, 64, 128, GREEN)
oled.vline(64,  0, 128, YELLOW)
oled.draw_cross(64, 64, 30, WHITE, 2)
oled.show(); time.sleep(2)

# 6 : Cercles et ellipses
oled.fill(BLACK)
oled.draw_circle(32,  32, 28, WHITE)
oled.fill_circle(96,  32, 28, RED)
oled.fill_circle(96,  32, 18, BLUE)
oled.fill_circle(96,  32,  8, WHITE)
oled.draw_ellipse(64, 96, 55, 24, CYAN)
oled.fill_ellipse(64, 96, 40, 16, color565(50, 200, 50))
oled.show(); time.sleep(2)

# 7 : Triangles plein et vide
oled.fill(BLACK)
oled.draw_triangle(4, 4, 124, 4, 64, 60, CYAN)
oled.fill_triangle(4, 68, 124, 68, 64, 124, color565(255, 100, 0))
oled.show(); time.sleep(2)

# 8 : Rectangles coins arrondis
oled.fill(BLACK)
oled.draw_rounded_rect(4,   4, 120, 56, 12, CYAN)
oled.fill_rounded_rect(4,  68, 120, 56, 12, color565(80, 0, 140))
oled.text("  Rounded  Rect ", 4, 88, WHITE)
oled.show(); time.sleep(2)

# 9 : Losanges
oled.fill(BLACK)
oled.draw_diamond(32,  64, 50, 80, WHITE)
oled.fill_diamond(96,  64, 50, 80, color565(200, 100, 0))
oled.show(); time.sleep(2)

# Fin
oled.fill(BLACK)
oled.draw_rounded_rect(0, 0, 128, 128, 10, GREEN)
oled.text("Exemple 1  OK ! ", 0, 56, WHITE)
oled.show()
print("Exemple 1 termine.")
