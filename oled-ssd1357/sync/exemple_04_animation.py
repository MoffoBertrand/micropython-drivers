"""
exemple_04_animation.py
=========================================================
Exemple 4 — Animations : balle, horloge, chenillard,
            particules, show_region
Module  : RGB OLED 0.96" SSD1357 (Waveshare)
Cible   : ESP32-S3 — MicroPython v1.21+
=========================================================
"""
import time, math, random
from ssd1357 import (SSD1357, color565,
                     BLACK, WHITE, RED, GREEN, BLUE,
                     YELLOW, CYAN, MAGENTA, GRAY)

oled = SSD1357()
W, H = oled.width, oled.height   # 64, 128

# ── 1 : Balle rebondissante (show_region) ────────────────
bx, by = 20.0, 40.0
vx, vy = 1.8, 2.2
R = 6
for _ in range(250):
    ox, oy = int(bx), int(by)
    bx += vx; by += vy
    if bx <= R or bx >= W - R: vx = -vx; bx = max(R, min(W-R, bx))
    if by <= R or by >= H - R: vy = -vy; by = max(R, min(H-R, by))
    nx, ny = int(bx), int(by)
    # Effacer ancienne position
    oled.fill_circle(ox, oy, R + 1, BLACK)
    # Dessiner nouvelle position
    oled.fill_circle(nx, ny, R, color565(255, 160, 0))
    oled.draw_circle(nx, ny, R, WHITE)
    # Mise a jour partielle
    x0 = max(0, min(ox, nx) - R - 2)
    y0 = max(0, min(oy, ny) - R - 2)
    x1 = min(W-1, max(ox, nx) + R + 2)
    y1 = min(H-1, max(oy, ny) + R + 2)
    oled.show_region(x0, y0, x1, y1)
    time.sleep_ms(18)

oled.fill(BLACK); oled.show()

# ── 2 : Horloge analogique ────────────────────────────────
cx, cy, Rc = 32, 64, 28

def draw_clock(sec):
    oled.fill(BLACK)
    oled.draw_circle(cx, cy, Rc, WHITE)
    oled.fill_circle(cx, cy, 2, WHITE)
    # Graduations
    for i in range(12):
        a = i * math.pi / 6 - math.pi / 2
        x0 = int(cx + (Rc-3) * math.cos(a))
        y0 = int(cy + (Rc-3) * math.sin(a))
        x1 = int(cx + Rc * math.cos(a))
        y1 = int(cy + Rc * math.sin(a))
        oled.line(x0, y0, x1, y1, WHITE)
    # Aiguille heures
    ah = (sec//3600 % 12)*math.pi/6 + (sec%3600)*math.pi/21600 - math.pi/2
    oled.line(cx, cy, cx+int(Rc*0.55*math.cos(ah)),
              cy+int(Rc*0.55*math.sin(ah)), WHITE)
    # Aiguille minutes
    am = (sec//60 % 60)*math.pi/30 - math.pi/2
    oled.line(cx, cy, cx+int(Rc*0.78*math.cos(am)),
              cy+int(Rc*0.78*math.sin(am)), CYAN)
    # Aiguille secondes
    a_s = (sec % 60)*math.pi/30 - math.pi/2
    oled.line(cx, cy, cx+int(Rc*0.9*math.cos(a_s)),
              cy+int(Rc*0.9*math.sin(a_s)), RED)
    # Titre
    oled.fill_rect(0, 0, 64, 10, color565(0,40,80))
    oled.text("Horloge ", 0, 1, WHITE)
    oled.show()

t0 = time.ticks_ms()
for _ in range(60):
    draw_clock(time.ticks_diff(time.ticks_ms(), t0)//1000 + 10*3600 + 30*60)
    time.sleep_ms(1000)

oled.fill(BLACK); oled.show()

# ── 3 : Chenillard ───────────────────────────────────────
NLED, LED_H = 16, 8
for _ in range(4):
    for i in range(NLED):
        oled.fill(BLACK)
        for j in range(NLED):
            d = abs(j - i)
            if   d == 0: c = color565(0, 255, 0)
            elif d == 1: c = color565(0, 120, 0)
            elif d == 2: c = color565(0,  40, 0)
            else:        c = color565(0,   8, 0)
            oled.fill_rect(0, j * LED_H, 64, LED_H-1, c)
        oled.show()
        time.sleep_ms(60)

oled.fill(BLACK); oled.show()

# ── 4 : Particules ───────────────────────────────────────
N = 35
px_a  = [random.uniform(0, W) for _ in range(N)]
py_a  = [random.uniform(0, H) for _ in range(N)]
pvx_a = [random.uniform(-1.5, 1.5) for _ in range(N)]
pvy_a = [random.uniform(-1.5, 1.5) for _ in range(N)]
pc_a  = [color565(random.randint(80,255),
                  random.randint(80,255),
                  random.randint(80,255)) for _ in range(N)]

for _ in range(150):
    oled.fill(BLACK)
    for i in range(N):
        px_a[i] += pvx_a[i]; py_a[i] += pvy_a[i]
        if px_a[i] < 0 or px_a[i] >= W: pvx_a[i] = -pvx_a[i]
        if py_a[i] < 0 or py_a[i] >= H: pvy_a[i] = -pvy_a[i]
        oled.pixel(int(px_a[i]), int(py_a[i]), pc_a[i])
    oled.show()
    time.sleep_ms(25)

# ── Fin ──────────────────────────────────────────────────
oled.fill(BLACK)
oled.text("Exemple4", 0, 56, GREEN)
oled.show()
print("Exemple 4 termine.")
