# tb6612_async.py — Version asynchrone du pilote 2× TB6612FNG via PCA9685
# À utiliser avec asyncio (MicroPython uasyncio).
#
# Différences avec tb6612.py (version synchrone) :
#   - ramp()       → coroutine : await asyncio.sleep_ms() au lieu de time.sleep_ms
#   - ramp_quad()  → coroutine : idem
#   - create()     → classmethod async
#
# Les méthodes de commande instantanée restent SYNCHRONES :
#   run(), stop(), brake(), dual_run(), quad_run(),
#   forward(), backward(), turn_left(), turn_right(), spin_left(), spin_right()
#
# Ceci est intentionnel : les écritures PCA9685 durent < 1 ms et peuvent être
# appelées directement dans une coroutine sans libérer le scheduler.
# Seules les rampes (qui contiennent des boucles avec délai) sont async.
#
# Usage typique en asyncio :
#   import asyncio, pca9685_async, tb6612_async as tb
#   from machine import Pin, I2C
#
#   i2c = I2C(0, sda=Pin(8), scl=Pin(9), freq=400_000)
#   pca = await pca9685_async.PCA9685.create(i2c, freq_hz=100)
#   mot = tb.TB6612(pca)
#
#   async def tache_moteurs():
#       mot.forward(70)                        # synchrone
#       await asyncio.sleep_ms(2000)
#       await mot.ramp('A', 0, steps=20)       # rampe async
#       mot.brake('all')

import asyncio

_CH = {
    'A': (0, 1, 2),
    'B': (3, 4, 5),
    'C': (6, 7, 8),
    'D': (9, 10, 11),
}

_PAIRS = {
    'AB': ('A', 'B'),
    'CD': ('C', 'D'),
    'AC': ('A', 'C'),
    'BD': ('B', 'D'),
}


class TB6612:
    """Pilote 2× TB6612FNG asynchrone — 4 moteurs DC via PCA9685.

    Moteurs : 'A', 'B' (TB1, ch 0–5)  |  'C', 'D' (TB2, ch 6–11)
    Paires  : 'AB', 'CD', 'AC', 'BD'
    Tous    : 'all'

    Méthodes synchrones (appelables directement dans une coroutine) :
        run, stop, brake, dual_run, quad_run,
        forward, backward, turn_left, turn_right, spin_left, spin_right

    Coroutines (nécessitent await) :
        ramp, ramp_quad
    """

    MOTORS = ('A', 'B', 'C', 'D')

    def __init__(self, pca):
        self._pca = pca
        self._stop_all()
        print("TB6612 OK — 4 moteurs (A, B via TB1 | C, D via TB2)")

    # ── Méthodes synchrones ───────────────────────────────────────────────

    def run(self, motor, speed, forward=True):
        """Lance un moteur. Synchrone — pas d'await nécessaire."""
        motor = motor.upper()
        if motor not in _CH:
            raise ValueError(f"Moteur '{motor}' inconnu. Utiliser A, B, C ou D.")
        ch_pwm, ch_in1, ch_in2 = _CH[motor]
        self._pca.duty(ch_pwm, max(0, min(100, speed)))
        self._pca.level(ch_in1, 1 if forward else 0)
        self._pca.level(ch_in2, 0 if forward else 1)

    def stop(self, motor='all'):
        """Arrêt roue libre. Synchrone."""
        for m in self._resolve(motor):
            self._pca.duty(_CH[m][0], 0)

    def brake(self, motor='all'):
        """Freinage actif. Synchrone."""
        for m in self._resolve(motor):
            ch_pwm, ch_in1, ch_in2 = _CH[m]
            self._pca.duty(ch_pwm, 0)
            self._pca.level(ch_in1, 1)
            self._pca.level(ch_in2, 1)

    def dual_run(self, pair, speed1, speed2, forward1=True, forward2=True):
        """Commande simultanée d'une paire. Synchrone."""
        pair = pair.upper()
        if pair not in _PAIRS:
            raise ValueError(f"Paire '{pair}' inconnue. Utiliser AB, CD, AC ou BD.")
        m1, m2 = _PAIRS[pair]
        self.run(m1, speed1, forward1)
        self.run(m2, speed2, forward2)

    def quad_run(self, speed_a, speed_b, speed_c, speed_d,
                 fwd_a=True, fwd_b=True, fwd_c=True, fwd_d=True):
        """Commande simultanée des 4 moteurs. Synchrone."""
        self.run('A', speed_a, fwd_a)
        self.run('B', speed_b, fwd_b)
        self.run('C', speed_c, fwd_c)
        self.run('D', speed_d, fwd_d)

    def forward(self, speed=70):
        """Robot 4WD avance tout droit. Synchrone."""
        self.quad_run(speed, speed, speed, speed)

    def backward(self, speed=70):
        """Robot 4WD recule tout droit. Synchrone."""
        self.quad_run(speed, speed, speed, speed, False, False, False, False)

    def turn_left(self, speed=70, inner=30):
        """Virage à gauche. Synchrone."""
        self.quad_run(inner, speed, inner, speed)

    def turn_right(self, speed=70, inner=30):
        """Virage à droite. Synchrone."""
        self.quad_run(speed, inner, speed, inner)

    def spin_left(self, speed=60):
        """Rotation sur place sens anti-horaire. Synchrone."""
        self.quad_run(speed, speed, speed, speed, False, True, False, True)

    def spin_right(self, speed=60):
        """Rotation sur place sens horaire. Synchrone."""
        self.quad_run(speed, speed, speed, speed, True, False, True, False)

    # ── Coroutines (contiennent des délais) ──────────────────────────────

    async def ramp(self, motor, target, steps=20, delay_ms=50, forward=True):
        """Rampe d'accélération async vers la vitesse cible.

        Libère le scheduler entre chaque palier (await asyncio.sleep_ms).

        Paramètres
        ----------
        motor    : 'A', 'B', 'C' ou 'D'
        target   : vitesse cible 0–100 %
        steps    : nombre de paliers (défaut 20)
        delay_ms : attente entre paliers en ms (défaut 50 ms → 20 Hz)
        forward  : sens de rotation
        """
        step = max(1, target // steps)
        for spd in range(0, target + step, step):
            self.run(motor, min(spd, target), forward)
            await asyncio.sleep_ms(delay_ms)   # ← libère le scheduler

    async def ramp_quad(self, targets, steps=20, delay_ms=50, forwards=None):
        """Rampe d'accélération simultanée des 4 moteurs. Async.

        Paramètres
        ----------
        targets  : tuple (speed_a, speed_b, speed_c, speed_d)
        steps    : nombre de paliers
        delay_ms : attente entre paliers
        forwards : tuple (fwd_a, fwd_b, fwd_c, fwd_d), défaut True×4
        """
        if forwards is None:
            forwards = (True, True, True, True)
        max_t = max(targets)
        step = max(1, max_t // steps)
        for s in range(0, max_t + step, step):
            for m, t, fwd in zip(self.MOTORS, targets, forwards):
                self.run(m, min(s, t), fwd)
            await asyncio.sleep_ms(delay_ms)   # ← libère le scheduler

    # ── Interne ──────────────────────────────────────────────────────────

    def _resolve(self, motor):
        m = motor.upper()
        if m == 'ALL': return list(self.MOTORS)
        if m in _PAIRS: return list(_PAIRS[m])
        if m in _CH: return [m]
        raise ValueError(f"Moteur ou paire '{motor}' inconnu(e).")

    def _stop_all(self):
        for ch_pwm, ch_in1, ch_in2 in _CH.values():
            self._pca.level(ch_pwm, 0)
            self._pca.level(ch_in1, 0)
            self._pca.level(ch_in2, 0)
