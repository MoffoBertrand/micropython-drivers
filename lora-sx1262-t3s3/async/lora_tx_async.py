"""
lora_tx_async.py — Emetteur LoRa asyncio pour LILYGO T3S3 V1.2
===============================================================
Auteur  : Prof. MOFFO LONLA Bertrand — Labo GIA / ENSP, Université de Douala
TP      : Communication LoRa Point-à-Point (SX1262 915 MHz) — version asyncio

Tâches parallèles :
  - tx_task()   : envoie un paquet toutes les 2 s (non bloquant)
  - oled_task() : rafraîchit l'OLED toutes les 500 ms
  - led_task()  : clignote à chaque TX (si LED disponible)

Avantage vs version synchrone : pendant les ~83 ms de TX,
les autres tâches continuent de s'exécuter.
"""

import asyncio
import time
from machine import I2C, Pin
from sx1262_async import (SX1262Async, SF7, BW_125, CR_4_5,
                           LORA_PRIVATE_SYNCWORD)

# ─── Configuration ────────────────────────────────────────────────────────────
FREQ_HZ    = 915_000_000
TX_POWER   = 14
SEND_EVERY = 2000   # ms
NODE_ID    = 0x01
MSG_TEMPLATE = "Hello from T3S3 node {:d} !"

# ─── État partagé entre les tâches ───────────────────────────────────────────
state = {
    "seq":    0,
    "status": "Démarrage...",
    "ok":     False,
    "dt":     0,
}

# ─── Format de paquet ─────────────────────────────────────────────────────────
def build_packet(seq):
    ts  = time.ticks_ms() & 0xFFFFFFFF
    adc = (seq * 17 + 2048) & 0xFFFF
    msg = MSG_TEMPLATE.format(NODE_ID).encode()
    hdr = bytes([
        NODE_ID & 0xFF,
        (seq >> 24) & 0xFF, (seq >> 16) & 0xFF,
        (seq >>  8) & 0xFF,  seq        & 0xFF,
        (ts  >> 24) & 0xFF, (ts  >> 16) & 0xFF,
        (ts  >>  8) & 0xFF,  ts         & 0xFF,
        (adc >>  8) & 0xFF,  adc        & 0xFF,
    ])
    return hdr + msg

# ─── Tâche TX ─────────────────────────────────────────────────────────────────
async def tx_task(radio):
    """Envoie un paquet toutes les SEND_EVERY ms."""
    print("[TX] Tâche démarrée")
    while True:
        state["seq"] += 1
        pkt = build_packet(state["seq"])

        t0 = time.ticks_ms()
        ok = await radio.transmit(pkt, timeout_ms=3000)
        dt = time.ticks_diff(time.ticks_ms(), t0)

        state["ok"]  = ok
        state["dt"]  = dt
        state["status"] = f"OK ({dt}ms)" if ok else "TIMEOUT"

        print(f"[TX #{state['seq']:4d}] {len(pkt)} octets... {state['status']}")

        # Attente non bloquante entre deux TX
        await asyncio.sleep_ms(SEND_EVERY)

# ─── Tâche OLED ───────────────────────────────────────────────────────────────
async def oled_task(oled):
    """Rafraîchit l'OLED toutes les 500 ms — indépendamment du TX."""
    if oled is None:
        return
    print("[OLED] Tâche démarrée")
    while True:
        try:
            oled.fill(0)
            oled.text("T3S3 LoRa TX", 0, 0)
            oled.hline(0, 10, 128, 1)
            oled.text(f"Seq : {state['seq']:5d}", 0, 14)
            oled.text(f"915 MHz SF7", 0, 24)
            oled.text(f"Pwr : {TX_POWER} dBm", 0, 34)
            oled.text(state["status"][:21], 0, 44)
            oled.text(f"dt  : {state['dt']} ms", 0, 54)
            oled.show()
        except Exception as e:
            print(f"[OLED] erreur : {e}")
        await asyncio.sleep_ms(500)

# ─── Tâche watchdog console ────────────────────────────────────────────────────
async def watchdog_task():
    """Affiche un heartbeat toutes les 10 s pour confirmer que la boucle tourne."""
    while True:
        await asyncio.sleep(10)
        print(f"[WDG] en vie — seq={state['seq']} heap libre : ", end="")
        try:
            import gc; gc.collect()
            import micropython
            micropython.mem_info()
        except Exception:
            print("N/A")

# ─── Main ─────────────────────────────────────────────────────────────────────
async def main():
    print("=" * 50)
    print("  T3S3 V1.2 — LoRa TX asyncio (SX1262 915 MHz)")
    print("=" * 50)

    # OLED
    oled = None
    try:
        import ssd1306
        i2c = I2C(0, scl=Pin(17), sda=Pin(18), freq=400_000)
        oled = ssd1306.SSD1306_I2C(128, 64, i2c, addr=0x3C)
        oled.fill(0); oled.text("Init LoRa...", 0, 0); oled.show()
        print("[OLED] OK")
    except Exception as e:
        print(f"[OLED] Non disponible : {e}")

    # Radio
    print("[RADIO] Initialisation SX1262...")
    radio = SX1262Async()
    ok = await radio.begin(
        freq      = FREQ_HZ,
        sf        = SF7,
        bw        = BW_125,
        cr        = CR_4_5,
        tx_power  = TX_POWER,
        sync_word = LORA_PRIVATE_SYNCWORD,
        crc       = True
    )
    if not ok:
        print("[RADIO] ERREUR : initialisation échouée !")
        return
    print(f"[RADIO] {radio}")

    # Lancer les tâches en parallèle
    asyncio.create_task(tx_task(radio))
    asyncio.create_task(oled_task(oled))
    asyncio.create_task(watchdog_task())

    # Boucle principale — garde la boucle d'événements active
    while True:
        await asyncio.sleep(1)

# ─── Lancement ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    asyncio.run(main())
