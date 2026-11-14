# pico_pins.py — Brochage Waveshare Pico-Sensor-Kit-B (schéma V1.1)
# À copier sur la carte avec tous les modules avant utilisation.
#
# Bus I²C :
#   I²C0 (bus 0) : GPIO8 SDA, GPIO9 SCL
#     → PCA9685 (0x40), EEPROM 24C01 (0x50), SGP40 (0x59),
#       QMI8658 (0x6B), SHTC3 (0x70)
#   I²C1 (bus 1) : GPIO6 SDA, GPIO7 SCL
#     → OLED SSD1327 (0x3D)

# ── Broches numériques ────────────────────────────────────────────────────
D3  = 14     # KEY   — Bouton utilisateur (actif bas, PULL_UP interne)
D6  = 17    # SDA1  — I²C bus 1 (OLED)
D7  = 18    # SCL1  — I²C bus 1
D8  = 33    # SDA0  — I²C bus 0 (capteurs + moteur)
D9  = 34    # SCL0  — I²C bus 0
D10 = 35    # LED   — LED rouge module (PWM possible)
D12 = 37    # BUZ   — Buzzer passif (PWM, fréquence audible)
D15 = 40    # IR_RX — Récepteur infrarouge
D16 = 42    # IR_TX — Émetteur infrarouge
D21 = 5     # SND_D — Sortie numérique microphone (comparateur)
D22 = 6     # RGB   — LED RGB WS2812B onboard (NeoPixel)

# ── Broches analogiques (ADC) ─────────────────────────────────────────────
A1  = 8    # VOL ADJ — Potentiomètre (0–3,3 V)
A2  = 7    # LDR     — Photorésistance (0–3,3 V)
A3  = 9    # SND_A   — Sortie analogique microphone

# ── Alias pratiques ───────────────────────────────────────────────────────
SDA0    = D8
SCL0    = D9
SDA1    = D6
SCL1    = D7
LED_PIN = D10
BUZ_PIN = D12
BTN_PIN = D3
RGB_PIN = D22
IR_RX   = D15
IR_TX   = D16
VOL_PIN = A1
LDR_PIN = A2
SND_PIN = A3
