"""
async_exemple_01_base.py — SSD1351Async RGB OLED 1.5" (128x128)
Exemple Async 1 : Trois modes d'utilisation
  Mode A : await show() manuel
  Mode B : start_refresh() + mark_dirty()
  Mode C : show_sync() hors asyncio
"""
import uasyncio as asyncio
from ssd1351_async import (SSD1351Async, color565, hsv_to_rgb565,
                            BLACK, WHITE, RED, GREEN, BLUE,
                            YELLOW, CYAN, MAGENTA, ORANGE, GRAY)

# ── MODE A : await show() manuel ─────────────────────────────────────────────
async def demo_mode_a(oled):
    print("Mode A : await show() explicite")
    colors = [(RED,"  ROUGE "), (GREEN,"  VERT  "),
              (BLUE,"  BLEU  "), (YELLOW," JAUNE  ")]
    for c, label in colors:
        oled.fill(c)
        oled.fill_rounded_rect(10, 45, 108, 38, 8, color565(0,0,0))
        oled.text("Mode A          ", 10, 55, WHITE)
        oled.text(label, 10, 67, WHITE)
        await oled.show()
        await asyncio.sleep_ms(700)

# ── MODE B : tache de refresh autonome ────────────────────────────────────────
async def demo_mode_b(oled):
    print("Mode B : start_refresh(30fps) + mark_dirty()")
    oled.start_refresh(fps=30)

    # Animation : roue HSV en temps reel
    for hue_off in range(0, 361, 3):
        oled.fill(BLACK)
        # Cercles concentriques HSV
        for r in range(55, 5, -8):
            c = hsv_to_rgb565(hue_off + r * 3, 1.0, 1.0)
            oled.fill_circle(64, 64, r, c)
        oled.fill_circle(64, 64, 12, BLACK)
        oled.text("Mode B    ", 24, 58, WHITE)
        oled.text("fps=30    ", 24, 70, GRAY)
        oled.mark_dirty()   # <- signal le rafraichissement
        await asyncio.sleep_ms(33)

    oled.stop_refresh()
    stats = oled.get_stats()
    print("  Stats :", stats)
    oled.reset_stats()

# ── MODE C : synchrone (sans asyncio) ─────────────────────────────────────────
def demo_mode_c(oled):
    print("Mode C : show_sync() bloquant")
    import time
    for i in range(4):
        hue = i * 90
        c   = hsv_to_rgb565(hue, 1.0, 1.0)
        oled.fill(c)
        oled.draw_rounded_rect(10, 45, 108, 38, 8, BLACK)
        oled.text("Mode C   sync   ", 10, 55, BLACK)
        oled.text("Hue={:3d}        ".format(hue), 10, 67, BLACK)
        oled.show_sync()
        time.sleep_ms(700)

# ── MAIN ──────────────────────────────────────────────────────────────────────
async def main():
    oled = SSD1351Async()
    await oled.init()
    print(oled)

    await demo_mode_a(oled)
    await demo_mode_b(oled)
    demo_mode_c(oled)

    await oled.clear()
    oled.draw_rounded_rect(4, 4, 120, 120, 12, GREEN)
    oled.text("Async 1  OK !   ", 8, 60, WHITE)
    await oled.show()
    print("Exemple async 1 termine.")

asyncio.run(main())
