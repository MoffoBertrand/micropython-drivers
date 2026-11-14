# shtc3_async.py — Version asynchrone du pilote SHTC3 (Sensirion)
# À utiliser avec asyncio (MicroPython uasyncio).
#
# Différences avec shtc3.py (version synchrone) :
#   - read()      → coroutine : await asyncio.sleep_ms(13) au lieu de time.sleep_ms
#   - _check_id() → coroutine : await pour le wake-up
#   - _wakeup()   → coroutine : await asyncio.sleep_ms(1)
#
# Dans une boucle asyncio, ceci permet à d'autres tâches de s'exécuter
# pendant les 13 ms d'attente de mesure (au lieu de bloquer le scheduler).
#
# CRC-8 : polynôme 0x31, init 0xFF — même algorithme que la version sync.
# Trame mesure (6 o) : T_MSB T_LSB CRC_T  H_MSB H_LSB CRC_H
#
# Usage :
#   import asyncio
#   from machine import Pin, I2C
#   import shtc3_async as shtc
#
#   i2c  = I2C(0, sda=Pin(8), scl=Pin(9), freq=400_000)
#   sens = await shtc.SHTC3.create(i2c)   # constructeur async
#
#   async def tache():
#       temp, hum = await sens.read()
#       print(f"T={temp:.1f}°C  H={hum:.1f}%")

import asyncio

_ADDR    = 0x70
_WAKEUP  = bytes([0x35, 0x17])
_SLEEP   = bytes([0xB0, 0x98])
_MEASURE = bytes([0x7C, 0xA2])   # Normal Mode, Température en premier
_READ_ID = bytes([0xEF, 0xC8])


def _crc8(b1, b2):
    """CRC-8 Sensirion : polynôme 0x31, init 0xFF, couvre 2 octets."""
    crc = 0xFF
    for byte in (b1, b2):
        crc ^= byte
        for _ in range(8):
            crc = ((crc << 1) ^ 0x31) & 0xFF if crc & 0x80 else (crc << 1) & 0xFF
    return crc


class SHTC3:
    """Pilote SHTC3 asynchrone — Capteur Temp/Hum Sensirion (I²C 0x70).

    Constructeur async
    ------------------
    Utiliser SHTC3.create(i2c) plutôt que SHTC3(i2c) directement,
    car __init__ ne peut pas être une coroutine :

        sens = await SHTC3.create(i2c)

    Compatibilité
    -------------
    L'API reste identique à shtc3.SHTC3, toutes les méthodes
    publiques sont maintenant des coroutines (await requis).
    """

    def __init__(self, i2c, addr=_ADDR):
        # Constructeur léger — pas d'I/O ici.
        # Utiliser create() pour initialiser avec vérification d'ID.
        self._i2c  = i2c
        self._addr = addr

    @classmethod
    async def create(cls, i2c, addr=_ADDR):
        """Crée et initialise une instance SHTC3 de façon asynchrone.

        Vérifie la présence du capteur et le CRC du chip ID.
        Lève OSError si le capteur est absent ou si le CRC est incorrect.
        """
        self = cls(i2c, addr)
        await self._check_id()
        return self

    # ── API publique (coroutines) ─────────────────────────────────────────

    async def read(self):
        """Déclenche une mesure et retourne (temperature_C, humidite_pct).

        Libère le scheduler pendant les 13 ms d'attente de mesure.
        Vérifie les deux CRC-8 (température et humidité).

        Retour
        ------
        tuple (float, float) : température en °C, humidité en %RH
        """
        await self._wakeup()
        self._i2c.writeto(self._addr, _MEASURE)
        await asyncio.sleep_ms(13)                # ← libère le scheduler (tMEAS ≤ 12,1 ms)
        data = self._i2c.readfrom(self._addr, 6)
        self._sleep()

        t_msb, t_lsb, crc_t = data[0], data[1], data[2]
        h_msb, h_lsb, crc_h = data[3], data[4], data[5]

        if _crc8(t_msb, t_lsb) != crc_t:
            raise ValueError(
                f"SHTC3 CRC température : reçu 0x{crc_t:02X}, "
                f"calculé 0x{_crc8(t_msb, t_lsb):02X}"
            )
        if _crc8(h_msb, h_lsb) != crc_h:
            raise ValueError(
                f"SHTC3 CRC humidité : reçu 0x{crc_h:02X}, "
                f"calculé 0x{_crc8(h_msb, h_lsb):02X}"
            )

        raw_t = (t_msb << 8) | t_lsb
        raw_h = (h_msb << 8) | h_lsb
        temp  = -45.0 + 175.0 * raw_t / 65535.0
        hum   = max(0.0, min(100.0, 100.0 * raw_h / 65535.0))
        return temp, hum

    # ── Interne ──────────────────────────────────────────────────────────

    async def _check_id(self):
        await self._wakeup()
        self._i2c.writeto(self._addr, _READ_ID)
        raw = self._i2c.readfrom(self._addr, 3)
        self._sleep()
        if _crc8(raw[0], raw[1]) != raw[2]:
            raise OSError("SHTC3 CRC chip ID incorrect")
        chip_id = ((raw[0] << 8) | raw[1]) & 0x083F
        if chip_id == 0:
            raise OSError("SHTC3 non détecté à l'adresse 0x70")
        print(f"SHTC3 OK (chip_id=0x{chip_id:04X}, CRC OK)")

    async def _wakeup(self):
        self._i2c.writeto(self._addr, _WAKEUP)
        await asyncio.sleep_ms(1)   # tWU ≥ 240 µs — libère le scheduler

    def _sleep(self):
        # _sleep est instantané (pas d'attente) → méthode synchrone
        self._i2c.writeto(self._addr, _SLEEP)
