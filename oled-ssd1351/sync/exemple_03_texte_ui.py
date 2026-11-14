"""
exemple_03_texte_ui.py — SSD1351 RGB OLED 1.5" (128x128)
Exemple 3 : Texte agrandi, UI dashboard, oscilloscope, menu
"""
import time, math, random
from ssd1351 import (SSD1351, color565,
                     BLACK, WHITE, RED, GREEN, BLUE,
                     YELLOW, CYAN, MAGENTA, ORANGE, GRAY)

oled = SSD1351()

# 1 : Texte agrandi (scale 1..4)
for scale in range(1, 5):
    oled.fill(BLACK)
    oled.text("Scale={}".format(scale), 0, 0, GRAY)
    oled.draw_text_large("RGB", 0, 16, scale, CYAN, BLACK)
    oled.show(); time.sleep(1)

# 2 : Affichage numerique style LED (scale 4)
oled.fill(BLACK)
oled.fill_rect(0, 0, 128, 14, color565(0, 60, 120))
oled.text("Compteur  ", 20, 3, WHITE)
for val in range(0, 101, 5):
    oled.fill_rect(0, 16, 128, 48, BLACK)
    oled.draw_text_large("{:3d}".format(val), 4, 20, 3, YELLOW, BLACK)
    oled.fill_rect(0, 68, 128, 8, BLACK)
    oled.draw_progress_bar(4, 70, 120, 12, val, fg=GREEN, bg=GRAY,
                           border=WHITE, radius=4)
    oled.show()
    time.sleep_ms(80)
time.sleep(1)

# 3 : Dashboard multi-capteurs (simule)
def draw_dashboard(temp, hum, pres, bat):
    oled.fill(BLACK)
    # Titre
    oled.fill_rounded_rect(0, 0, 128, 16, 4, color565(0, 50, 100))
    oled.text(" DASHBOARD      ", 0, 4, WHITE)
    # Separateurs
    oled.hline(0, 18, 128, GRAY)
    oled.vline(64, 18, 90, GRAY)
    # Temperature
    oled.text("TEMP", 4, 22, CYAN)
    col_t = RED if temp>35 else YELLOW if temp>28 else GREEN
    oled.draw_text_large("{:.0f}".format(temp), 4, 34, 2, col_t)
    oled.text("deg C", 4, 54, col_t)
    # Humidite
    oled.text("HUM%", 68, 22, CYAN)
    oled.draw_text_large("{:.0f}".format(hum), 68, 34, 2, color565(100,180,255))
    oled.text("  %", 68, 54, GRAY)
    # Pression
    oled.text("PRES", 4, 68, CYAN)
    oled.text("{:.0f}hPa".format(pres), 4, 80, color565(200,200,100))
    # Batterie
    oled.text("BAT ", 68, 68, CYAN)
    oled.draw_progress_bar(68, 80, 56, 10, bat, fg=GREEN, bg=GRAY,
                           border=WHITE, radius=2)
    oled.text("{:.0f}%".format(bat), 68, 94, GRAY)
    # Ligne bas
    oled.hline(0, 108, 128, GRAY)
    import time as t
    ms = t.ticks_ms() % 1000
    oled.text("t={:04d}ms ".format(ms), 4, 112, GRAY)
    oled.show()

for _ in range(30):
    draw_dashboard(
        22 + random.uniform(0, 18),
        45 + random.uniform(-15, 35),
        1013 + random.uniform(-5, 5),
        random.uniform(10, 100)
    )
    time.sleep_ms(400)

# 4 : Oscilloscope 3 canaux
oled.fill(BLACK)
oled.fill_rect(0, 0, 128, 14, color565(30, 30, 80))
oled.text("Oscilloscope    ", 0, 3, WHITE)

CH_H = 36  # hauteur par canal
phase = [0, 2.09, 4.19]  # dephasages 120 degres
colors = [RED, GREEN, BLUE]

for frame in range(100):
    oled.fill_rect(0, 14, 128, 114, BLACK)
    # 3 axes
    for ch in range(3):
        y_center = 14 + ch * CH_H + CH_H // 2
        oled.hline(0, y_center, 128, color565(30, 30, 30))
        # Signal
        prev_y = None
        for px in range(128):
            val = math.sin(px * 2 * math.pi / 64 + phase[ch] + frame * 0.15)
            py = int(y_center + val * 14)
            py = max(14 + ch * CH_H + 2, min(14 + (ch+1)*CH_H - 2, py))
            if prev_y is not None:
                oled.line(px-1, prev_y, px, py, colors[ch])
            prev_y = py
        # Label
        oled.text("CH{}".format(ch+1), 0, 14 + ch * CH_H + 2, colors[ch])
    oled.show()
    time.sleep_ms(40)

# Fin
oled.fill(BLACK)
oled.text("Exemple 3  OK ! ", 0, 60, GREEN)
oled.show()
print("Exemple 3 termine.")
