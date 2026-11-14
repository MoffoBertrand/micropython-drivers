"""
lora_rx_async.py — Récepteur LoRa asyncio pour LILYGO T3S3 V1.2
================================================================
Auteur  : Prof. MOFFO LONLA Bertrand — Labo GIA / ENSP, Université de Douala
TP      : Communication LoRa Point-à-Point (SX1262 915 MHz) — version asyncio

Tâches parallèles :
  - rx_task()   : écoute en permanence les paquets LoRa
  - oled_task() : rafraîchit l'OLED toutes les 500 ms
  - stats_task(): affiche les statistiques toutes les 10 s

La réception bloquante (~timeout secondes) est remplacée par
un polling asyncio qui libère la boucle d'événements à chaque ms.
"""

import asyncio
import time
from machine import I2C, Pin
from sx1262_async import (SX1262Async, SF7, BW_125, CR_4_5,
                           LORA_PRIVATE_SYNCWORD)

# ─── Configuration ────────────────────────────────────────────────────────────
FREQ_HZ = 915_000_000
HDR_SIZE = 11

# ─── État partagé ─────────────────────────────────────────────────────────────
state = {
    "seq":      0,
    "rssi":     0.0,
    "snr":      0.0,
    "msg":      "En attente...",
    "nb_ok":    0,
    "nb_err":   0,
    "last_seq": -1,
}

# ─── Décodage paquet ──────────────────────────────────────────────────────────
def decode_packet(data):
    if len(data) < HDR_SIZE:
        return None
    try:
        if not isinstance(data, bytes):
            data = bytes(data)
        node_id = data[0]
        seq     = (data[1]<<24)|(data[2]<<16)|(data[3]<<8)|data[4]
        ts      = (data[5]<<24)|(data[6]<<16)|(data[7]<<8)|data[8]
        adc     = (data[9]<<8)|data[10]
        try:
            msg = data[HDR_SIZE:].decode("ascii")
        except Exception:
            msg = "".join(chr(b) if 32<=b<127 else "?" for b in data[HDR_SIZE:])
        return {"node": node_id, "seq": seq, "ts": ts, "adc": adc, "msg": msg}
    except Exception:
        return None

# ─── Tâche RX ─────────────────────────────────────────────────────────────────
async def rx_task(radio):
    """Écoute en permanence — non bloquante grâce à asyncio."""
    print("[RX] Tâche démarrée — en écoute...")
    while True:
        # Réception avec timeout 5s (non bloquante — yield toutes les 1ms)
        result = await radio.receive(timeout_ms=5000)

        if result is None:
            print("[RX] ... (rien reçu)")
            continue

        payload, rssi, snr = result
        pkt = decode_packet(payload)

        if pkt is None:
            state["nb_err"] += 1
            print(f"[RX] Décodage impossible (err={state['nb_err']})")
            continue

        state["nb_ok"]  += 1
        state["rssi"]    = rssi
        state["snr"]     = snr
        state["msg"]     = pkt["msg"]
        state["seq"]     = pkt["seq"]

        # Paquets manqués
        if state["last_seq"] >= 0:
            manques = pkt["seq"] - state["last_seq"] - 1
            if manques > 0:
                print(f"     ⚠  {manques} paquet(s) manqué(s)")
        state["last_seq"] = pkt["seq"]

        print(f"[RX #{pkt['seq']:4d}] "
              f"Node={pkt['node']:02X}h  "
              f"RSSI={rssi:+.1f} dBm  "
              f"SNR={snr:+.1f} dB  "
              f"\"{pkt['msg']}\"")

        # Laisser les autres tâches s'exécuter
        await asyncio.sleep_ms(0)

# ─── Tâche OLED ───────────────────────────────────────────────────────────────
async def oled_task(oled):
    """Rafraîchit l'OLED toutes les 500 ms — indépendamment du RX."""
    if oled is None:
        return
    print("[OLED] Tâche démarrée")
    while True:
        try:
            oled.fill(0)
            oled.text("T3S3 LoRa RX", 0, 0)
            oled.hline(0, 10, 128, 1)
            oled.text(f"Seq : {state['seq']:5d}", 0, 14)
            oled.text(f"RSSI:{state['rssi']:+.0f} SNR:{state['snr']:+.0f}", 0, 24)
            oled.text(state["msg"][:16], 0, 34)
            oled.text(f"OK:{state['nb_ok']:4d} Err:{state['nb_err']:3d}", 0, 44)
            # Barre signal RSSI (-120 → -40 dBm = 0 → 100%)
            bar = max(0, min(128, int((state["rssi"] + 120) * 128 / 80)))
            oled.fill_rect(0, 56, bar, 7, 1)
            oled.rect(0, 56, 128, 7, 1)
            oled.show()
        except Exception as e:
            print(f"[OLED] erreur : {e}")
        await asyncio.sleep_ms(500)

# ─── Tâche statistiques ───────────────────────────────────────────────────────
async def stats_task():
    """Affiche les statistiques de réception toutes les 30 s."""
    while True:
        await asyncio.sleep(30)
        total = state["nb_ok"] + state["nb_err"]
        taux  = state["nb_ok"] / total * 100 if total > 0 else 0
        print(f"\n[STATS] Reçus={state['nb_ok']}  Err={state['nb_err']}  "
              f"Taux={taux:.1f}%  "
              f"Dernier RSSI={state['rssi']:+.1f} dBm  "
              f"SNR={state['snr']:+.1f} dB\n")

# ─── Main ─────────────────────────────────────────────────────────────────────
async def main():
    print("=" * 50)
    print("  T3S3 V1.2 — LoRa RX asyncio (SX1262 915 MHz)")
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
        tx_power  = 14,
        sync_word = LORA_PRIVATE_SYNCWORD,
        crc       = True
    )
    if not ok:
        print("[RADIO] ERREUR : initialisation échouée !")
        return
    print(f"[RADIO] {radio}")

    # Lancer les tâches
    asyncio.create_task(rx_task(radio))
    asyncio.create_task(oled_task(oled))
    asyncio.create_task(stats_task())

    while True:
        await asyncio.sleep(1)

# ─── Lancement ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    asyncio.run(main())
