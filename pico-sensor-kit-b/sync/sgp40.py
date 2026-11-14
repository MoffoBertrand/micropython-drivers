# sgp40.py — Pilote MicroPython pour SGP40 (Sensirion)
# Capteur VOC (Composés Organiques Volatils), I²C adresse fixe 0x59
# Waveshare Pico-Sensor-Kit-B : I²C bus 0 (GPIO8 SDA, GPIO9 SCL)
#
# Note : le SGP40 retourne un indice VOC brut (0–65535).
#   0       = air très propre
#   ~20000  = air intérieur normal
#   65535   = maximum pollution
#   Pour un indice VOC normalisé (0–500) utiliser le VOCAlgorithm Sensirion.
#
# Usage :
#   from machine import Pin, I2C
#   import sgp40
#   i2c  = I2C(0, sda=Pin(8), scl=Pin(9), freq=400_000)
#   sens = sgp40.SGP40(i2c)
#   voc  = sens.measure()                     # sans compensation
#   voc  = sens.measure(rh_pct=55, temp_c=23) # avec compensation T/RH

import time

_ADDR         = 0x59
_CMD_MEASURE  = bytes([0x26, 0x0F])   # Measure Raw Signal
_CMD_SELFTEST = bytes([0x28, 0x0E])   # Execute Self Test


def _crc8(b1, b2):
    """CRC-8 Sensirion (polynôme 0x31, init 0xFF) sur 2 octets."""
    crc = 0xFF
    for b in (b1, b2):
        crc ^= b
        for _ in range(8):
            crc = ((crc << 1) ^ 0x31) & 0xFF if crc & 0x80 else (crc << 1) & 0xFF
    return crc


class SGP40:
    """Pilote SGP40 — Capteur VOC Sensirion (I²C 0x59)."""

    def __init__(self, i2c, addr=_ADDR):
        self._i2c  = i2c
        self._addr = addr
        print("SGP40 OK (adresse 0x59)")

    # ── API publique ──────────────────────────────────────────────────────

    def measure(self, rh_pct=50.0, temp_c=25.0):
        """Déclenche une mesure et retourne l'indice VOC brut (0–65535).

        Paramètres
        ----------
        rh_pct  : humidité relative pour compensation (défaut 50 %RH)
        temp_c  : température pour compensation (défaut 25 °C)

        Retour
        ------
        int : indice VOC brut (0=propre, 65535=pollué)
        """
        rh_raw   = max(0, min(65535, int(rh_pct  / 100.0 * 65535)))
        temp_raw = max(0, min(65535, int((temp_c + 45.0) / 175.0 * 65535)))
        rh_h, rh_l = (rh_raw >> 8) & 0xFF, rh_raw & 0xFF
        t_h,  t_l  = (temp_raw >> 8) & 0xFF, temp_raw & 0xFF
        cmd = _CMD_MEASURE + bytes([
            rh_h, rh_l, _crc8(rh_h, rh_l),
            t_h,  t_l,  _crc8(t_h,  t_l),
        ])
        self._i2c.writeto(self._addr, cmd)
        time.sleep_ms(30)
        data = self._i2c.readfrom(self._addr, 3)
        return (data[0] << 8) | data[1]

    def measure_with_shtc3(self, shtc3_sensor):
        """Mesure avec compensation automatique depuis un capteur SHTC3.

        Paramètres
        ----------
        shtc3_sensor : instance shtc3.SHTC3 déjà initialisée

        Retour
        ------
        tuple (int, float, float) : (voc_brut, temp_C, hum_pct)
        """
        temp, hum = shtc3_sensor.read()
        voc = self.measure(rh_pct=hum, temp_c=temp)
        return voc, temp, hum

    def self_test(self):
        """Exécute le self-test interne (300 ms). Retourne True si OK."""
        self._i2c.writeto(self._addr, _CMD_SELFTEST)
        time.sleep_ms(320)
        data = self._i2c.readfrom(self._addr, 3)
        result = (data[0] << 8) | data[1]
        ok = (result == 0xD400)
        print(f"SGP40 self-test : {'OK' if ok else 'ECHEC'} (0x{result:04X})")
        return ok

    @staticmethod
    def describe(voc):
        """Retourne une description textuelle de l'indice VOC brut."""
        if voc < 15000:
            return "Excellent"
        elif voc < 30000:
            return "Bon"
        elif voc < 45000:
            return "Modéré"
        elif voc < 55000:
            return "Mauvais"
        else:
            return "Très mauvais"
