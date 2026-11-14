# tb6612.py — Pilote MicroPython pour 2× TB6612FNG via PCA9685
# Toshiba TB6612FNG : double H-bridge, 1,2 A continu / 3,2 A crête par canal
#
# La carte Waveshare Pico-Sensor-Kit-B embarque DEUX TB6612FNG (TB1 et TB2),
# chacun contrôlant 2 moteurs DC — soit 4 moteurs indépendants au total.
#
# ── Mapping PCA9685 → TB6612FNG (schéma V1.1) ────────────────────────────
#
#   PCA ch   Signal      TB chip   Moteur
#   ───────────────────────────────────────
#   ch  0  → PWMA        TB1       Moteur A  (vitesse)
#   ch  1  → AIN1        TB1       Moteur A  (direction bit 1)
#   ch  2  → AIN2        TB1       Moteur A  (direction bit 2)
#   ch  3  → PWMB        TB1       Moteur B  (vitesse)   ← ch3, pas ch5 !
#   ch  4  → BIN1        TB1       Moteur B  (direction bit 1)
#   ch  5  → BIN2        TB1       Moteur B  (direction bit 2)
#   ch  6  → PWMC        TB2       Moteur C  (vitesse)
#   ch  7  → CIN1        TB2       Moteur C  (direction bit 1)
#   ch  8  → CIN2        TB2       Moteur C  (direction bit 2)
#   ch  9  → PWMD        TB2       Moteur D  (vitesse)
#   ch 10  → DIN1        TB2       Moteur D  (direction bit 1)
#   ch 11  → DIN2        TB2       Moteur D  (direction bit 2)
#
# ── Table de vérité (par moteur) ─────────────────────────────────────────
#   xIN1=1, xIN2=0  → avant (forward)
#   xIN1=0, xIN2=1  → arrière (backward)
#   xIN1=1, xIN2=1  → frein actif (brake)
#   PWMx=0          → roue libre (stop)
#
# ── Usage typique ─────────────────────────────────────────────────────────
#   from machine import Pin, I2C
#   from pico_pins import D8, D9
#   import pca9685, tb6612
#
#   i2c = I2C(0, sda=Pin(D8), scl=Pin(D9), freq=400_000)
#   pca = pca9685.PCA9685(i2c)
#   pca.freq(100)
#   mot = tb6612.TB6612(pca)
#
#   mot.run('A', 75)                  # Moteur A, 75 %, avant
#   mot.run('B', 60, forward=False)   # Moteur B, 60 %, arrière
#   mot.run('C', 80)                  # Moteur C, 80 %, avant
#   mot.run('D', 50, forward=False)   # Moteur D, 50 %, arrière
#   mot.dual_run('AB', 70, 70)        # A+B ensemble, même vitesse
#   mot.quad_run(60, 60, 60, 60)      # 4 moteurs simultanément
#   mot.forward(70)                   # robot 4WD avance tout droit
#   mot.stop('all')                   # Arrêt roue libre tous
#   mot.brake('all')                  # Freinage actif tous

import time

# ── Mapping canaux PCA9685 ────────────────────────────────────────────────
# Chaque entrée : (ch_pwm, ch_in1, ch_in2)
_CH = {
    'A': (0, 1, 2),    # TB1 : PWMA, AIN1, AIN2  (pins 23, 21, 22)
    'B': (3, 4, 5),    # TB1 : PWMB, BIN1, BIN2  (pins 15, 17, 16)  ch3=PWMB !
    'C': (6, 7, 8),    # TB2 : PWMC, CIN1, CIN2
    'D': (9, 10, 11),  # TB2 : PWMD, DIN1, DIN2
}

# Paires pour commandes combinées
_PAIRS = {
    'AB': ('A', 'B'),   # TB1 — ex: roues gauche
    'CD': ('C', 'D'),   # TB2 — ex: roues droite
    'AC': ('A', 'C'),   # Avant gauche + avant droite
    'BD': ('B', 'D'),   # Arrière gauche + arrière droite
}


class TB6612:
    """Pilote pour 2× TB6612FNG (4 moteurs DC) commandés via PCA9685.

    Moteurs disponibles : 'A', 'B', 'C', 'D'
    Paires               : 'AB', 'CD', 'AC', 'BD'
    Tous                 : 'all'

    Paramètres
    ----------
    pca : pca9685.PCA9685
        Instance déjà initialisée avec pca.freq() appelé.
    """

    MOTORS = ('A', 'B', 'C', 'D')

    def __init__(self, pca):
        self._pca = pca
        self._stop_all()    # état sûr au démarrage
        print("TB6612 OK — 4 moteurs (A, B via TB1 | C, D via TB2)")

    # ── API principale ────────────────────────────────────────────────────

    def run(self, motor, speed, forward=True):
        """Lance un moteur à la vitesse donnée dans le sens choisi.

        Paramètres
        ----------
        motor   : 'A', 'B', 'C' ou 'D'
        speed   : 0–100 (% de la vitesse maximale)
        forward : True = avant, False = arrière (défaut True)
        """
        motor = motor.upper()
        if motor not in _CH:
            raise ValueError(f"Moteur '{motor}' inconnu. Utiliser 'A', 'B', 'C' ou 'D'.")
        ch_pwm, ch_in1, ch_in2 = _CH[motor]
        self._pca.duty(ch_pwm, max(0, min(100, speed)))
        self._pca.level(ch_in1, 1 if forward else 0)
        self._pca.level(ch_in2, 0 if forward else 1)

    def stop(self, motor='all'):
        """Arrêt roue libre : PWM=0, le moteur peut tourner librement.

        Paramètres
        ----------
        motor : 'A'|'B'|'C'|'D', paire 'AB'|'CD'|'AC'|'BD', ou 'all'
        """
        for m in self._resolve(motor):
            self._pca.duty(_CH[m][0], 0)

    def brake(self, motor='all'):
        """Freinage actif : IN1=IN2=1, arrêt électromécanique immédiat.

        Paramètres
        ----------
        motor : 'A'|'B'|'C'|'D', paire 'AB'|'CD'|'AC'|'BD', ou 'all'
        """
        for m in self._resolve(motor):
            ch_pwm, ch_in1, ch_in2 = _CH[m]
            self._pca.duty(ch_pwm, 0)
            self._pca.level(ch_in1, 1)
            self._pca.level(ch_in2, 1)

    # ── Commandes multi-moteurs ───────────────────────────────────────────

    def dual_run(self, pair, speed1, speed2, forward1=True, forward2=True):
        """Commande simultanée d'une paire de moteurs.

        Paramètres
        ----------
        pair     : 'AB', 'CD', 'AC' ou 'BD'
        speed1   : vitesse du 1er moteur de la paire (0–100 %)
        speed2   : vitesse du 2e moteur de la paire (0–100 %)
        forward1 : sens du 1er moteur (défaut True)
        forward2 : sens du 2e moteur (défaut True)

        Exemples
        --------
        mot.dual_run('AB', 70, 70)               # A+B à 70 % en avant
        mot.dual_run('AB', 70, 70, True, False)  # pivot sur TB1
        mot.dual_run('CD', 60, 40)               # vitesses asymétriques TB2
        """
        pair = pair.upper()
        if pair not in _PAIRS:
            raise ValueError(f"Paire '{pair}' inconnue. Utiliser 'AB', 'CD', 'AC' ou 'BD'.")
        m1, m2 = _PAIRS[pair]
        self.run(m1, speed1, forward1)
        self.run(m2, speed2, forward2)

    def quad_run(self, speed_a, speed_b, speed_c, speed_d,
                 fwd_a=True, fwd_b=True, fwd_c=True, fwd_d=True):
        """Commande simultanée des 4 moteurs A, B, C et D.

        Paramètres
        ----------
        speed_a/b/c/d : vitesses 0–100 % pour chaque moteur
        fwd_a/b/c/d   : sens de rotation (True=avant, défaut True)

        Exemples
        --------
        mot.quad_run(70, 70, 70, 70)                      # tout droit
        mot.quad_run(40, 70, 40, 70)                      # virage gauche doux
        mot.quad_run(70, 70, 70, 70, True, False, True, False)  # pivot
        """
        self.run('A', speed_a, fwd_a)
        self.run('B', speed_b, fwd_b)
        self.run('C', speed_c, fwd_c)
        self.run('D', speed_d, fwd_d)

    def ramp(self, motor, target, steps=20, delay_ms=50, forward=True):
        """Démarrage progressif vers la vitesse cible (protège la mécanique).

        Paramètres
        ----------
        motor    : 'A', 'B', 'C' ou 'D'
        target   : vitesse cible 0–100 %
        steps    : nombre de paliers (défaut 20)
        delay_ms : attente entre paliers en ms (défaut 50 ms)
        forward  : sens de rotation
        """
        step = max(1, target // steps)
        for spd in range(0, target + step, step):
            self.run(motor, min(spd, target), forward)
            time.sleep_ms(delay_ms)

    def ramp_quad(self, targets, steps=20, delay_ms=50, forwards=None):
        """Démarrage progressif simultané des 4 moteurs.

        Paramètres
        ----------
        targets  : tuple (speed_a, speed_b, speed_c, speed_d)
        steps    : nombre de paliers
        delay_ms : attente entre paliers
        forwards : tuple (fwd_a, fwd_b, fwd_c, fwd_d), défaut (True, True, True, True)

        Exemple — démarrage 4WD en douceur :
            mot.ramp_quad((80, 80, 80, 80), steps=30)
        """
        if forwards is None:
            forwards = (True, True, True, True)
        max_t = max(targets)
        step = max(1, max_t // steps)
        for s in range(0, max_t + step, step):
            for m, t, fwd in zip(self.MOTORS, targets, forwards):
                self.run(m, min(s, t), fwd)
            time.sleep_ms(delay_ms)

    # ── Raccourcis navigation robot 4WD ──────────────────────────────────

    def forward(self, speed=70):
        """Robot 4WD avance tout droit."""
        self.quad_run(speed, speed, speed, speed)

    def backward(self, speed=70):
        """Robot 4WD recule tout droit."""
        self.quad_run(speed, speed, speed, speed,
                      False, False, False, False)

    def turn_left(self, speed=70, inner=30):
        """Virage à gauche : moteurs côté gauche (A, C) ralentis."""
        self.quad_run(inner, speed, inner, speed)

    def turn_right(self, speed=70, inner=30):
        """Virage à droite : moteurs côté droit (B, D) ralentis."""
        self.quad_run(speed, inner, speed, inner)

    def spin_left(self, speed=60):
        """Rotation sur place sens anti-horaire (A,C reculent, B,D avancent)."""
        self.quad_run(speed, speed, speed, speed,
                      False, True, False, True)

    def spin_right(self, speed=60):
        """Rotation sur place sens horaire (A,C avancent, B,D reculent)."""
        self.quad_run(speed, speed, speed, speed,
                      True, False, True, False)

    # ── Interne ──────────────────────────────────────────────────────────

    def _resolve(self, motor):
        """Résout un identifiant en liste de moteurs individuels."""
        m = motor.upper()
        if m == 'ALL':
            return list(self.MOTORS)
        if m in _PAIRS:
            return list(_PAIRS[m])
        if m in _CH:
            return [m]
        raise ValueError(f"Moteur ou paire '{motor}' inconnu(e).")

    def _stop_all(self):
        """Met tous les canaux à 0 (état sûr au démarrage)."""
        for ch_pwm, ch_in1, ch_in2 in _CH.values():
            self._pca.level(ch_pwm, 0)
            self._pca.level(ch_in1, 0)
            self._pca.level(ch_in2, 0)
