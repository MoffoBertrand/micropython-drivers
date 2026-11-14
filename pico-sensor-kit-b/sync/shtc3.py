# shtc3.py — Pilote MicroPython pour SHTC3 (Sensirion)
# Capteur Température & Humidité relative, I²C adresse fixe 0x70
# Waveshare Pico-Sensor-Kit-B : I²C bus 0 (GPIO8 SDA, GPIO9 SCL)
#
# CRC-8 (Sensirion) : polynôme 0x31, valeur initiale 0xFF, pas de XOR final
#   Réponse mesure (6 octets) : T_MSB T_LSB CRC_T  H_MSB H_LSB CRC_H
#   Réponse ID     (3 octets) : ID_MSB ID_LSB CRC_ID
#   Le CRC couvre les 2 octets de données qui le précèdent.
#   En cas d'erreur CRC : lève ValueError avec les octets bruts pour diagnostic.
#
# Usage :
#   from machine import Pin, I2C
#   import shtc3
#   i2c  = I2C(0, sda=Pin(8), scl=Pin(9), freq=400_000)
#   sens = shtc3.SHTC3(i2c)
#   temp, hum = sens.read()
#   print(f"T={temp:.2f}°C  H={hum:.1f}%RH")

import time

_ADDR    = 0x70
_WAKEUP  = bytes([0x35, 0x17])
_SLEEP   = bytes([0xB0, 0x98])
_MEASURE = bytes([0x7C, 0xA2])   # Normal Mode, Température en premier
_READ_ID = bytes([0xEF, 0xC8])


def _crc8(b1, b2):
    """CRC-8 Sensirion : polynôme 0x31, init 0xFF, couvre 2 octets de données.

    Algorithme (datasheet SHTC3 §4.8) :
      1. Init CRC = 0xFF
      2. Pour chaque bit (MSB en premier) : XOR avec MSB du CRC courant,
         si MSB=1 décaler puis XOR 0x31, sinon décaler seulement.
      3. Répéter pour les 2 octets.
    """
    crc = 0xFF
    for byte in (b1, b2):
        crc ^= byte
        for _ in range(8):
            if crc & 0x80:
                crc = ((crc << 1) ^ 0x31) & 0xFF
            else:
                crc = (crc << 1) & 0xFF
    return crc


class SHTC3:
    """Pilote SHTC3 — Capteur Temp/Hum Sensirion (I²C 0x70).

    Chaque lecture vérifie les deux CRC-8 (température et humidité).
    Une ValueError est levée si un CRC ne correspond pas, indiquant
    une corruption sur le bus I²C (bruit, câblage trop long, etc.).
    """

    def __init__(self, i2c, addr=_ADDR):
        self._i2c  = i2c
        self._addr = addr
        self._check_id()

    # ── API publique ──────────────────────────────────────────────────────

    def read(self):
        """Déclenche une mesure et retourne (temperature_C, humidite_pct).

        Vérifie les CRC-8 de la température ET de l'humidité.
        Lève ValueError si l'un des CRC est incorrect.

        Retour
        ------
        tuple (float, float) : température en °C, humidité en %RH
        """
        self._wakeup()
        self._i2c.writeto(self._addr, _MEASURE)
        time.sleep_ms(13)                         # tMEAS ≤ 12,1 ms
        data = self._i2c.readfrom(self._addr, 6)
        self._sleep()

        # Trame : [T_MSB, T_LSB, CRC_T, H_MSB, H_LSB, CRC_H]
        t_msb, t_lsb, crc_t = data[0], data[1], data[2]
        h_msb, h_lsb, crc_h = data[3], data[4], data[5]

        # ── Vérification CRC température ─────────────────────────────────
        calc_t = _crc8(t_msb, t_lsb)
        if calc_t != crc_t:
            raise ValueError(
                f"SHTC3 CRC température incorrect : "
                f"reçu 0x{crc_t:02X}, calculé 0x{calc_t:02X} "
                f"(données brutes : {list(data)})"
            )

        # ── Vérification CRC humidité ─────────────────────────────────────
        calc_h = _crc8(h_msb, h_lsb)
        if calc_h != crc_h:
            raise ValueError(
                f"SHTC3 CRC humidité incorrect : "
                f"reçu 0x{crc_h:02X}, calculé 0x{calc_h:02X} "
                f"(données brutes : {list(data)})"
            )

        raw_t = (t_msb << 8) | t_lsb
        raw_h = (h_msb << 8) | h_lsb
        temp  = -45.0 + 175.0 * raw_t / 65535.0
        hum   = max(0.0, min(100.0, 100.0 * raw_h / 65535.0))
        return temp, hum

    @property
    def temperature(self):
        """Température seule (°C)."""
        return self.read()[0]

    @property
    def humidity(self):
        """Humidité relative seule (%RH)."""
        return self.read()[1]

    # ── Interne ──────────────────────────────────────────────────────────

    def _check_id(self):
        """Lit et vérifie le chip ID (CRC inclus). Lève OSError si absent."""
        self._wakeup()
        self._i2c.writeto(self._addr, _READ_ID)
        raw = self._i2c.readfrom(self._addr, 3)
        self._sleep()

        id_msb, id_lsb, crc_id = raw[0], raw[1], raw[2]

        # ── Vérification CRC du chip ID ───────────────────────────────────
        calc = _crc8(id_msb, id_lsb)
        if calc != crc_id:
            raise OSError(
                f"SHTC3 CRC chip ID incorrect : "
                f"reçu 0x{crc_id:02X}, calculé 0x{calc:02X}"
            )

        chip_id = ((id_msb << 8) | id_lsb) & 0x083F
        if chip_id == 0:
            raise OSError("SHTC3 non détecté à l'adresse 0x70")
        print(f"SHTC3 OK (chip_id=0x{chip_id:04X}, CRC OK)")

    def _wakeup(self):
        self._i2c.writeto(self._addr, _WAKEUP)
        time.sleep_ms(1)                          # tWU ≥ 240 µs

    def _sleep(self):
        self._i2c.writeto(self._addr, _SLEEP)
