"""
exemple_05_capteurs.py — SSD1351 RGB OLED 1.5" (128x128)
Exemple 5 : Capteurs ESP32-S3, ADC, tracé temps réel, bitmap
"""
import time, math, esp32
from machine import ADC, Pin
from ssd1351 import (SSD1351, color565, hsv_to_rgb565,
                     BLACK, WHITE, RED, GREEN, BLUE,
                     YELLOW, CYAN, GRAY, MAGENTA, ORANGE)

oled = SSD1351()
W, H = oled.width, oled.height

adc = ADC(Pin(4))
adc.atten(ADC.ATTN_11DB)
adc.width(ADC.WIDTH_12BIT)

HIST_W = W
history = [0.0] * HIST_W

def push(val):
    history.pop(0); history.append(val)

def plot(title, unit, mn, mx, color, sub=""):
    oled.fill(BLACK)
    # Header
    oled.fill_rounded_rect(0, 0, W, 18, 4, color565(0, 40, 80))
    oled.text(title[:16], 0, 5, WHITE)
    # Zone graphique
    GY, GH = 22, 80
    oled.rect(0, GY, W, GH, GRAY)
    oled.hline(1, GY + GH//2, W-2, color565(40,40,40))
    # Courbe
    prev_y = None
    for px in range(W):
        v = history[px]
        ratio = (v - mn) / max(mx - mn, 0.001)
        py = GY + GH - 2 - int(ratio * (GH - 4))
        py = max(GY+1, min(GY+GH-2, py))
        c_px = hsv_to_rgb565((1-ratio)*240, 1.0, 1.0)  # bleu->rouge
        if prev_y is not None:
            oled.line(px-1, prev_y, px, py, c_px)
        prev_y = py
    # Valeur courante
    cur = history[-1]
    col = RED if cur > (mx*0.8) else YELLOW if cur > (mx*0.5) else GREEN
    oled.draw_text_large("{:.1f}".format(cur), 0, 106, 2, col)
    oled.text(unit, 0, 122, GRAY)
    if sub:
        oled.text(sub[:8], 72, 122, GRAY)
    # Echelle
    oled.text("{:.0f}".format(mx), 104, GY+2, GRAY)
    oled.text("{:.0f}".format(mn), 104, GY+GH-10, GRAY)
    oled.show()

# 1 : Temp MCU (30 s)
print("Temperature MCU (30 s)...")
for _ in range(120):
    push(esp32.mcu_temperature())
    plot("Temp MCU", "deg C", 20, 80, RED, "ESP32-S3")
    time.sleep_ms(250)

# 2 : ADC GPIO4 (20 s)
history = [0.0] * HIST_W
print("ADC GPIO4 (20 s)...")
for _ in range(200):
    push(adc.read() * 3.3 / 4095)
    plot("ADC GPIO 4", "Volts", 0, 3.3, CYAN, "0-3.3V")
    time.sleep_ms(100)

# 3 : Comparaison 2 signaux (temp + ADC normalisee)
print("Double trace (15 s)...")
h1 = [0.0] * HIST_W
h2 = [0.0] * HIST_W

for frame in range(150):
    h1.pop(0); h1.append(esp32.mcu_temperature())
    h2.pop(0); h2.append(adc.read() * 80 / 4095 + 20)

    oled.fill(BLACK)
    oled.fill_rounded_rect(0,0,W,18,4,color565(0,40,80))
    oled.text("Dual Trace      ",0,5,WHITE)

    GY, GH = 22, 100
    oled.rect(0,GY,W,GH,GRAY)
    oled.hline(1, GY+GH//2, W-2, color565(40,40,40))

    for px in range(W):
        for h_arr, col in [(h1, RED), (h2, CYAN)]:
            v = h_arr[px]
            py = GY+GH-2-int((v-20)/(80-20)*(GH-4))
            py = max(GY+1, min(GY+GH-2, py))
            oled.pixel(px, py, col)

    oled.text("T:{:.1f}C".format(h1[-1]), 0, 122, RED)
    oled.text("V:{:.1f}V".format(h2[-1]*3.3/80), 64, 122, CYAN)
    oled.show()
    time.sleep_ms(100)

# 4 : Bitmap 32x32 (logo stylise)
LOGO32 = bytearray(32 * 32 // 8)  # 128 octets
# Dessiner un cercle et une croix dans le bitmap
for y in range(32):
    for x in range(32):
        cx, cy = 16, 16
        dist = ((x-cx)**2 + (y-cy)**2)**0.5
        is_ring = 13 < dist < 15
        is_cross = (abs(x-cx)<2 and abs(y-cy)<12) or (abs(y-cy)<2 and abs(x-cx)<12)
        if is_ring or is_cross:
            idx = (y * 32 + x) // 8
            bit = 7 - ((y * 32 + x) % 8)
            LOGO32[idx] |= (1 << bit)

oled.fill(BLACK)
oled.text("Bitmap 1bpp     ", 0, 4, WHITE)
# x1 normal
oled.draw_bitmap_mono(4,  20, LOGO32, 32, 32, GREEN, BLACK)
# x1 couleur differente
oled.draw_bitmap_mono(40, 20, LOGO32, 32, 32, YELLOW)
# x1 transparent sur fond colore
oled.fill_rect(76, 20, 48, 48, color565(0,0,100))
oled.draw_bitmap_mono(76, 20, LOGO32, 32, 32, WHITE)
# Bitmap agrandi x2
for row in range(32):
    for col in range(32):
        idx=(row*32+col)//8; bit=7-((row*32+col)%8)
        if LOGO32[idx]&(1<<bit):
            c=hsv_to_rgb565(col*360//32, 1.0, 1.0)
            oled.fill_rect(4+col*2, 70+row*2, 2, 2, c)
oled.text("x2 HSV          ", 0, 122, GRAY)
oled.show(); time.sleep(3)

# 5 : Compte a rebours
for s in range(10, -1, -1):
    oled.fill(BLACK)
    oled.fill_rounded_rect(0, 0, W, W, 12, color565(80,0,0))
    oled.fill_circle(W//2, H//2, 55, color565(20,0,0))
    oled.draw_circle(W//2, H//2, 55, RED)
    digits = str(s) if s >= 10 else " " + str(s)
    oled.draw_text_large(digits, 18, 44, 4, YELLOW)
    oled.hline(0, 124, W, RED)
    oled.show(); time.sleep(1)

oled.fill(BLACK)
oled.draw_text_large("GO!", 16, 44, 4, GREEN)
oled.show(); time.sleep(1)

oled.fill(BLACK)
oled.text("Exemple 5  OK ! ", 0, 60, GREEN)
oled.show()
print("Exemple 5 termine.")
