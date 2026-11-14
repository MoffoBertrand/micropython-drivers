# ssd1327_async.py — Version asynchrone du pilote OLED SSD1327
# À utiliser avec asyncio (MicroPython uasyncio).
#
# Différences avec ssd1327.py (version synchrone) :
#   - _init_display() → coroutine : await asyncio.sleep_ms(100)
#   - create()        → classmethod async
#   - show()          → coroutine : le transfert I²C de 8 Ko dure ~20 ms à 400 kHz
#                        (libère le scheduler pendant ce transfert)
#
# Les méthodes de DESSIN héritées de FrameBuffer restent SYNCHRONES :
#   fill(), text(), rect(), fill_rect(), pixel(), hline(), vline(), blit()…
#   Ces opérations écrivent uniquement en RAM locale — pas de libération
#   du scheduler nécessaire.
#
# RÈGLE D'OR pour l'asyncio :
#   1. Préparer le frame en RAM  → synchrone, rapide
#   2. await oled.show()         → transfère sur I²C, libère le scheduler
#   3. Ne jamais appeler show() plusieurs fois par tâche sans await entre les deux.
#
# Usage :
#   import asyncio, ssd1327_async as oled_mod
#   from machine import Pin, I2C
#
#   i2c  = I2C(1, scl=Pin(7), sda=Pin(6), freq=400_000)
#   oled = await oled_mod.SSD1327.create(i2c)
#
#   async def tache_affichage():
#       while True:
#           oled.fill(0)
#           oled.center_text("Hello", 56, oled_mod.WHITE)
#           await oled.show()          # ← libère ~20 ms au scheduler
#           await asyncio.sleep_ms(100)

import asyncio
import framebuf

ADDR   = 0x3D

# Palette de gris
BLACK  =  0
GRAY2  =  2
GRAY4  =  4
GRAY6  =  6
GRAY8  =  8
GRAY10 = 10
GRAY12 = 12
WHITE  = 15


class SSD1327(framebuf.FrameBuffer):
    """Pilote OLED SSD1327 asynchrone — 128×128, 16 niveaux de gris (I²C 0x3D).

    Hérite de framebuf.FrameBuffer — toutes les méthodes de dessin standard
    restent SYNCHRONES (elles opèrent uniquement en RAM locale) :
        fill(), text(), rect(), fill_rect(), pixel(), hline(), vline(), blit()…

    Seules show() et create() sont des coroutines.

    Constructeur async
    ------------------
        oled = await SSD1327.create(i2c)
    """

    def __init__(self, i2c, addr=ADDR):
        self.width  = 128
        self.height = 128
        self.addr   = addr
        self._i2c   = i2c
        self._tmp   = bytearray(2)
        self.white  = WHITE
        self.black  = BLACK
        self.buffer = bytearray(self.height * self.width // 2)
        super().__init__(self.buffer, self.width, self.height, framebuf.GS4_HMSB)

    @classmethod
    async def create(cls, i2c, addr=ADDR):
        """Crée et initialise l'écran OLED de façon asynchrone.

        Libère le scheduler pendant les 100 ms de stabilisation.
        """
        self = cls(i2c, addr)
        await self._init_display()
        print(f"SSD1327 OK (adresse 0x{addr:02X}, 128×128, 16 gris)")
        return self

    # ── Coroutines ────────────────────────────────────────────────────────

    async def show(self):
        """Transfère le buffer RAM vers l'écran OLED.

        Le transfert I²C de 8192 octets dure ~20 ms à 400 kHz.
        Ce await libère le scheduler pendant toute la durée du transfert,
        permettant à d'autres tâches de s'exécuter.
        """
        self._setwindow(0, 0, 128, 128)
        self._i2c.writeto(self.addr, b'\x40' + self.buffer)
        await asyncio.sleep_ms(0)   # ← céder le contrôle après le transfert

    # ── API publique synchrone ────────────────────────────────────────────

    def contrast(self, level):
        """Règle la luminosité (0–255). Synchrone."""
        self._cmd(0x81)
        self._cmd(max(0, min(255, level)))

    def poweroff(self):
        """Éteint le panneau OLED. Synchrone."""
        self._cmd(0xAE)

    def poweron(self):
        """Rallume le panneau OLED. Synchrone."""
        self._cmd(0xAF)

    def invert(self, invert):
        """Inverse l'affichage. Synchrone."""
        self._cmd(0xA7 if invert else 0xA4)

    def center_text(self, msg, y, color=WHITE):
        """Texte centré horizontalement. Synchrone."""
        x = max(0, (self.width - len(msg) * 8) // 2)
        self.text(msg, x, y, color)

    def hline_gray(self, y, color=GRAY8):
        """Ligne horizontale séparatrice. Synchrone."""
        self.hline(0, y, self.width, color)

    def progress_bar(self, x, y, w, h, pct, fg=WHITE, bg=GRAY4):
        """Barre de progression. Synchrone."""
        self.fill_rect(x, y, w, h, bg)
        filled = max(0, min(w, w * pct // 100))
        if filled:
            self.fill_rect(x, y, filled, h, fg)
        self.rect(x, y, w, h, GRAY8)

    # ── Interne ──────────────────────────────────────────────────────────

    def _cmd(self, cmd):
        self._tmp[0] = 0x00
        self._tmp[1] = cmd
        self._i2c.writeto(self.addr, self._tmp)

    def _setwindow(self, x0, y0, x1, y1):
        self._cmd(0x15)
        self._cmd(x0 // 2)
        self._cmd(x1 // 2 - 1)
        self._cmd(0x75)
        self._cmd(y0)
        self._cmd(y1 - 1)

    async def _init_display(self):
        """Séquence d'initialisation SSD1327 — libère le scheduler pendant 100 ms."""
        cmds = [
            0xAE,
            0x15, 0x00, 0x7F,
            0x75, 0x00, 0x7F,
            0x81, 0x80,
            0xA0, 0x51,
            0xA1, 0x00,
            0xA2, 0x00,
            0xA4,
            0xA8, 0x7F,
            0xB1, 0xF1,
            0xB3, 0x00,
            0xAB, 0x01,
            0xB6, 0x0F,
            0xBE, 0x0F,
            0xBC, 0x08,
            0xD5, 0x62,
            0xFD, 0x12,
        ]
        for c in cmds:
            self._cmd(c)
        await asyncio.sleep_ms(100)   # ← libère le scheduler (stabilisation)
        self._cmd(0xAF)


OLED_1inch5 = SSD1327
