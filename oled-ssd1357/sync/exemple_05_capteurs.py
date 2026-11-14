"""
exemple_05_capteurs.py
=========================================================
Exemple 5 — Capteurs ESP32-S3 : temperature MCU,
            ADC GPIO4, tracé temps réel, bitmap, compte
Module  : RGB OLED 0.96" SSD1357 (Waveshare)
Cible   : ESP32-S3 — MicroPython v1.21+
=========================================================
"""
import time, math, esp32
from machine import ADC, Pin
from ssd1357 import (SSD1357, color565,
                     BLACK, WHITE, RED, GREEN, BLUE,
                     YELLOW, CYAN, GRAY, MAGENTA)

oled = SSD1357()
W, H = oled.width, oled.height

# ADC GPIO 4
adc = ADC(Pin(4))
adc.atten(ADC.ATTN_11DB)
adc.width(ADC.WIDTH_12BIT)

# ── 1 : Tracé température MCU en temps réel (30 s) ───────
history = [0.0] * W

def push(val):
    history.pop(0); history.append(val)

def plot(title, unit, mn, mx, color):
    oled.fill(BLACK)
    oled.fill_rect(0, 0, W, 12, color565(30, 30, 80))
    oled.text(title[:8], 0, 2, WHITE)
    oled.rect(0, 14, W, H-14, GRAY)
    prev_y = None
    for px in range(W):
        v = history[px]
        py = 14 + (H-15) - 1 - int((v-mn)/(mx-mn)*(H-16))
        py = max(15, min(H-2, py))
        if prev_y is not None:
            oled.line(px-1, prev_y, px, py, color)
        prev_y = py
    oled.text("{:.1f}{}".format(history[-1], unit), 0, H-10, color)
    oled.show()

print("Temperature MCU (30 s)...")
for _ in range(120):
    push(esp32.mcu_temperature())
    plot("TempMCU", "C", 20, 80, RED)
    time.sleep_ms(250)

# ── 2 : ADC temps réel (20 s) ────────────────────────────
history = [0.0] * W
print("ADC GPIO4 (20 s)...")
for _ in range(200):
    push(adc.read() * 3.3 / 4095)
    plot("ADC GP4", "V", 0.0, 3.3, CYAN)
    time.sleep_ms(100)

# ── 3 : Bitmap monochrome 1bpp (logo 16x16) ──────────────
LOGO = bytes([
    0b11111111, 0b11111111,
    0b11000000, 0b00000011,
    0b11001111, 0b11110011,
    0b11001001, 0b00100011,
    0b11001001, 0b00100011,
    0b11001111, 0b11110011,
    0b11001000, 0b10000011,
    0b11001000, 0b10000011,
    0b11001000, 0b10000011,
    0b11001111, 0b11111111,
    0b11000000, 0b00000011,
    0b11111111, 0b11111111,
    0b00000000, 0b00000000,
    0b00000000, 0b00000000,
    0b00000000, 0b00000000,
    0b00000000, 0b00000000,
])
oled.fill(BLACK)
oled.text("Bitmap  ", 0, 4, WHITE)
oled.draw_bitmap_mono( 4, 20, LOGO, 16, 16, GREEN,  BLACK)  # x1
oled.draw_bitmap_mono( 4, 50, LOGO, 16, 16, YELLOW, BLACK)  # x1 jaune
# Version agrandie x2 manuellement
for py in range(16):
    for px in range(16):
        idx = (py*16+px)//8
        bit = 7-((py*16+px)%8)
        if LOGO[idx] & (1<<bit):
            oled.fill_rect(28+px*2, 20+py*2, 2, 2, CYAN)
oled.show(); time.sleep(3)

# ── 4 : Compte a rebours ─────────────────────────────────
for s in range(10, -1, -1):
    oled.fill(BLACK)
    oled.fill_rect(0, 0, 64, 14, color565(80, 0, 0))
    oled.text("Rebours ", 0, 3, WHITE)
    oled.draw_text_large(str(s), 16 if s >= 10 else 24, 30, 3, YELLOW)
    oled.hline(0, 126, 64, RED)
    oled.show()
    time.sleep(1)

oled.fill(BLACK)
oled.draw_text_large("GO!", 4, 50, 2, GREEN)
oled.show(); time.sleep(1)

# ── Fin ──────────────────────────────────────────────────
oled.fill(BLACK)
oled.text("Exemple5", 0, 56, GREEN)
oled.show()
print("Exemple 5 termine.")
