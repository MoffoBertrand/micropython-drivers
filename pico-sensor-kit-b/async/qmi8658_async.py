# qmi8658_async.py — Version asynchrone du pilote QMI8658C (QST Corporation)
# À utiliser avec asyncio (MicroPython uasyncio).
#
# Différences avec qmi8658.py (version synchrone) :
#   - _init()  → coroutine : await asyncio.sleep_ms(10) au lieu de time.sleep_ms
#   - create() → classmethod async
#
# Les méthodes de lecture restent SYNCHRONES :
#   accel(), gyro(), read_all(), orientation(), is_shaken()
#
#   Pourquoi synchrones ? Les lectures de registres I²C du QMI8658 durent
#   < 0,5 ms. Il n'y a aucune attente matérielle après la commande de lecture.
#   Les appeler directement dans une coroutine (sans await) n'affecte pas
#   le scheduler de façon significative.
#
#   Seul _init() contient un sleep de 10 ms (stabilisation après config),
#   d'où create() async.
#
# Usage :
#   import asyncio, qmi8658_async as imu_mod
#   from machine import Pin, I2C
#
#   i2c = I2C(0, sda=Pin(8), scl=Pin(9), freq=400_000)
#   imu = await imu_mod.QMI8658.create(i2c)
#
#   async def tache_imu():
#       while True:
#           ax, ay, az = imu.accel()    # synchrone — pas d'await
#           roll, pitch = imu.orientation()
#           await asyncio.sleep_ms(50)  # cadence 20 Hz

import asyncio
import math

_ADDR           = 0x6B
_REG_WHO_AM_I   = 0x00
_REG_CTRL1      = 0x02
_REG_CTRL2      = 0x03
_REG_CTRL7      = 0x08
_REG_ACCEL_XOUT = 0x35
_REG_GYRO_XOUT  = 0x3B
_ACCEL_SCALE    = 8192.0
_GYRO_SCALE     =   64.0


class QMI8658:
    """Pilote QMI8658C asynchrone — IMU 6 axes (I²C 0x6B).

    Constructeur async
    ------------------
        imu = await QMI8658.create(i2c)

    Méthodes de lecture : SYNCHRONES (< 0,5 ms, pas d'await nécessaire).
    Seul create() nécessite await (initialisation avec sleep de stabilisation).
    """

    def __init__(self, i2c, addr=_ADDR):
        self._i2c  = i2c
        self._addr = addr

    @classmethod
    async def create(cls, i2c, addr=_ADDR):
        """Crée et initialise l'IMU de façon asynchrone.

        Libère le scheduler pendant les 10 ms de stabilisation post-config.
        Lève OSError si le chip ID est incorrect.
        """
        self = cls(i2c, addr)
        await self._init()
        return self

    # ── API publique synchrone ────────────────────────────────────────────

    def accel(self):
        """Retourne l'accélération (ax, ay, az) en g. Synchrone."""
        return self._parse(self._read(_REG_ACCEL_XOUT, 6), _ACCEL_SCALE)

    def gyro(self):
        """Retourne la vitesse angulaire (gx, gy, gz) en °/s. Synchrone."""
        return self._parse(self._read(_REG_GYRO_XOUT, 6), _GYRO_SCALE)

    def read_all(self):
        """Retourne (ax, ay, az, gx, gy, gz) en une seule lecture I²C. Synchrone."""
        d = self._read(_REG_ACCEL_XOUT, 12)
        return (*self._parse(d[0:6], _ACCEL_SCALE), *self._parse(d[6:12], _GYRO_SCALE))

    def orientation(self):
        """Calcule roll et pitch (°) depuis l'accéléromètre. Synchrone."""
        ax, ay, az = self.accel()
        roll  = math.atan2(ay, az) * 180 / math.pi
        pitch = math.atan2(-ax, math.sqrt(ay*ay + az*az)) * 180 / math.pi
        return roll, pitch

    def is_shaken(self, threshold_g=1.5):
        """Détecte une secousse. Synchrone."""
        ax, ay, az = self.accel()
        return abs(math.sqrt(ax*ax + ay*ay + az*az) - 1.0) > (threshold_g - 1.0)

    # ── Interne ──────────────────────────────────────────────────────────

    async def _init(self):
        who = self._read(_REG_WHO_AM_I, 1)[0]
        if who != 0x05:
            raise OSError(f"QMI8658 non détecté (WHO_AM_I=0x{who:02X}, attendu 0x05)")
        self._write(_REG_CTRL1, [0x60])
        self._write(_REG_CTRL2, [0x60])
        self._write(_REG_CTRL7, [0x03])
        await asyncio.sleep_ms(10)   # ← stabilisation post-config
        print("QMI8658 OK (adresse 0x6B)")

    def _write(self, reg, data):
        self._i2c.writeto_mem(self._addr, reg, bytes(data))

    def _read(self, reg, n):
        return self._i2c.readfrom_mem(self._addr, reg, n)

    @staticmethod
    def _parse(data, scale):
        def s16(hi, lo):
            raw = (hi << 8) | lo
            return raw - 65536 if raw >= 32768 else raw
        return (
            s16(data[1], data[0]) / scale,
            s16(data[3], data[2]) / scale,
            s16(data[5], data[4]) / scale,
        )
