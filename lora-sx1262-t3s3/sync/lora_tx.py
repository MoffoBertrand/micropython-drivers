"""
lora_tx.py — Emetteur LoRa pour LILYGO T3S3 V1.2
==================================================
Auteur  : Prof. MOFFO LONLA Bertrand — Labo GIA / ENSP, Université de Douala
TP      : Communication LoRa Point-à-Point (SX1262 915 MHz)
Module  : LILYGO T3-S3 V1.2

Description :
    Envoie un paquet LoRa toutes les 2 secondes avec :
      - un compteur de séquence
      - un horodatage (ms depuis démarrage)
      - une valeur d'ADC simulée (température)

Prérequis :
    - sx1262.py copié sur la carte (même répertoire)
    - ssd1306.py ou bibliothèque OLED disponible (optionnel)
"""

import time
import struct
from machine import I2C, Pin
from sx1262 import SX1262, SF7, BW_125, CR_4_5, LORA_PRIVATE_SYNCWORD

# ─── Configuration ───────────────────────────────────────────────────────────

FREQ_HZ    = 915_000_000   # 915 MHz — bande AU915 / US915
TX_POWER   = 14            # dBm (max légal EU = 14 dBm EIRP)
SEND_EVERY = 2000          # intervalle entre deux envois (ms)
NODE_ID    = 0x01          # identifiant de ce nœud émetteur

# ─── LED embarquée ───────────────────────────────────────────────────────────
# ATTENTION T3S3 V1.2 : GPIO37 = FSPI_Q (MISO LoRa) — PAS de LED utilisateur !
# La LED est désactivée pour éviter tout conflit matériel.

def blink(n=1, ms=80):
    pass   # Pas de LED disponible sur T3S3 V1.2 sans conflit

# ─── OLED (optionnel) ─────────────────────────────────────────────────────────

def init_oled():
    try:
        import ssd1306
        i2c = I2C(0, scl=Pin(17), sda=Pin(18), freq=400_000)
        oled = ssd1306.SSD1306_I2C(128, 64, i2c, addr=0x3C)
        return oled
    except Exception as e:
        print(f"[OLED] Non disponible : {e}")
        return None

def oled_show(oled, seq, status, rssi_info=""):
    if oled is None:
        return
    oled.fill(0)
    oled.text("T3S3 LoRa TX", 0, 0)
    oled.hline(0, 10, 128, 1)
    oled.text(f"Seq : {seq:5d}", 0, 14)
    oled.text(f"Freq: 915 MHz", 0, 24)
    oled.text(f"SF7/BW125/CR45", 0, 34)
    oled.text(f"Pwr : {TX_POWER} dBm", 0, 44)
    oled.text(status[:21], 0, 54)
    oled.show()

# ─── Format de paquet ─────────────────────────────────────────────────────────
#
#  Octet 0     : NODE_ID        (1 octet)
#  Octets 1-4  : numéro séquence (uint32 big-endian)
#  Octets 5-8  : timestamp ms   (uint32 big-endian)
#  Octets 9-10 : valeur ADC     (uint16 big-endian — simulée)
#  Octets 11+  : message ASCII  (variable)
#
MSG_TEMPLATE = "Hello from T3S3 node {:d} !"

def build_packet(seq):
    """
    Construit un paquet LoRa.
    En-tête manuel (évite les problèmes d'alignement struct sur MicroPython) :
      [0]    : NODE_ID  (1 octet)
      [1-4]  : SEQ      (uint32 big-endian)
      [5-8]  : TS       (uint32 big-endian)
      [9-10] : ADC      (uint16 big-endian)
      [11+]  : MESSAGE  (ASCII)
    """
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

# ─── Programme principal ──────────────────────────────────────────────────────

def main():
    print("=" * 48)
    print("  LILYGO T3S3 V1.2 — LoRa Emetteur (SX1262)")
    print("=" * 48)

    # Initialisation OLED
    oled = init_oled()
    if oled:
        oled.fill(0)
        oled.text("Init LoRa...", 0, 0)
        oled.show()

    # Initialisation radio
    print("[RADIO] Initialisation SX1262...")
    radio = SX1262()   # broches par défaut T3S3 V1.2
    ok = radio.begin(
        freq      = FREQ_HZ,
        sf        = SF7,
        bw        = BW_125,
        cr        = CR_4_5,
        tx_power  = TX_POWER,
        sync_word = LORA_PRIVATE_SYNCWORD,
        crc       = True
    )
    if not ok:
        print("[RADIO] ERREUR : initialisation SX1262 échouée !")
        blink(10, 200)
        return

    print(f"[RADIO] {radio}")
    blink(3, 100)

    seq = 0
    t_last_send = time.ticks_ms() - SEND_EVERY   # envoyer immédiatement

    print("[TX] Démarrage des émissions...")
    print(f"     Intervalle = {SEND_EVERY} ms")
    print("-" * 48)

    while True:
        now = time.ticks_ms()

        if time.ticks_diff(now, t_last_send) >= SEND_EVERY:
            seq += 1
            pkt = build_packet(seq)

            print(f"[TX #{seq:4d}] Envoi {len(pkt)} octets...", end="")
            t0  = time.ticks_ms()
            ok  = radio.transmit(pkt, timeout_ms=3000)
            dt  = time.ticks_diff(time.ticks_ms(), t0)

            if ok:
                status = f"OK  ({dt} ms)"
                print(f" {status}")
            else:
                status = "TIMEOUT !"
                print(f" {status}")
                blink(2, 50)

            oled_show(oled, seq, status)
            t_last_send = time.ticks_ms()

        time.sleep_ms(10)

# ─── Lancement ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    main()
