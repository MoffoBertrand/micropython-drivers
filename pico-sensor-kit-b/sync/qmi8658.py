# qmi8658.py — Pilote MicroPython pour QMI8658C (QST Corporation)
# IMU 6 axes : accéléromètre + gyroscope, I²C adresse 0x6B
# Waveshare Pico-Sensor-Kit-B : I²C bus 0 (GPIO8 SDA, GPIO9 SCL)
#
# Usage :
#   from machine import Pin, I2C
#   import qmi8658
#   i2c  = I2C(0, sda=Pin(8), scl=Pin(9), freq=400_000)
#   imu  = qmi8658.QMI8658(i2c)
#   ax, ay, az = imu.accel()
#   gx, gy, gz = imu.gyro()
#   roll, pitch = imu.orientation()

import math
import time

_ADDR      = 0x6B   # SA0 = VDD sur le schéma Waveshare V1.1

# ── Registres principaux ──────────────────────────────────────────────────
_REG_WHO_AM_I   = 0x00   # valeur attendue : 0x05
_REG_CTRL1      = 0x02   # Accéléromètre : plage + ODR
_REG_CTRL2      = 0x03   # Gyroscope     : plage + ODR
_REG_CTRL7      = 0x08   # Enable accel/gyro
_REG_ACCEL_XOUT = 0x35   # Données accel  (6 octets, little-endian)
_REG_GYRO_XOUT  = 0x3B   # Données gyro   (6 octets, little-endian)

# ── Facteurs d'échelle ─────────────────────────────────────────────────────
# Accéléromètre : 0x60 → ±4 g  →  sensibilité = 8192 LSB/g
# Gyroscope     : 0x60 → ±512 dps → sensibilité = 64 LSB/dps
_ACCEL_SCALE = 8192.0
_GYRO_SCALE  =   64.0


class QMI8658:
    """Pilote QMI8658C — IMU 6 axes (I²C 0x6B)."""

    def __init__(self, i2c, addr=_ADDR):
        self._i2c  = i2c
        self._addr = addr
        self._init()

    # ── API publique ──────────────────────────────────────────────────────

    def accel(self):
        """Retourne l'accélération (ax, ay, az) en g."""
        d = self._read(_REG_ACCEL_XOUT, 6)
        return self._parse(d, _ACCEL_SCALE)

    def gyro(self):
        """Retourne la vitesse angulaire (gx, gy, gz) en °/s."""
        d = self._read(_REG_GYRO_XOUT, 6)
        return self._parse(d, _GYRO_SCALE)

    def read_all(self):
        """Retourne (ax, ay, az, gx, gy, gz) en une seule lecture I²C."""
        # Les registres accel et gyro sont contigus (0x35 → 0x44)
        d = self._read(_REG_ACCEL_XOUT, 12)
        ax, ay, az = self._parse(d[0:6],  _ACCEL_SCALE)
        gx, gy, gz = self._parse(d[6:12], _GYRO_SCALE)
        return ax, ay, az, gx, gy, gz

    def orientation(self):
        """Calcule roll et pitch (en degrés) depuis l'accéléromètre.

        Retour
        ------
        tuple (roll_deg, pitch_deg)
          roll  : inclinaison latérale (axe X)
          pitch : inclinaison avant/arrière (axe Y)
        """
        ax, ay, az = self.accel()
        roll  = math.atan2(ay, az) * 180 / math.pi
        pitch = math.atan2(-ax, math.sqrt(ay*ay + az*az)) * 180 / math.pi
        return roll, pitch

    def is_shaken(self, threshold_g=1.5):
        """Détecte une secousse si la norme d'accélération dépasse le seuil.

        Paramètres
        ----------
        threshold_g : seuil en g (défaut 1.5 g)

        Retour
        ------
        bool
        """
        ax, ay, az = self.accel()
        norm = math.sqrt(ax*ax + ay*ay + az*az)
        return abs(norm - 1.0) > (threshold_g - 1.0)

    # ── Interne ──────────────────────────────────────────────────────────

    def _init(self):
        who = self._read(_REG_WHO_AM_I, 1)[0]
        if who != 0x05:
            raise OSError(f"QMI8658 non détecté (WHO_AM_I=0x{who:02X}, attendu 0x05)")
        # Accel ±4 g, ODR 896 Hz
        self._write(_REG_CTRL1, [0x60])
        # Gyro ±512 dps, ODR 896 Hz
        self._write(_REG_CTRL2, [0x60])
        # Enable accel + gyro
        self._write(_REG_CTRL7, [0x03])
        time.sleep_ms(10)
        print("QMI8658 OK (adresse 0x6B)")

    def _write(self, reg, data):
        self._i2c.writeto_mem(self._addr, reg, bytes(data))

    def _read(self, reg, n):
        return self._i2c.readfrom_mem(self._addr, reg, n)

    @staticmethod
    def _parse(data, scale):
        """Convertit 6 octets little-endian en (x, y, z) mis à l'échelle."""
        def s16(hi, lo):
            raw = (hi << 8) | lo
            return raw - 65536 if raw >= 32768 else raw
        x = s16(data[1], data[0]) / scale
        y = s16(data[3], data[2]) / scale
        z = s16(data[5], data[4]) / scale
        return x, y, z
