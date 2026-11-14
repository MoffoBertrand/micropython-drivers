# pca9685_async.py — Version asynchrone du pilote PCA9685
# À utiliser avec asyncio (MicroPython uasyncio).
#
# Différences avec pca9685.py (version synchrone) :
#   - freq()    → coroutine : await asyncio.sleep_ms(5) ×2 au lieu de time.sleep_ms
#   - _reset()  → coroutine : await asyncio.sleep_ms(5)
#   - create()  → classmethod async (remplace __init__ pour l'initialisation complète)
#
# Les méthodes pwm(), duty(), level(), stop_all() restent SYNCHRONES :
# les écritures I²C dans les registres LED du PCA9685 durent < 0,5 ms
# et n'ont PAS besoin d'await — les appeler directement depuis une coroutine
# sans bloquer le scheduler.
#
# Usage :
#   import asyncio
#   from machine import Pin, I2C
#   import pca9685_async as pca_mod
#
#   i2c = I2C(0, sda=Pin(8), scl=Pin(9), freq=400_000)
#   pca = await pca_mod.PCA9685.create(i2c, freq_hz=100)
#
#   async def tache():
#       pca.duty(0, 75)    # synchrone — pas d'await nécessaire
#       pca.level(1, 1)    # synchrone

import asyncio

_MODE1    = 0x00
_PRESCALE = 0xFE
_LED0_ON  = 0x06


class PCA9685:
    """Pilote PCA9685 asynchrone — contrôleur PWM 16 canaux (I²C 0x40).

    Constructeur async
    ------------------
        pca = await PCA9685.create(i2c, freq_hz=100)

    Méthodes de commande (pwm, duty, level, stop_all) : SYNCHRONES.
    Seules freq() et create() nécessitent await.
    """

    def __init__(self, i2c, addr=0x40):
        self._i2c  = i2c
        self._addr = addr

    @classmethod
    async def create(cls, i2c, addr=0x40, freq_hz=100):
        """Crée, réinitialise et configure la fréquence PWM de façon async.

        Paramètres
        ----------
        i2c     : objet machine.I2C
        addr    : adresse I²C (défaut 0x40)
        freq_hz : fréquence PWM initiale en Hz (défaut 100)
        """
        self = cls(i2c, addr)
        await self._reset()
        await self.freq(freq_hz)
        return self

    # ── Coroutines (contiennent des await) ───────────────────────────────

    async def freq(self, hz=100):
        """Règle la fréquence PWM globale (40–1000 Hz).

        Libère le scheduler pendant les courtes pauses de reconfiguration.
        """
        pre = max(3, min(255, round(25_000_000 / (4096 * hz)) - 1))
        old = self._read(_MODE1, 1)[0]
        self._write(_MODE1, [(old & 0x7F) | 0x10])   # entrer en sleep
        self._write(_PRESCALE, [pre])
        self._write(_MODE1, [old & 0x7F])
        await asyncio.sleep_ms(5)                      # ← stabilisation oscillateur
        self._write(_MODE1, [old | 0xA1])              # auto-increment ON
        await asyncio.sleep_ms(1)                      # ← sortie de sleep
        print(f"PCA9685 freq={hz} Hz, prescale={pre}")

    # ── Méthodes synchrones (< 0,5 ms chacune — pas d'await) ─────────────

    def pwm(self, ch, on, off):
        """Règle les compteurs ON/OFF bruts (0–4095) du canal ch.
        Synchrone — appelable directement depuis une coroutine."""
        reg = _LED0_ON + 4 * ch
        self._write(reg, [on & 0xFF, on >> 8, off & 0xFF, off >> 8])

    def duty(self, ch, pct):
        """Règle la duty-cycle du canal ch en pourcents (0–100).
        Synchrone — appelable directement depuis une coroutine."""
        if pct <= 0:
            self.pwm(ch, 0, 4096)
        elif pct >= 100:
            self.pwm(ch, 4096, 0)
        else:
            self.pwm(ch, 0, int(pct * 4095 // 100))

    def level(self, ch, high):
        """Force le canal ch à HIGH (1) ou LOW (0).
        Synchrone — appelable directement depuis une coroutine."""
        self.pwm(ch, 4096, 0) if high else self.pwm(ch, 0, 4096)

    def stop_all(self):
        """Met tous les canaux à 0 (sécurité).
        Synchrone — appelable directement depuis une coroutine."""
        for ch in range(16):
            self.pwm(ch, 0, 4096)

    # ── Interne ──────────────────────────────────────────────────────────

    async def _reset(self):
        self._write(_MODE1, [0x00])
        await asyncio.sleep_ms(5)

    def _write(self, reg, data):
        self._i2c.writeto_mem(self._addr, reg, bytes(data))

    def _read(self, reg, n):
        return self._i2c.readfrom_mem(self._addr, reg, n)
