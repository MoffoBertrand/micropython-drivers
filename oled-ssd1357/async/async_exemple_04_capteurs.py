"""
async_exemple_04_capteurs.py
=========================================================
Exemple Async 4 — Acquisition multi-capteurs concurrente
  Tache affichage : dashboard mis a jour en continu
  Tache ADC      : echantillonnage a 100 Hz
  Tache TEMP     : temperature MCU toutes les 1 s
  Tache UART     : envoi donnees serie toutes les 2 s

Les donnees capteurs sont echangees via des objets
SharedData (sans lock — tableaux a index unique par tache).
=========================================================
"""
import uasyncio as asyncio
import esp32, math
from machine import ADC, Pin, UART
from ssd1357_async import (SSD1357Async, color565,
                            BLACK, WHITE, RED, GREEN, BLUE,
                            YELLOW, CYAN, GRAY)

# ── Donnees partagees entre taches ────────────────────────────────────────────
class SharedData:
    """Buffer circulaire partage entre taches producteur/consommateur."""
    def __init__(self, size=64):
        self.adc_buf  = [0.0] * size   # historique ADC (volts)
        self.adc_idx  = 0
        self.adc_last = 0.0
        self.temp     = 25.0
        self.frame    = 0

data = SharedData(64)

# ── Tache ADC : echantillonnage 100 Hz ────────────────────────────────────────
async def tache_adc():
    """
    Echantillonne l'ADC GPIO4 a 100 Hz (periode 10 ms).
    Stocke dans le buffer circulaire data.adc_buf.
    """
    adc = ADC(Pin(4))
    adc.atten(ADC.ATTN_11DB)
    adc.width(ADC.WIDTH_12BIT)
    while True:
        raw = adc.read()
        volts = raw * 3.3 / 4095
        data.adc_buf[data.adc_idx % len(data.adc_buf)] = volts
        data.adc_idx += 1
        data.adc_last = volts
        await asyncio.sleep_ms(10)   # 100 Hz

# ── Tache temperature : toutes les 1 s ────────────────────────────────────────
async def tache_temp():
    while True:
        data.temp = esp32.mcu_temperature()
        await asyncio.sleep_ms(1000)

# ── Tache UART : envoi des donnees serie toutes les 2 s ──────────────────────
async def tache_uart():
    """Envoie les donnees en JSON sur UART0 pour logging externe."""
    try:
        uart = UART(0, baudrate=115200)
        while True:
            msg = '{{"t":{:.1f},"v":{:.3f},"f":{}}}\r\n'.format(
                  data.temp, data.adc_last, data.frame)
            uart.write(msg)
            await asyncio.sleep_ms(2000)
    except Exception as e:
        print("UART non disponible :", e)
        while True:
            await asyncio.sleep_ms(2000)

# ── Tache affichage : dashboard temps reel ────────────────────────────────────
async def tache_affichage(oled):
    """
    Affiche un dashboard avec :
    - Graphe ADC (historique 64 pts)
    - Temperature MCU
    - Compteur de frames
    """
    W, H = oled.width, oled.height   # 64, 128
    GRAPH_H = 50
    GRAPH_Y = 50

    while True:
        oled.fill(BLACK)

        # ── Titre ─────────────────────────────────────────────────────────
        oled.fill_rect(0, 0, W, 14, color565(0, 40, 80))
        oled.text("SENSORS ", 0, 3, WHITE)

        # ── Temperature ───────────────────────────────────────────────────
        t = data.temp
        col_t = RED if t > 60 else YELLOW if t > 45 else GREEN
        oled.text("T:", 0, 16, CYAN)
        oled.text("{:.1f}C ".format(t), 16, 16, col_t)

        # ── Valeur ADC instantanee ────────────────────────────────────────
        oled.text("V:", 0, 28, CYAN)
        oled.text("{:.2f}V".format(data.adc_last), 16, 28, WHITE)

        # ── Frame count ───────────────────────────────────────────────────
        data.frame += 1
        oled.text("F:{:5d}".format(data.frame), 0, 40, GRAY)

        # ── Graphe ADC (historique) ────────────────────────────────────────
        oled.rect(0, GRAPH_Y, W, GRAPH_H, GRAY)
        # Axe 1.65V (milieu 0-3.3V)
        oled.hline(1, GRAPH_Y + GRAPH_H//2, W-2, color565(30,30,30))

        n = len(data.adc_buf)
        idx_start = data.adc_idx  # index courant = point le plus recent
        prev_y = None
        for px in range(W - 2):
            # Lire les n derniers points dans l'ordre chronologique
            buf_idx = (idx_start - (W-2) + px) % n
            v = data.adc_buf[buf_idx]
            py = GRAPH_Y + GRAPH_H - 2 - int(v / 3.3 * (GRAPH_H - 4))
            py = max(GRAPH_Y+1, min(GRAPH_Y + GRAPH_H - 2, py))
            if prev_y is not None:
                # Couleur selon valeur : rouge si haut, vert si bas
                gc = color565(
                    int(v/3.3 * 255),
                    int((1-v/3.3) * 200),
                    0
                )
                oled.line(px, prev_y, px+1, py, gc)
            prev_y = py

        # ── Echelle ADC ────────────────────────────────────────────────────
        oled.text("3.3V", 36, GRAPH_Y + 1, GRAY)
        oled.text("0.0V", 36, GRAPH_Y + GRAPH_H - 10, GRAY)

        oled.mark_dirty()
        await asyncio.sleep_ms(40)   # 25 fps affichage

# ── MAIN ──────────────────────────────────────────────────────────────────────
async def main():
    oled = SSD1357Async()
    await oled.init()
    oled.start_refresh(fps=25)
    print("Dashboard multi-capteurs demarre.")
    print("  ADC    GPIO4 @ 100 Hz")
    print("  Temp   MCU   @ 1 Hz")
    print("  UART   log   @ 0.5 Hz")
    print("  Ecran         @ 25 fps")
    print("Duree : 60 secondes")

    try:
        await asyncio.wait_for(
            asyncio.gather(
                tache_adc(),
                tache_temp(),
                tache_uart(),
                tache_affichage(oled),
            ),
            60
        )
    except asyncio.TimeoutError:
        pass

    oled.stop_refresh()
    print("Termine. Frames :", data.frame)
    await oled.clear()
    oled.text("Done!   ", 8, 56, GREEN)
    await oled.show()

asyncio.run(main())
