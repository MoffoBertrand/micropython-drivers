"""
lora_rx.py — Récepteur LoRa pour LILYGO T3S3 V1.2
===================================================
Auteur  : Prof. MOFFO LONLA Bertrand — Labo GIA / ENSP, Université de Douala
TP      : Communication LoRa Point-à-Point (SX1262 915 MHz)
Module  : LILYGO T3-S3 V1.2

Description :
    Écoute en permanence les paquets LoRa émis par lora_tx.py.
    Affiche sur la console et sur l'OLED :
      - numéro de séquence reçu
      - RSSI (dBm) et SNR (dB)
      - message texte extrait du paquet
      - statistiques (paquets reçus / erreurs)

Prérequis :
    - sx1262.py copié sur la carte (même répertoire)
"""

import time
import struct
from machine import Pin, I2C
from sx1262 import SX1262, SF7, BW_125, CR_4_5, LORA_PRIVATE_SYNCWORD

# ─── Configuration ───────────────────────────────────────────────────────────

FREQ_HZ  = 915_000_000   # doit être identique à l'émetteur

# ─── LED embarquée ───────────────────────────────────────────────────────────
# ATTENTION T3S3 V1.2 : GPIO37 = FSPI_Q (MISO LoRa) — PAS de LED utilisateur !
# La LED est désactivée pour éviter tout conflit matériel.

def blink(n=1, ms=80):
    pass   # Pas de LED disponible sur T3S3 V1.2 sans conflit

# ─── OLED ────────────────────────────────────────────────────────────────────

def init_oled():
    try:
        import ssd1306
        i2c = I2C(0, scl=Pin(17), sda=Pin(18), freq=400_000)
        oled = ssd1306.SSD1306_I2C(128, 64, i2c, addr=0x3C)
        return oled
    except Exception as e:
        print(f"[OLED] Non disponible : {e}")
        return None

def oled_show(oled, seq, rssi, snr, msg, nb_ok, nb_err):
    if oled is None:
        return
    oled.fill(0)
    oled.text("T3S3 LoRa RX", 0, 0)
    oled.hline(0, 10, 128, 1)
    oled.text(f"Seq : {seq:5d}", 0, 14)
    oled.text(f"RSSI:{rssi:+.0f} SNR:{snr:+.0f}", 0, 24)
    # Afficher les 16 premiers caractères du message
    oled.text(msg[:16], 0, 34)
    oled.text(f"OK:{nb_ok:4d} Err:{nb_err:3d}", 0, 44)
    # Barre signal (RSSI de -120 à -40 → 0 à 100%)
    bar = max(0, min(128, int((rssi + 120) * 128 / 80)))
    oled.fill_rect(0, 56, bar, 7, 1)
    oled.rect(0, 56, 128, 7, 1)
    oled.show()

# ─── Décodage du paquet ──────────────────────────────────────────────────────
#
#  Format (identique à lora_tx.py) :
#  Octet 0     : NODE_ID   (uint8)
#  Octets 1-4  : séquence  (uint32 big-endian)
#  Octets 5-8  : timestamp (uint32 big-endian)
#  Octets 9-10 : ADC       (uint16 big-endian)
#  Octets 11+  : message   (ASCII)

# En-tête fixe : B(1) + I(4) + I(4) + H(2) = 11 octets
# Sur MicroPython, struct.unpack_from sur bytearray peut échouer
# → toujours convertir en bytes avant unpack.
HDR_SIZE = 11

def decode_packet(data):
    """
    Décode un paquet LoRa reçu.
    Note : sur MicroPython, bytes.decode() ne supporte pas errors=
    → utiliser try/except à la place.
    """
    if len(data) < HDR_SIZE:
        return None
    try:
        # Forcer bytes (MicroPython peut retourner bytearray)
        if not isinstance(data, bytes):
            data = bytes(data)
        # Décomposition manuelle big-endian (évite struct sur MicroPython)
        node_id = data[0]
        seq     = (data[1] << 24) | (data[2] << 16) | (data[3] << 8) | data[4]
        ts      = (data[5] << 24) | (data[6] << 16) | (data[7] << 8) | data[8]
        adc     = (data[9] << 8)  |  data[10]
        # decode() sans paramètre errors= (non supporté sur MicroPython)
        try:
            msg = data[HDR_SIZE:].decode("ascii")
        except Exception:
            msg = "".join(chr(b) if 32 <= b < 127 else "?" for b in data[HDR_SIZE:])
        return {"node": node_id, "seq": seq, "ts": ts, "adc": adc, "msg": msg}
    except Exception as e:
        return None

# ─── Programme principal ──────────────────────────────────────────────────────

def main():
    print("=" * 48)
    print(" LILYGO T3S3 V1.2 — LoRa Récepteur (SX1262)")
    print("=" * 48)

    oled = init_oled()
    if oled:
        oled.fill(0)
        oled.text("Init LoRa...", 0, 0)
        oled.show()

    print("[RADIO] Initialisation SX1262...")
    radio = SX1262()
    ok = radio.begin(
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
        blink(10, 200)
        return

    print(f"[RADIO] {radio}")
    blink(3, 100)

    # Statistiques
    nb_ok    = 0
    nb_err   = 0
    last_seq = -1

    # Affichage OLED initial
    if oled:
        oled.fill(0)
        oled.text("En attente...", 0, 0)
        oled.text("915 MHz SF7", 0, 20)
        oled.show()

    print("[RX] En écoute... (Ctrl-C pour arrêter)")
    print(f"     Fréquence : {FREQ_HZ/1e6:.1f} MHz")
    print(f"     SF7 / BW125 / CR4-5")
    print("-" * 48)

    while True:
        # Réception bloquante (5 s de timeout puis reboucle)
        result = radio.receive(timeout_ms=5000)

        if result is None:
            print("[RX] ... (rien reçu, en attente)")
            continue

        payload, rssi, snr = result
        blink(1, 30)   # clignotement bref à chaque paquet

        pkt = decode_packet(payload)

        if pkt is None:
            nb_err += 1
            print(f"[RX] Paquet {len(payload)} octets — décodage impossible (err={nb_err})")
            continue

        nb_ok += 1

        # Détection de paquets manqués
        if last_seq >= 0 and pkt["seq"] != last_seq + 1:
            manques = pkt["seq"] - last_seq - 1
            if manques > 0:
                print(f"     ⚠  {manques} paquet(s) manqué(s) !")
        last_seq = pkt["seq"]

        print(f"[RX #{pkt['seq']:4d}] "
              f"Node={pkt['node']:02X}h  "
              f"RSSI={rssi:+.1f} dBm  "
              f"SNR={snr:+.1f} dB  "
              f"ADC={pkt['adc']}  "
              f"\"{pkt['msg']}\"")

        oled_show(oled,
                  seq    = pkt["seq"],
                  rssi   = rssi,
                  snr    = snr,
                  msg    = pkt["msg"],
                  nb_ok  = nb_ok,
                  nb_err = nb_err)

# ─── Lancement ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    main()

