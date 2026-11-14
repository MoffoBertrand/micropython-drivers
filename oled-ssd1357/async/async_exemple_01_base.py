"""
async_exemple_01_base.py
=========================================================
Exemple Async 1 — Utilisation de base : init, show, clear
Demontre les 3 modes d'utilisation :
  Mode A : await show()  (dans une coroutine)
  Mode B : mark_dirty() + start_refresh()  (tache autonome)
  Mode C : show_sync()  (sans boucle asyncio)
=========================================================
"""
import uasyncio as asyncio
from ssd1357_async import SSD1357Async, BLACK, WHITE, RED, GREEN, BLUE, YELLOW, CYAN

# ── MODE A : await show() manuel ─────────────────────────────────────────────
async def demo_mode_a(oled):
    """Appel explicite a await show() apres chaque scene."""
    print("Mode A : await show() manuel")
    for color, label in [(RED,"ROUGE"), (GREEN,"VERT"), (BLUE,"BLEU")]:
        oled.fill(color)
        oled.text(label,  16, 56, WHITE)
        oled.text("Mode A",  8, 72, WHITE)
        await oled.show()
        await asyncio.sleep_ms(800)

# ── MODE B : tache de refresh autonome ────────────────────────────────────────
async def demo_mode_b(oled):
    """
    start_refresh() + mark_dirty() :
    la tache de refresh surveille le signal dirty et pousse
    le buffer automatiquement a la frequence demandee.
    """
    print("Mode B : start_refresh + mark_dirty")
    oled.start_refresh(fps=25)

    for i in range(60):
        oled.fill(BLACK)
        oled.fill_rect(0, 0, 64, 14, GREEN)
        oled.text("Mode B  ", 0, 3, BLACK)
        oled.text("fps=25  ", 0, 20, WHITE)
        oled.text("frame {:3d}".format(i), 0, 36, CYAN)
        oled.fill_circle(32, 90, 18, RED)
        oled.draw_circle(32, 90, 18 - i % 10, YELLOW)
        oled.mark_dirty()             # <- signale la frame prete
        await asyncio.sleep_ms(40)

    oled.stop_refresh()
    print("  Frames affichees :", oled.get_frame_count())
    oled.reset_frame_count()

# ── MODE C : show_sync() hors asyncio ─────────────────────────────────────────
def demo_mode_c_sync(oled):
    """Usage synchrone — compatible avec du code non-async."""
    print("Mode C : show_sync()")
    import time
    for c, label in [(0xF800,"ROUGE"), (0x07E0,"VERT"), (0x001F,"BLEU")]:
        oled.fill(c)
        oled.text(label,  16, 56, WHITE)
        oled.text("Sync !", 12, 72, WHITE)
        oled.show_sync()              # bloquant
        time.sleep_ms(600)

# ── MAIN ──────────────────────────────────────────────────────────────────────
async def main():
    oled = SSD1357Async()
    await oled.init()
    print(oled)

    await demo_mode_a(oled)
    await demo_mode_b(oled)

    # Mode C appele depuis une coroutine (bloquant mais court)
    demo_mode_c_sync(oled)

    await oled.clear()
    oled.text("Async OK", 0, 56, GREEN)
    await oled.show()
    print("Exemple async 1 termine.")

asyncio.run(main())
