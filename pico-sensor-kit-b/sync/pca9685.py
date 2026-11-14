# pca9685.py — Pilote MicroPython pour PCA9685
# Contrôleur PWM 16 canaux, 12-bit, I²C
# Oscillateur interne : 25 MHz — Résolution : 0 → 4095
# Waveshare Pico-Sensor-Kit-B : I²C bus 0, adresse 0x40
#
# Usage :
#   from machine import Pin, I2C
#   import pca9685
#   i2c = I2C(0, sda=Pin(8), scl=Pin(9), freq=400_000)
#   pca = pca9685.PCA9685(i2c)
#   pca.freq(100)
#   pca.duty(0, 50)   # canal 0 à 50 %

import time

_MODE1    = 0x00
_PRESCALE = 0xFE
_LED0_ON  = 0x06   # base registres canal 0 ; +4 par canal


class PCA9685:
    """Pilote PCA9685 — contrôleur PWM 16 canaux via I²C."""

    def __init__(self, i2c, addr=0x40):
        self._i2c  = i2c
        self._addr = addr
        self._reset()

    # ── API publique ──────────────────────────────────────────────────────

    def freq(self, hz=100):
        """Règle la fréquence PWM globale (40–1000 Hz).
        Doit être appelé avant toute commande de canal."""
        pre = max(3, min(255, round(25_000_000 / (4096 * hz)) - 1))
        old = self._read(0, 1)[0]
        self._write(0, [(old & 0x7F) | 0x10])   # sleep
        self._write(_PRESCALE, [pre])
        self._write(0, [old & 0x7F])
        time.sleep_ms(5)
        self._write(0, [old | 0xA1])             # auto-increment ON
        print(f"PCA9685 freq={hz} Hz, prescale={pre}")

    def pwm(self, ch, on, off):
        """Règle les compteurs ON/OFF bruts (0–4095) du canal ch."""
        reg = _LED0_ON + 4 * ch
        self._write(reg, [on & 0xFF, on >> 8, off & 0xFF, off >> 8])

    def duty(self, ch, pct):
        """Règle la duty-cycle du canal ch en pourcents (0–100)."""
        if pct <= 0:
            self.pwm(ch, 0, 4096)        # toujours OFF
        elif pct >= 100:
            self.pwm(ch, 4096, 0)        # toujours ON
        else:
            self.pwm(ch, 0, int(pct * 4095 // 100))

    def level(self, ch, high):
        """Force le canal ch à l'état logique HIGH (1) ou LOW (0)."""
        self.pwm(ch, 4096, 0) if high else self.pwm(ch, 0, 4096)

    def stop_all(self):
        """Met tous les canaux à 0 (sécurité)."""
        for ch in range(16):
            self.pwm(ch, 0, 4096)

    # ── Interne ──────────────────────────────────────────────────────────

    def _reset(self):
        self._write(_MODE1, [0x00])
        time.sleep_ms(5)

    def _write(self, reg, data):
        self._i2c.writeto_mem(self._addr, reg, bytes(data))

    def _read(self, reg, n):
        return self._i2c.readfrom_mem(self._addr, reg, n)
