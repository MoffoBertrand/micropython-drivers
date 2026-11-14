"""
async_exemple_03_sprites.py — SSD1351Async RGB OLED 1.5"
Exemple Async 3 : Systeme de sprites et animations async
  Demo 1 : Sprites independants (balles, rectangles, pixels)
  Demo 2 : draw_colorwheel_async (non bloquant)
  Demo 3 : plasma_async (non bloquant)
  Demo 4 : bounce_ball_async (non bloquant)
  Demo 5 : scroll_text_async en parallele avec animation
  Demo 6 : fade_in/fade_out async
"""
import uasyncio as asyncio
import random
from ssd1351_async import (SSD1351Async, Sprite, color565, hsv_to_rgb565,
                            BLACK, WHITE, RED, GREEN, BLUE,
                            YELLOW, CYAN, MAGENTA, ORANGE, GRAY)

# ── Demo 1 : Sprites autonomes ────────────────────────────────────────────────
async def demo_sprites(oled):
    print("Demo 1 : Sprites")
    oled.fill(BLACK); await oled.show()
    sm = oled.sprites

    # 5 balles colorees
    for i in range(5):
        sm.add(Sprite(
            x=random.randint(15,113), y=random.randint(15,113),
            vx=random.uniform(-2.5,2.5), vy=random.uniform(-2.5,2.5),
            color=hsv_to_rgb565(i*72, 1.0, 1.0),
            radius=random.randint(6,14), shape='circle',
            bounce=True
        ))

    # 3 rectangles
    for i in range(3):
        sm.add(Sprite(
            x=random.randint(0,100), y=random.randint(0,100),
            vx=random.uniform(-1.5,1.5), vy=random.uniform(-1.5,1.5),
            color=hsv_to_rgb565(i*120+40, 0.8, 1.0),
            w=18, h=10, shape='rect', bounce=True
        ))

    # 20 pixels rapides
    for _ in range(20):
        sm.add(Sprite(
            x=random.randint(0,127), y=random.randint(0,127),
            vx=random.uniform(-3,3), vy=random.uniform(-3,3),
            color=WHITE, shape='pixel', wrap=True
        ))

    for frame in range(250):
        sm.update_all()
        sm.draw_all(erase_color=BLACK)
        oled.mark_dirty()
        await asyncio.sleep_ms(20)

    sm.clear()
    await oled.clear()

# ── Demo 2 : Roue chromatique async ───────────────────────────────────────────
async def demo_colorwheel(oled):
    print("Demo 2 : Roue chromatique async")
    oled.fill(BLACK)
    oled.text("Roue HSV async  ", 0, 0, WHITE)
    await oled.show()
    # La roue se dessine progressivement sans bloquer
    await oled.draw_colorwheel_async(64, 64, 60, 0)
    await oled.show()
    await asyncio.sleep_ms(1500)

    # Version annulaire
    oled.fill(BLACK)
    oled.text("Anneau HSV      ", 0, 0, WHITE)
    await oled.draw_colorwheel_async(64, 64, 60, 25)
    oled.fill_circle(64, 64, 24, BLACK)
    oled.text(" OLED ", 36, 58, WHITE)
    await oled.show()
    await asyncio.sleep_ms(2000)

# ── Demo 3 : Plasma async ─────────────────────────────────────────────────────
async def demo_plasma(oled):
    print("Demo 3 : Plasma async")
    await oled.plasma_async(frames=60, delay_ms=15)

# ── Demo 4 : Balle rebondissante async ────────────────────────────────────────
async def demo_bounce(oled):
    print("Demo 4 : Balle async")
    oled.fill(BLACK); await oled.show()
    await oled.bounce_ball_async(
        color=color565(255,140,0), r=14, frames=200, delay_ms=16)

# ── Demo 5 : Scroll + animation en parallele ──────────────────────────────────
async def demo_scroll_parallele(oled):
    print("Demo 5 : Scroll + animation parallele")
    oled.start_refresh(fps=25)

    import math

    async def animation_fond():
        """Cercles concentriques animes en fond."""
        phase = 0
        for _ in range(120):
            oled.fill_rect(0, 16, 128, 96, BLACK)
            for r in range(45, 5, -8):
                hue = (phase * 3 + r * 5) % 360
                oled.fill_circle(64, 62, r, hsv_to_rgb565(hue, 1.0, 1.0))
            oled.fill_circle(64, 62, 10, BLACK)
            phase += 3
            oled.mark_dirty()
            await asyncio.sleep_ms(40)

    async def scroll_ligne1():
        await oled.scroll_text_async(
            "  SSD1351 Async -- RGB OLED 1.5 pouces -- 128x128 px  ",
            4, WHITE, color565(0,20,40), delay_ms=45)

    async def scroll_ligne2():
        await asyncio.sleep_ms(500)   # decalage
        await oled.scroll_text_async(
            "  Prof. MOFFO LONLA Bertrand -- UB COT / Labo GIA Douala  ",
            116, CYAN, BLACK, delay_ms=45)

    await asyncio.gather(animation_fond(), scroll_ligne1(), scroll_ligne2())
    oled.stop_refresh()

# ── Demo 6 : Fade in / Fade out async ─────────────────────────────────────────
async def demo_fade(oled):
    print("Demo 6 : Fade in/out async")
    oled.fill(BLACK)
    oled.gradient_fill(0, 0, 128, 128, RED, BLUE)
    oled.draw_rounded_rect(14, 44, 100, 40, 8, WHITE)
    oled.text("  Fade  async   ", 14, 56, WHITE)
    oled.text("  in  /  out    ", 14, 68, WHITE)
    oled.set_master_contrast(0)
    await oled.show()

    await oled.fade_in_async(steps=15, delay_ms=40)
    await asyncio.sleep_ms(1000)
    await oled.fade_out_async(steps=15, delay_ms=40)
    await asyncio.sleep_ms(500)

# ── MAIN ──────────────────────────────────────────────────────────────────────
async def main():
    oled = SSD1351Async()
    await oled.init()
    print(oled)

    await demo_sprites(oled)
    await demo_colorwheel(oled)
    await demo_plasma(oled)
    await demo_bounce(oled)
    await demo_scroll_parallele(oled)
    await demo_fade(oled)

    await oled.clear()
    oled.draw_text_large("OK!", 28, 52, 4, GREEN)
    await oled.show()
    print("Exemple async 3 termine.")

asyncio.run(main())
