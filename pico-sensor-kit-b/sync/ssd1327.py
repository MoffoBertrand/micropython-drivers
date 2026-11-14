# ssd1327.py — Pilote MicroPython pour OLED SSD1327 1,5" Waveshare
# 128×128 pixels, 16 niveaux de gris (format GS4_HMSB)
# I²C bus 1, adresse fixe 0x3D (BS1=GND, schéma V1.1)
#
# Basé sur le driver officiel Waveshare (V1.0, 2022-03-15).
# Améliorations :
#   - L'objet I2C est passé en paramètre (cohérence avec les autres modules)
#   - Alias de couleur : BLACK=0, WHITE=15 + palette de gris
#   - Méthodes utilitaires : contrast(), poweroff(), poweron()
#   - Correction faute de frappe 'balck' → 'black'
#   - Documentation des registres SSD1327
#
# Notes écran :
#   Format GS4_HMSB : chaque octet contient 2 pixels (nibble haut = pixel gauche)
#   Couleur 0 = noir, 15 = blanc, intermédiaires = niveaux de gris
#   La colonne matérielle = pixel_x // 2 (d'où les divisions par 2 dans setwindows)
#
# Usage :
#   from machine import Pin, I2C
#   import ssd1327
#   i2c  = I2C(1, scl=Pin(7), sda=Pin(6), freq=400_000)
#   oled = ssd1327.SSD1327(i2c)
#   oled.fill(0)
#   oled.text("Bonjour", 10, 10, ssd1327.WHITE)
#   oled.rect(0, 0, 128, 128, ssd1327.GRAY8)
#   oled.show()

import framebuf
import time

# ── Adresse I²C ───────────────────────────────────────────────────────────
ADDR = 0x3D   # BS1=GND sur le schéma Waveshare V1.1

# ── Palette de gris (0–15) ────────────────────────────────────────────────
BLACK  =  0    # éteint
GRAY2  =  2
GRAY4  =  4
GRAY6  =  6
GRAY8  =  8    # gris moyen
GRAY10 = 10
GRAY12 = 12
WHITE  = 15    # pleine luminosité


class SSD1327(framebuf.FrameBuffer):
    """Pilote OLED SSD1327 128×128 16 niveaux de gris (I²C 0x3D).

    Hérite de framebuf.FrameBuffer — toutes les méthodes de dessin standard
    sont disponibles : fill(), pixel(), text(), line(), rect(), fill_rect(),
    ellipse(), poly(), blit().

    Paramètres
    ----------
    i2c  : objet machine.I2C déjà initialisé (bus 1, GPIO6/7)
    addr : adresse I²C (défaut 0x3D)
    """

    def __init__(self, i2c, addr=ADDR):
        self.width  = 128
        self.height = 128
        self.addr   = addr
        self._i2c   = i2c
        self._tmp   = bytearray(2)

        # Couleurs pratiques accessibles comme attributs d'instance
        self.white = WHITE
        self.black = BLACK

        # Buffer : 128×128 pixels × 4 bits = 8192 octets
        self.buffer = bytearray(self.height * self.width // 2)
        super().__init__(self.buffer, self.width, self.height, framebuf.GS4_HMSB)

        self._init_display()
        print(f"SSD1327 OK (adresse 0x{addr:02X}, 128×128, 16 gris)")

    # ── API publique ──────────────────────────────────────────────────────

    def show(self):
        """Transfère le buffer en RAM vers l'écran OLED (affiche le contenu)."""
        self._setwindow(0, 0, 128, 128)
        self._i2c.writeto(self.addr, b'\x40' + self.buffer)

    def contrast(self, level):
        """Règle la luminosité de l'écran (0 = minimum, 255 = maximum).

        Paramètres
        ----------
        level : int 0–255
        """
        self._cmd(0x81)
        self._cmd(max(0, min(255, level)))

    def poweroff(self):
        """Éteint le panneau OLED (basse consommation). Le buffer est conservé."""
        self._cmd(0xAE)

    def poweron(self):
        """Rallume le panneau OLED."""
        self._cmd(0xAF)

    def invert(self, invert):
        """Inverse l'affichage (True = inversé, False = normal)."""
        self._cmd(0xA7 if invert else 0xA4)

    # ── Méthodes utilitaires ──────────────────────────────────────────────

    def center_text(self, msg, y, color=WHITE):
        """Affiche un texte centré horizontalement à la ligne y.

        Paramètres
        ----------
        msg   : chaîne à afficher (police 8×8 px)
        y     : position verticale en pixels
        color : niveau de gris 0–15 (défaut WHITE=15)
        """
        x = max(0, (self.width - len(msg) * 8) // 2)
        self.text(msg, x, y, color)

    def hline_gray(self, y, color=GRAY8):
        """Trace une ligne horizontale complète (barre de séparation)."""
        self.hline(0, y, self.width, color)

    def progress_bar(self, x, y, w, h, pct, fg=WHITE, bg=GRAY4):
        """Dessine une barre de progression.

        Paramètres
        ----------
        x, y : coin supérieur gauche
        w, h : largeur et hauteur totales
        pct  : pourcentage rempli (0–100)
        fg   : couleur remplie (défaut WHITE)
        bg   : couleur fond (défaut GRAY4)
        """
        self.fill_rect(x, y, w, h, bg)
        filled = max(0, min(w, w * pct // 100))
        if filled:
            self.fill_rect(x, y, filled, h, fg)
        self.rect(x, y, w, h, GRAY8)

    # ── Interne ──────────────────────────────────────────────────────────

    def _cmd(self, cmd):
        """Envoie une commande sur l'I²C (octet de contrôle 0x00)."""
        self._tmp[0] = 0x00
        self._tmp[1] = cmd
        self._i2c.writeto(self.addr, self._tmp)

    def _setwindow(self, x0, y0, x1, y1):
        """Définit la fenêtre de destination pour l'écriture des données."""
        self._cmd(0x15)          # set column address
        self._cmd(x0 // 2)       # start col (2 pixels/octet)
        self._cmd(x1 // 2 - 1)  # end col
        self._cmd(0x75)          # set row address
        self._cmd(y0)            # start row
        self._cmd(y1 - 1)        # end row

    def _init_display(self):
        """Séquence d'initialisation SSD1327 — source Waveshare officielle."""
        cmds = [
            0xAE,               # Display OFF (veille)
            0x15, 0x00, 0x7F,   # Set Column Address 0–127
            0x75, 0x00, 0x7F,   # Set Row Address 0–127
            0x81, 0x80,         # Contrast Control
            0xA0, 0x51,         # Segment Remap (rotation 180°)
            0xA1, 0x00,         # Display Start Line 0
            0xA2, 0x00,         # Display Offset 0
            0xA4,               # Normal Display (pas d'inversion)
            0xA8, 0x7F,         # Multiplex Ratio 1/128
            0xB1, 0xF1,         # Phase Length
            0xB3, 0x00,         # Display Clock Divide Ratio (100 Hz)
            0xAB, 0x01,         # Function Selection A — internal VDD
            0xB6, 0x0F,         # Second Pre-charge Period
            0xBE, 0x0F,         # VCOMH Voltage
            0xBC, 0x08,         # Pre-charge Voltage
            0xD5, 0x62,         # Function Selection B
            0xFD, 0x12,         # Command Lock (unlocked)
        ]
        for c in cmds:
            self._cmd(c)
        time.sleep_ms(100)
        self._cmd(0xAF)         # Display ON


# ── Alias de compatibilité avec l'ancien nom Waveshare ────────────────────
OLED_1inch5 = SSD1327
