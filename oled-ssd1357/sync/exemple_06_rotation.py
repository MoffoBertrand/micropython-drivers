"""
exemple_06_rotation.py
=========================================================
Exemple 6 — Rotation de l'affichage
Module  : RGB OLED 0.96" SSD1357 (Waveshare)
Cible   : ESP32-S3 — MicroPython v1.21+

La rotation agit sur le registre REMAP (0xA0) du SSD1357.
Base 0x60 (col/row swap + BGR) + bits de direction :
  0°  -> 0x60   90°  -> 0x63
  180°-> 0x72   270° -> 0x71
=========================================================
"""
import time
from ssd1357 import (SSD1357, color565,
                     BLACK, WHITE, RED, GREEN, BLUE, YELLOW, CYAN)

oled = SSD1357()

def scene(angle):
    """Dessine une scene asymetrique pour visualiser la rotation."""
    oled.fill(BLACK)
    # Barre titre avec angle
    oled.fill_rect(0, 0, 64, 12, color565(0, 60, 120))
    oled.text("Rot {:3d}".format(angle), 0, 2, WHITE)
    # Triangle indicateur de haut
    oled.draw_triangle(28, 14, 36, 14, 32, 20, YELLOW)
    # Rectangle rouge a gauche
    oled.fill_rect(0, 30, 20, 60, RED)
    oled.text("G", 6, 55, WHITE)
    # Rectangle vert a droite
    oled.fill_rect(44, 30, 20, 60, GREEN)
    oled.text("D", 50, 55, WHITE)
    # Cercle centre
    oled.fill_circle(32, 90, 10, CYAN)
    oled.text("O", 28, 86, BLACK)
    oled.show()

for angle in [0, 90, 180, 270, 0]:
    oled.rotate(angle)
    scene(angle)
    time.sleep(2)

print("Rotation actuelle :", oled.get_rotation(), "deg")
print("Exemple 6 termine.")
