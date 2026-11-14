"""
async_exemple_02_multitaches.py
=========================================================
Exemple Async 2 — Multitaches concurrent :
  Tache 1 : animation OLED (balle rebondissante)
  Tache 2 : lecture temperature MCU toutes les 500 ms
  Tache 3 : clignotement LED GPIO (independant de l'ecran)
  Tache 4 : watchdog console (affiche stats toutes les 5 s)

Montre que l'ecran tourne a 25 fps sans bloquer les autres
taches grace a uasyncio.
=========================================================
"""
import uasyncio as asyncio
import esp32
import math
from machine import Pin
from ssd1357_async import (SSD1357Async, color565,
                            BLACK, WHITE, RED, GREEN, BLUE,
                            YELLOW, CYAN, GRAY, ORANGE)

# ── Tache 1 : Animation OLED ──────────────────────────────────────────────────
async def tache_oled(oled, temp_ref):
    """
    Balle rebondissante + affichage temperature en temps reel.
    Utilise mark_dirty() -> la tache de refresh pousse a 25 fps.
    """
    bx, by = 20.0, 60.0
    vx, vy = 1.6, 2.1
    R = 7
    W, H = oled.width, oled.height

    while True:
        # Mise a jour physique
        bx += vx; by += vy
        if bx <= R or bx >= W - R: vx = -vx; bx = max(R, min(W-R, bx))
        if by <= R or by >= H - R: vy = -vy; by = max(R, min(H-R, by))

        # Dessin de la scene
        oled.fill(BLACK)
        # Barre titre
        oled.fill_rect(0, 0, 64, 12, color565(0, 40, 80))
        oled.text("T={:.1f}C".format(temp_ref[0]), 0, 2, WHITE)
        # Balle
        oled.fill_circle(int(bx), int(by), R, color565(255, 140, 0))
        oled.draw_circle(int(bx), int(by), R, WHITE)
        # Trace de trajectoire (effet sillage)
        for i in range(1, 4):
            tx = int(bx - vx * i * 3)
            ty = int(by - vy * i * 3)
            if 0 <= tx < W and 0 <= ty < H:
                oled.fill_circle(tx, ty, max(1, R - i*2),
                                 color565(80-i*20, 50-i*10, 0))
        oled.mark_dirty()      # signale la frame prete
        await asyncio.sleep_ms(40)   # ~25 fps

# ── Tache 2 : Lecture capteur temperature ─────────────────────────────────────
async def tache_capteur(temp_ref):
    """Lit la temperature MCU toutes les 500 ms et met a jour temp_ref[0]."""
    while True:
        temp_ref[0] = esp32.mcu_temperature()
        await asyncio.sleep_ms(500)

# ── Tache 3 : Clignotement LED (GPIO independant) ─────────────────────────────
async def tache_led(pin_num=2):
    """Fait clignoter une LED sans interrompre l'affichage."""
    try:
        led = Pin(pin_num, Pin.OUT)
        while True:
            led(1); await asyncio.sleep_ms(100)
            led(0); await asyncio.sleep_ms(900)
    except Exception:
        # Si la broche n'existe pas ou est deja utilisee
        while True:
            await asyncio.sleep_ms(1000)

# ── Tache 4 : Watchdog console ────────────────────────────────────────────────
async def tache_watchdog(oled, temp_ref):
    """Affiche des statistiques dans la console toutes les 5 secondes."""
    import time
    t0 = time.ticks_ms()
    while True:
        await asyncio.sleep_ms(5000)
        elapsed = time.ticks_diff(time.ticks_ms(), t0) / 1000
        fps_reel = oled.get_frame_count() / elapsed if elapsed > 0 else 0
        print("[Watchdog] T={:.1f}C | Frames={} | FPS reel={:.1f}".format(
              temp_ref[0], oled.get_frame_count(), fps_reel))

# ── MAIN ──────────────────────────────────────────────────────────────────────
async def main():
    oled = SSD1357Async()
    await oled.init()
    oled.start_refresh(fps=25)
    print("Demarrage multitaches...")
    print("  Tache 1 : animation OLED")
    print("  Tache 2 : temperature MCU")
    print("  Tache 3 : LED clignotante")
    print("  Tache 4 : watchdog console")

    temp_ref = [25.0]   # reference partagee entre taches

    # Lancer toutes les taches en parallele (duree 30 secondes)
    try:
        await asyncio.wait_for(
            asyncio.gather(
                tache_oled(oled, temp_ref),
                tache_capteur(temp_ref),
                tache_led(2),
                tache_watchdog(oled, temp_ref),
            ),
            30   # timeout 30 secondes
        )
    except asyncio.TimeoutError:
        pass

    oled.stop_refresh()
    print("Termine. Frames totales :", oled.get_frame_count())
    await oled.clear()
    oled.text("Async OK", 0, 56, GREEN)
    await oled.show()

asyncio.run(main())
