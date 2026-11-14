"""
async_exemple_02_multitaches.py — SSD1351Async RGB OLED 1.5"
Exemple Async 2 : 5 taches concurrentes
  Tache 1 : animation OLED (plasma + balle) @ 25 fps
  Tache 2 : temperature MCU toutes les 500 ms
  Tache 3 : ADC GPIO4 toutes les 100 ms
  Tache 4 : LED clignotante GPIO (independante de l'ecran)
  Tache 5 : console watchdog toutes les 5 s
"""
import uasyncio as asyncio
import esp32, math
from machine import ADC, Pin
from ssd1351_async import (SSD1351Async, color565, hsv_to_rgb565,
                            BLACK, WHITE, RED, GREEN, BLUE,
                            YELLOW, CYAN, GRAY, ORANGE, MAGENTA)

# ── Donnees partagees (pas de lock : chaque tache ecrit dans son propre champ)
class State:
    temp     = 25.0
    voltage  = 1.65
    frame    = 0
    phase    = 0.0

state = State()

# ── Tache 1 : Animation OLED ──────────────────────────────────────────────────
async def tache_affichage(oled):
    """Dashboard anime : sinusoide + jauge temp + jauge ADC + FPS."""
    W, H = oled.width, oled.height

    while True:
        state.phase += 0.08
        state.frame += 1
        oled.fill(BLACK)

        # Titre
        oled.fill_rounded_rect(0, 0, W, 16, 4, color565(0,40,80))
        oled.text("SSD1351 Async   ", 0, 4, WHITE)

        # Sinusoide couleur
        prev_y = None
        for px in range(W):
            val = math.sin(px * 2 * math.pi / W * 2 + state.phase)
            py  = int(20 + 16 + val * 14)
            hue = px * 360 / W
            c   = hsv_to_rgb565(hue, 1.0, 1.0)
            if prev_y is not None:
                oled.line(px-1, prev_y, px, py, c)
            prev_y = py

        # Température
        oled.text("T:", 0, 56, CYAN)
        col_t = RED if state.temp>50 else YELLOW if state.temp>40 else GREEN
        oled.draw_text_large("{:.0f}".format(state.temp), 16, 52, 2, col_t)
        oled.text("C", 64, 56, col_t)
        oled.draw_progress_bar(0, 74, 128, 10,
                               min(100, state.temp * 1.25),
                               fg=col_t, bg=GRAY, border=WHITE, radius=3)

        # ADC
        oled.text("V:", 0, 90, CYAN)
        oled.draw_text_large("{:.1f}".format(state.voltage), 16, 86, 2,
                             color565(100,180,255))
        oled.draw_progress_bar(0, 106, 128, 10,
                               state.voltage / 3.3 * 100,
                               fg=color565(100,180,255), bg=GRAY,
                               border=WHITE, radius=3)

        # Frame counter
        oled.text("F:{:5d}".format(state.frame), 0, 120, GRAY)

        oled.mark_dirty()
        await asyncio.sleep_ms(40)   # 25 fps

# ── Tache 2 : Temperature MCU ─────────────────────────────────────────────────
async def tache_temp():
    while True:
        state.temp = esp32.mcu_temperature()
        await asyncio.sleep_ms(500)

# ── Tache 3 : ADC ─────────────────────────────────────────────────────────────
async def tache_adc():
    adc = ADC(Pin(4))
    adc.atten(ADC.ATTN_11DB)
    adc.width(ADC.WIDTH_12BIT)
    while True:
        state.voltage = adc.read() * 3.3 / 4095
        await asyncio.sleep_ms(100)

# ── Tache 4 : LED clignotante ──────────────────────────────────────────────────
async def tache_led(pin_num=2):
    try:
        led = Pin(pin_num, Pin.OUT)
        while True:
            led(1); await asyncio.sleep_ms(100)
            led(0); await asyncio.sleep_ms(900)
    except Exception:
        while True: await asyncio.sleep_ms(1000)

# ── Tache 5 : Watchdog console ────────────────────────────────────────────────
async def tache_watchdog(oled):
    import time
    t0 = time.ticks_ms()
    while True:
        await asyncio.sleep_ms(5000)
        elapsed = time.ticks_diff(time.ticks_ms(), t0) / 1000
        stats = oled.get_stats()
        fps   = stats['frames'] / elapsed if elapsed > 0 else 0
        print("[WDT] T={:.1f}C V={:.2f}V F={} FPS={:.1f}".format(
              state.temp, state.voltage, stats['frames'], fps))

# ── MAIN ──────────────────────────────────────────────────────────────────────
async def main():
    oled = SSD1351Async()
    await oled.init()
    oled.start_refresh(fps=25)
    print("Demarrage 5 taches concurrentes (duree 30 s)...")

    try:
        await asyncio.wait_for(
            asyncio.gather(
                tache_affichage(oled),
                tache_temp(),
                tache_adc(),
                tache_led(2),
                tache_watchdog(oled),
            ),
            30
        )
    except asyncio.TimeoutError:
        pass

    oled.stop_refresh()
    stats = oled.get_stats()
    print("Termine. Frames:", stats['frames'])
    await oled.clear()
    oled.draw_text_large("OK!", 28, 52, 4, GREEN)
    await oled.show()

asyncio.run(main())
