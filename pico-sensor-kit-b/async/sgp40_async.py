# sgp40_async.py — Version asynchrone du pilote SGP40 (Sensirion)
# À utiliser avec asyncio (MicroPython uasyncio).
#
# Différences avec sgp40.py (version synchrone) :
#   - measure()   → coroutine : await asyncio.sleep_ms(30) au lieu de time.sleep_ms
#   - self_test() → coroutine : await asyncio.sleep_ms(320)
#   - measure_with_shtc3() → coroutine : accepte un SHTC3 async ou sync
#
# Usage :
#   import asyncio
#   from machine import Pin, I2C
#   import sgp40_async as sgp
#
#   i2c  = I2C(0, sda=Pin(8), scl=Pin(9), freq=400_000)
#   sens = sgp.SGP40(i2c)
#
#   async def tache():
#       voc = await sens.measure(rh_pct=55, temp_c=23)
#       print(f"VOC brut : {voc}  → {sgp.SGP40.describe(voc)}")

import asyncio

_ADDR         = 0x59
_CMD_MEASURE  = bytes([0x26, 0x0F])
_CMD_SELFTEST = bytes([0x28, 0x0E])


def _crc8(b1, b2):
    """CRC-8 Sensirion : polynôme 0x31, init 0xFF."""
    crc = 0xFF
    for b in (b1, b2):
        crc ^= b
        for _ in range(8):
            crc = ((crc << 1) ^ 0x31) & 0xFF if crc & 0x80 else (crc << 1) & 0xFF
    return crc


class SGP40:
    """Pilote SGP40 asynchrone — Capteur VOC Sensirion (I²C 0x59).

    Toutes les méthodes d'acquisition sont des coroutines.
    Les méthodes utilitaires (describe) restent synchrones.
    """

    def __init__(self, i2c, addr=_ADDR):
        self._i2c  = i2c
        self._addr = addr
        print("SGP40 OK (adresse 0x59)")

    # ── API publique (coroutines) ─────────────────────────────────────────

    async def measure(self, rh_pct=50.0, temp_c=25.0):
        """Déclenche une mesure VOC et retourne l'indice brut (0–65535).

        Libère le scheduler pendant les 30 ms d'attente de mesure.

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
        await asyncio.sleep_ms(30)   # ← libère le scheduler (tMEAS ≤ 30 ms)
        data = self._i2c.readfrom(self._addr, 3)
        return (data[0] << 8) | data[1]

    async def measure_with_shtc3(self, shtc3_sensor):
        """Mesure avec compensation automatique depuis un capteur SHTC3 async.

        Paramètres
        ----------
        shtc3_sensor : instance shtc3_async.SHTC3 déjà initialisée

        Retour
        ------
        tuple (int, float, float) : (voc_brut, temp_C, hum_pct)
        """
        temp, hum = await shtc3_sensor.read()
        voc = await self.measure(rh_pct=hum, temp_c=temp)
        return voc, temp, hum

    async def self_test(self):
        """Exécute le self-test interne (320 ms). Retourne True si OK.

        Libère le scheduler pendant les 320 ms d'attente.
        """
        self._i2c.writeto(self._addr, _CMD_SELFTEST)
        await asyncio.sleep_ms(320)   # ← libère le scheduler
        data = self._i2c.readfrom(self._addr, 3)
        result = (data[0] << 8) | data[1]
        ok = (result == 0xD400)
        print(f"SGP40 self-test : {'OK' if ok else 'ECHEC'} (0x{result:04X})")
        return ok

    # ── Méthodes synchrones (pas d'I/O) ──────────────────────────────────

    @staticmethod
    def describe(voc):
        """Retourne une description textuelle de l'indice VOC brut."""
        if voc < 15000: return "Excellent"
        elif voc < 30000: return "Bon"
        elif voc < 45000: return "Modéré"
        elif voc < 55000: return "Mauvais"
        else: return "Très mauvais"
