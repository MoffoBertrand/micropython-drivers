"""
exemple_03_texte_ui.py
=========================================================
Exemple 3 — Texte agrandi, barre de progression, IHM
Module  : RGB OLED 0.96" SSD1357 (Waveshare)
Cible   : ESP32-S3 — MicroPython v1.21+
=========================================================
"""
import time, math
from ssd1357 import (SSD1357, color565,
                     BLACK, WHITE, RED, GREEN, BLUE,
                     YELLOW, CYAN, ORANGE, GRAY, MAGENTA)

oled = SSD1357()

# ── 1 : Texte agrandi (scale 1..3) ───────────────────────
for scale in range(1, 4):
    oled.fill(BLACK)
    oled.text("Scale={}".format(scale), 0, 0, GRAY)
    oled.draw_text_large("UB", 0, 16, scale, CYAN)
    oled.show(); time.sleep(1.2)

# ── 2 : Barre de progression animee ──────────────────────
oled.fill(BLACK)
oled.text("Chargem.", 0, 4, WHITE)
for pct in range(0, 101, 2):
    oled.fill_rect(0, 18, 64, 20, BLACK)
    oled.draw_progress_bar(2, 20, 60, 14, pct,
                           fg=GREEN, bg=GRAY, border=WHITE)
    oled.fill_rect(18, 38, 28, 10, BLACK)
    oled.text("{:3d}%".format(pct), 20, 38, YELLOW)
    oled.show(); time.sleep_ms(30)
time.sleep(1)

# ── 3 : Dashboard capteur (valeurs simulees) ─────────────
import random

def dashboard(temp, hum, bat):
    oled.fill(BLACK)
    # Titre
    oled.fill_rect(0, 0, 64, 12, color565(0, 60, 120))
    oled.text("SENSORS ", 0, 2, WHITE)
    # Temperature
    oled.text("T:", 0, 16, CYAN)
    col = RED if temp > 35 else YELLOW if temp > 28 else GREEN
    oled.text("{:.1f}C".format(temp), 16, 16, col)
    # Humidite
    oled.text("H:", 0, 28, CYAN)
    oled.text("{:.0f}%".format(hum), 16, 28, color565(100,200,255))
    # Batterie
    oled.text("Bat", 0, 42, CYAN)
    oled.draw_progress_bar(0, 54, 64, 10, bat,
                           fg=color565(0,220,0), bg=GRAY, border=WHITE)
    oled.text("{:.0f}%".format(bat), 24, 68, GRAY)
    oled.show()

for _ in range(20):
    dashboard(22 + random.uniform(0, 16),
              50 + random.uniform(-20, 30),
              random.uniform(5, 100))
    time.sleep_ms(500)

# ── 4 : Oscilloscope sin(t) ───────────────────────────────
oled.fill(BLACK)
oled.fill_rect(0, 0, 64, 12, color565(40, 40, 40))
oled.text("sin(t)  ", 0, 2, YELLOW)

phase = 0
for _ in range(80):
    oled.fill_rect(0, 14, 64, 114, BLACK)
    oled.hline(0, 71, 64, GRAY)          # axe zero
    prev_y = None
    for px in range(64):
        val = math.sin(px * 2 * math.pi / 64 + phase) * 0.9
        py  = 14 + int((1 - val) / 2 * 113)
        if prev_y is not None:
            oled.line(px - 1, prev_y, px, py, CYAN)
        prev_y = py
    oled.show()
    phase += 0.2
    time.sleep_ms(40)

# ── Fin ──────────────────────────────────────────────────
oled.fill(BLACK)
oled.text("Exemple3", 0, 56, GREEN)
oled.show()
print("Exemple 3 termine.")
