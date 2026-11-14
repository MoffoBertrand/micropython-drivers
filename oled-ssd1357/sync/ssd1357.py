"""
ssd1357.py — Driver MicroPython pour module RGB OLED 0.96" SSD1357
Dimensions  : 64 colonnes x 128 lignes (portrait)
Couleurs    : RGB565 big-endian standard (identique a framebuf.RGB565)
Interface   : SPI hardware
Cible       : ESP32-S3 (MicroPython v1.21+)

Source de reference : OLED_0in96_rgb.py — Waveshare team v1.0 (2023-04-15)

Brochage par defaut :
  GPIO 11 (SCK) -> CLK  |  GPIO 13 (MOSI) -> DIN  |  GPIO 10 (CS) -> CS
  GPIO  9 (DC)  -> DC   |  GPIO  8 (RST)  -> RST   |  3.3V -> VCC

Parametres hardware (source : driver officiel Waveshare) :
  Colonnes SSD1357 : 0x20 -> 0x5F  (decalage physique de 32 dans le ctrl)
  Lignes SSD1357   : 0x00 -> 0x7F
  Remap 0xA0       : 0x60, 0x00   (BGR dans le ctrl + col/row swap)
  StartLine 0xA1   : 0x00
  DisplayOffset 0xA2: 0x00
  MuxRatio 0xCA    : 0x7F

  Note : le remap 0x60 active BGR dans le controleur MAIS getbuffer()
  de Waveshare ecrit les pixels en RGB565 big-endian standard.
  framebuf.RGB565 est donc correct tel quel.

Auteur  : Prof. MOFFO LONLA Bertrand — UB COT / Labo GIA Douala
Version : 6.0.0 — base sur driver officiel Waveshare
"""

import framebuf
import time
from machine import Pin, SPI

# ── Couleurs RGB565 standard (identiques a framebuf.RGB565) ──────────────────
BLACK      = const(0x0000)
WHITE      = const(0xFFFF)
RED        = const(0xF800)
GREEN      = const(0x07E0)
BLUE       = const(0x001F)
YELLOW     = const(0xFFE0)
CYAN       = const(0x07FF)
MAGENTA    = const(0xF81F)
ORANGE     = const(0xFD20)
GRAY       = const(0x8410)
PURPLE     = const(0x8010)
DARK_GREEN = const(0x03E0)
LIGHT_BLUE = const(0x567E)
PINK       = const(0xFC18)


def color565(r, g, b):
    """
    Convertit R, G, B (0-255) -> RGB565 big-endian.
    Equivalent a la formule Waveshare getbuffer() :
      octet_haut = (R & 0xF8) | (G >> 5)
      octet_bas  = ((G << 3) & 0xE0) | (B >> 3)
    """
    return ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)


class SSD1357:
    """
    Driver SSD1357 — RGB OLED 0.96" Waveshare (portrait 64x128).

    Coordonnees framebuffer :
      x in [0, 63]   (gauche -> droite)
      y in [0, 127]  (haut   -> bas)

    Toutes les primitives framebuf (fill, pixel, line, hline, vline,
    rect, fill_rect, text, blit, scroll) sont accessibles directement
    via delegation __getattr__ -> self._fb.
    """

    WIDTH  = 64
    HEIGHT = 128

    # Offset physique des colonnes dans le controleur SSD1357
    # La dalle est couplee aux colonnes 0x20..0x5F du ctrl 128-col
    _COL_START = 0x20
    _COL_END   = 0x5F

    def __init__(self, spi_id=1, sck=11, mosi=13, cs=10,
                 dc=9, rst=8, baudrate=16_000_000):
        self.width  = self.WIDTH
        self.height = self.HEIGHT

        self._cs  = Pin(cs,  Pin.OUT, value=1)
        self._dc  = Pin(dc,  Pin.OUT, value=0)
        self._rst = Pin(rst, Pin.OUT, value=1)

        self._spi = SPI(spi_id, baudrate=baudrate, polarity=0, phase=0,
                        sck=Pin(sck), mosi=Pin(mosi), miso=None)

        # Framebuffer 64x128 x 2 = 16384 octets, RGB565 big-endian
        self._buf = bytearray(self.width * self.height * 2)
        self._fb  = framebuf.FrameBuffer(
                        self._buf, self.width, self.height, framebuf.RGB565)
        self._rotation = 0
        self._init_display()

    # ── Delegation FrameBuffer ───────────────────────────────────────────────
    def __getattr__(self, name):
        if name.startswith('_'):
            raise AttributeError(name)
        return getattr(self._fb, name)

    # ── SPI ──────────────────────────────────────────────────────────────────
    def _write_cmd(self, cmd):
        self._cs(0); self._dc(0)
        self._spi.write(bytearray([cmd]))
        self._cs(1)

    def _write_data(self, data):
        self._cs(0); self._dc(1)
        self._spi.write(bytearray([data]) if isinstance(data, int) else data)
        self._cs(1)

    def _cmd_data(self, cmd, *args):
        self._write_cmd(cmd)
        for b in args:
            self._write_data(b)

    # ── Initialisation (calquee sur Waveshare OLED_0in96_rgb.py) ─────────────
    def _init_display(self):
        # Reset (identique Waveshare : 100ms haut, 100ms bas, 100ms haut)
        self._rst(1); time.sleep_ms(100)
        self._rst(0); time.sleep_ms(100)
        self._rst(1); time.sleep_ms(100)

        self._cmd_data(0xFD, 0x12)        # command lock

        self._write_cmd(0xAE)             # display off

        # Fenetre colonnes : 0x20..0x5F (64 colonnes, offset physique)
        self._cmd_data(0x15, 0x20, 0x5F)
        # Fenetre lignes   : 0x00..0x7F (128 lignes)
        self._cmd_data(0x75, 0x00, 0x7F)

        # Remap : 0x60 = col/row swap + BGR | 0x00 = octet2
        self._cmd_data(0xA0, 0x60, 0x00)

        self._cmd_data(0xA1, 0x00)        # StartLine = 0x00
        self._cmd_data(0xA2, 0x00)        # DisplayOffset = 0x00

        self._cmd_data(0xB1, 0x84)
        self._cmd_data(0xB3, 0x20)
        self._cmd_data(0xB6, 0x01)
        self._cmd_data(0xBB, 0x00)
        self._cmd_data(0xBE, 0x07)
        self._cmd_data(0xC7, 0x0F)
        self._cmd_data(0xC1, 0x32, 0x29, 0x53)  # contrast R,G,B (Waveshare)
        self._cmd_data(0xCA, 0x7F)        # MuxRatio = 0x7F

        time.sleep_ms(100)
        self._write_cmd(0xAF)             # display on

        # Re-armer la fenetre avant ecriture (identique Waveshare)
        self._cmd_data(0x15, 0x20, 0x5F)
        self._cmd_data(0x75, 0x00, 0x7F)
        self._write_cmd(0x5C)             # write RAM

        self._fb.fill(BLACK)
        self.show()

    # ── Controle ─────────────────────────────────────────────────────────────
    def reset(self):
        self._rst(1); time.sleep_ms(100)
        self._rst(0); time.sleep_ms(100)
        self._rst(1); time.sleep_ms(100)

    def power_on(self):   self._write_cmd(0xAF)
    def power_off(self):  self._write_cmd(0xAE)

    def invert(self, state):
        self._write_cmd(0xA7 if state else 0xA6)

    def rotate(self, angle):
        """Rotation 0/90/180/270 via registre REMAP."""
        angle = angle % 360
        if angle not in (0, 90, 180, 270):
            raise ValueError("angle doit etre 0, 90, 180 ou 270")
        # Base 0x60 (col/row swap + BGR) + bits direction
        _remap = {0: 0x60, 90: 0x63, 180: 0x72, 270: 0x71}
        self._rotation = angle
        self._cmd_data(0xA0, _remap[angle], 0x00)

    def get_rotation(self):
        return self._rotation

    def set_contrast(self, r, g, b):
        """Contraste par canal R, G, B (0-255)."""
        self._cmd_data(0xC1, r & 0xFF, g & 0xFF, b & 0xFF)

    def set_master_contrast(self, level):
        """Contraste global 0 (min) ... 15 (max)."""
        self._cmd_data(0xC7, level & 0x0F)

    # ── Show ─────────────────────────────────────────────────────────────────
    def show(self):
        """
        Transfere le framebuffer 64x128 vers la RAM du SSD1357.
        Colonnes : 0x20..0x5F (offset physique Waveshare)
        Lignes   : 0x00..0x7F
        """
        self._cmd_data(0x15, self._COL_START, self._COL_END)
        self._cmd_data(0x75, 0x00, 0x7F)
        self._write_cmd(0x5C)
        self._cs(0); self._dc(1)
        self._spi.write(self._buf)
        self._cs(1)

    def show_region(self, x0, y0, x1, y1):
        """Mise a jour partielle — x0,x1 sont les indices framebuf (0..63)."""
        x0 = max(0, x0); y0 = max(0, y0)
        x1 = min(self.width - 1,  x1)
        y1 = min(self.height - 1, y1)
        # Ajouter l'offset physique sur les colonnes
        self._cmd_data(0x15, x0 + self._COL_START, x1 + self._COL_START)
        self._cmd_data(0x75, y0, y1)
        self._write_cmd(0x5C)
        self._cs(0); self._dc(1)
        row_bytes = (x1 - x0 + 1) * 2
        for row in range(y0, y1 + 1):
            offset = (row * self.width + x0) * 2
            self._spi.write(self._buf[offset: offset + row_bytes])
        self._cs(1)

    # ── Primitives etendues ───────────────────────────────────────────────────
    def draw_circle(self, cx, cy, r, color):
        x, y, err = 0, r, 1 - r
        while x <= y:
            for dx, dy in [(x,y),(y,x),(-x,y),(-y,x),
                           (x,-y),(y,-x),(-x,-y),(-y,-x)]:
                px, py = cx + dx, cy + dy
                if 0 <= px < self.width and 0 <= py < self.height:
                    self._fb.pixel(px, py, color)
            if err < 0: err += 2 * x + 3
            else:       err += 2 * (x - y) + 5; y -= 1
            x += 1

    def fill_circle(self, cx, cy, r, color):
        for dy in range(-r, r + 1):
            dx = int((r * r - dy * dy) ** 0.5)
            self._fb.hline(cx - dx, cy + dy, 2 * dx + 1, color)

    def draw_triangle(self, x0, y0, x1, y1, x2, y2, color):
        self._fb.line(x0, y0, x1, y1, color)
        self._fb.line(x1, y1, x2, y2, color)
        self._fb.line(x2, y2, x0, y0, color)

    def draw_rounded_rect(self, x, y, w, h, r, color):
        self._fb.hline(x + r, y,         w - 2*r, color)
        self._fb.hline(x + r, y + h - 1, w - 2*r, color)
        self._fb.vline(x,         y + r, h - 2*r, color)
        self._fb.vline(x + w - 1, y + r, h - 2*r, color)
        for i in range(r + 1):
            j = int((r*r - i*i) ** 0.5)
            self._fb.pixel(x + r - i,         y + r - j,         color)
            self._fb.pixel(x + w - 1 - r + i, y + r - j,         color)
            self._fb.pixel(x + r - i,         y + h - 1 - r + j, color)
            self._fb.pixel(x + w - 1 - r + i, y + h - 1 - r + j, color)

    def draw_text_large(self, text, x, y, scale, color):
        """Texte agrandi par facteur scale (police native 8x8)."""
        tw = 8 * len(text); th = 8
        tb = bytearray(tw * th * 2)
        tf = framebuf.FrameBuffer(tb, tw, th, framebuf.RGB565)
        tf.fill(BLACK); tf.text(text, 0, 0, color)
        for sy in range(th):
            for sx in range(tw):
                c = tf.pixel(sx, sy)
                if c != BLACK:
                    self._fb.fill_rect(x + sx * scale,
                                       y + sy * scale,
                                       scale, scale, c)

    def gradient_fill(self, x, y, w, h, c_top, c_bot):
        """Degrade vertical lineaire."""
        r0=(c_top>>11)&0x1F;  g0=(c_top>>5)&0x3F;  b0=c_top&0x1F
        r1=(c_bot>>11)&0x1F;  g1=(c_bot>>5)&0x3F;  b1=c_bot&0x1F
        for row in range(h):
            t = row / max(h - 1, 1)
            c = (int(r0+(r1-r0)*t) << 11) | \
                (int(g0+(g1-g0)*t) <<  5) | \
                 int(b0+(b1-b0)*t)
            self._fb.hline(x, y + row, w, c)

    def draw_progress_bar(self, x, y, w, h, pct,
                          fg=GREEN, bg=GRAY, border=WHITE):
        """Barre de progression (0.0 ... 100.0)."""
        pct = max(0.0, min(100.0, pct))
        f = int(w * pct / 100.0)
        self._fb.rect(x, y, w, h, border)
        if f > 2:     self._fb.fill_rect(x + 1, y + 1, f - 2, h - 2, fg)
        if f < w - 2: self._fb.fill_rect(x + f, y + 1, w - f - 1, h - 2, bg)

    def draw_image(self, x, y, w, h, data):
        """Image brute RGB565 (bytearray w*h*2 octets)."""
        img = framebuf.FrameBuffer(bytearray(data), w, h, framebuf.RGB565)
        self._fb.blit(img, x, y)

    def draw_bitmap_mono(self, x, y, bitmap, w, h, fg, bg=-1):
        """Bitmap monochrome 1bpp MSB-first. bg=-1 = transparent."""
        for row in range(h):
            for col in range(w):
                idx = (row * w + col) // 8
                bit = 7 - ((row * w + col) % 8)
                if bitmap[idx] & (1 << bit):
                    self._fb.pixel(x + col, y + row, fg)
                elif bg >= 0:
                    self._fb.pixel(x + col, y + row, bg)

    def clear(self, color=BLACK):
        """Efface et rafraichit."""
        self._fb.fill(color); self.show()

    def __repr__(self):
        return "SSD1357 RGB OLED {}x{} px v6.0.0".format(
               self.width, self.height)
