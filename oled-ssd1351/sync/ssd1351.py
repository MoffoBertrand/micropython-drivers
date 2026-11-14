"""
ssd1351.py — Driver MicroPython complet pour le module RGB OLED 1.5" SSD1351
=============================================================================
Module  : Waveshare 1.5inch RGB OLED Module
Taille  : 1,5 pouce — Resolution : 128 x 128 pixels (carre)
Couleurs : RGB565 standard — 65 536 couleurs
Controleur : SSD1351 (Solomon Systech)
Interface  : SPI 4 fils uniquement (SPI only — pas d'I2C sur ce module)
Cible   : ESP32-S3 (MicroPython v1.21+)

Source de reference : OLED_Driver.py — Waveshare team (GitHub)
https://github.com/waveshare/1.5inch-RGB-OLED-Module

Brochage par defaut (modifiable via constructeur) :
  ESP32-S3 GPIO   ->  Module
  GPIO 11 (SCK)   ->  CLK
  GPIO 13 (MOSI)  ->  DIN
  GPIO 10 (CS)    ->  CS
  GPIO  9 (DC)    ->  DC
  GPIO  8 (RST)   ->  RST
  3.3 V           ->  VCC
  GND             ->  GND

Avantages du SSD1351 vs SSD1357 (0.96") :
  - Resolution 128x128 (carre) vs 64x128 (portrait)
  - Pas d'offset physique de colonnes (adressage direct 0x00..0x7F)
  - Pas de StartLine/MuxRatio a calibrer empiriquement
  - Sequenced d'init standard bien documentee
  - Buffer 32 Ko vs 16 Ko (128x128x2)
  - Supporte les deux profondeurs 65K et 262K couleurs

Architecture : COMPOSITION — self._fb = framebuf.FrameBuffer(RGB565)
  Les primitives graphiques (fill, pixel, text, line, rect, fill_rect,
  blit, scroll) sont deléguees via __getattr__ -> self._fb.
  Seul show() et show_region() accedent au bus SPI.

Auteur  : Prof. MOFFO LONLA Bertrand — UB COT / Labo GIA Douala
Version : 1.0.0
"""

import framebuf
import time
from machine import Pin, SPI

# ── Couleurs RGB565 standard ─────────────────────────────────────────────────
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
BROWN      = const(0xA145)
GOLD       = const(0xFEA0)
SILVER     = const(0xC618)
NAVY       = const(0x000F)
MAROON     = const(0x7800)
OLIVE      = const(0x7BE0)
TEAL       = const(0x0410)


def color565(r, g, b):
    """
    Convertit R, G, B (0-255) -> RGB565 16 bits.
    Compatible avec framebuf.RGB565 (big-endian).
    """
    return ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)


def hsv_to_rgb565(h, s, v):
    """
    Convertit teinte/saturation/valeur -> RGB565.
    h : 0.0 .. 360.0 (teinte)
    s : 0.0 .. 1.0   (saturation)
    v : 0.0 .. 1.0   (valeur/luminosite)
    """
    if s == 0.0:
        c = int(v * 255)
        return color565(c, c, c)
    h = h % 360
    i = int(h / 60)
    f = (h / 60) - i
    p = int(v * (1 - s) * 255)
    q = int(v * (1 - s * f) * 255)
    t = int(v * (1 - s * (1 - f)) * 255)
    vi = int(v * 255)
    if i == 0: return color565(vi, t,  p)
    if i == 1: return color565(q,  vi, p)
    if i == 2: return color565(p,  vi, t)
    if i == 3: return color565(p,  q,  vi)
    if i == 4: return color565(t,  p,  vi)
    return color565(vi, p, q)


def blend(c1, c2, t):
    """
    Melange lineaire de deux couleurs RGB565.
    t : 0.0 (c1 pur) .. 1.0 (c2 pur)
    """
    r1=(c1>>11)&0x1F; g1=(c1>>5)&0x3F; b1=c1&0x1F
    r2=(c2>>11)&0x1F; g2=(c2>>5)&0x3F; b2=c2&0x1F
    r=int(r1+(r2-r1)*t); g=int(g1+(g2-g1)*t); b=int(b1+(b2-b1)*t)
    return (r<<11)|(g<<5)|b


# ── Commandes SSD1351 (source : Waveshare OLED_Driver.py) ───────────────────
_CMD_SETCOLUMN      = const(0x15)
_CMD_SETROW         = const(0x75)
_CMD_WRITERAM       = const(0x5C)
_CMD_READRAM        = const(0x5D)
_CMD_SETREMAP       = const(0xA0)
_CMD_STARTLINE      = const(0xA1)
_CMD_DISPLAYOFFSET  = const(0xA2)
_CMD_DISPLAYALLOFF  = const(0xA4)
_CMD_DISPLAYALLON   = const(0xA5)
_CMD_NORMALDISPLAY  = const(0xA6)
_CMD_INVERTDISPLAY  = const(0xA7)
_CMD_FUNCTIONSELECT = const(0xAB)
_CMD_DISPLAYOFF     = const(0xAE)
_CMD_DISPLAYON      = const(0xAF)
_CMD_PRECHARGE      = const(0xB1)
_CMD_DISPLAYENHANCE = const(0xB2)
_CMD_CLOCKDIV       = const(0xB3)
_CMD_SETVSL         = const(0xB4)
_CMD_SETGPIO        = const(0xB5)
_CMD_PRECHARGE2     = const(0xB6)
_CMD_SETGRAY        = const(0xB8)
_CMD_USELUT         = const(0xB9)
_CMD_PRECHARGELEVEL = const(0xBB)
_CMD_VCOMH          = const(0xBE)
_CMD_CONTRASTABC    = const(0xC1)
_CMD_CONTRASTMASTER = const(0xC7)
_CMD_MUXRATIO       = const(0xCA)
_CMD_COMMANDLOCK    = const(0xFD)
_CMD_HORIZSCROLL    = const(0x96)
_CMD_STOPSCROLL     = const(0x9E)
_CMD_STARTSCROLL    = const(0x9F)


class SSD1351:
    """
    Driver SSD1351 — RGB OLED 1.5" Waveshare (128x128 px, RGB565).

    Coordonnees framebuffer :
      x in [0, 127]  (gauche -> droite)
      y in [0, 127]  (haut   -> bas)

    Toutes les primitives framebuf (fill, pixel, line, hline, vline,
    rect, fill_rect, text, blit, scroll) sont disponibles directement
    via delegation __getattr__ -> self._fb.

    Primitives etendues :
      draw_circle, fill_circle, draw_triangle, draw_rounded_rect,
      draw_text_large, gradient_fill, gradient_fill_h,
      draw_progress_bar, draw_image, draw_bitmap_mono,
      draw_arc, fill_arc, draw_polygon, fill_polygon,
      draw_cross, draw_diamond, fill_diamond,
      draw_checkerboard, draw_sine_wave,
      fade_in, fade_out, scroll_text
    """

    WIDTH  = 128
    HEIGHT = 128

    def __init__(self, spi_id=1, sck=11, mosi=13, cs=10,
                 dc=9, rst=8, baudrate=20_000_000):
        """
        Parametres
        ----------
        spi_id  : bus SPI MicroPython (1 par defaut sur ESP32-S3)
        sck     : GPIO horloge SPI
        mosi    : GPIO donnees SPI (DIN)
        cs      : GPIO Chip Select (actif bas)
        dc      : GPIO Data/Command (0=cmd, 1=data)
        rst     : GPIO Reset (actif bas)
        baudrate: frequence SPI en Hz (20 MHz recommande)
        """
        self.width  = self.WIDTH
        self.height = self.HEIGHT

        # Broches
        self._cs  = Pin(cs,  Pin.OUT, value=1)
        self._dc  = Pin(dc,  Pin.OUT, value=0)
        self._rst = Pin(rst, Pin.OUT, value=1)

        # Bus SPI
        self._spi = SPI(spi_id, baudrate=baudrate, polarity=0, phase=0,
                        sck=Pin(sck), mosi=Pin(mosi), miso=None)

        # Framebuffer 128x128 x 2 = 32 768 octets (32 Ko), RGB565
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

    # ── SPI bas niveau ────────────────────────────────────────────────────────
    def _write_cmd(self, cmd):
        self._cs(0); self._dc(0)
        self._spi.write(bytearray([cmd]))
        self._cs(1)

    def _write_data(self, data):
        self._cs(0); self._dc(1)
        self._spi.write(bytearray([data]) if isinstance(data, int) else data)
        self._cs(1)

    def _cmd_data(self, cmd, *args):
        """Envoie une commande suivie de N octets de donnees."""
        self._write_cmd(cmd)
        for b in args:
            self._write_data(b)

    # ── Initialisation (source : Waveshare OLED_Driver.py) ───────────────────
    def _init_display(self):
        """
        Sequence d'initialisation du SSD1351.
        Identique a la sequence officielle Waveshare.
        """
        # Reset materiel
        self._rst(1); time.sleep_ms(100)
        self._rst(0); time.sleep_ms(100)
        self._rst(1); time.sleep_ms(100)

        # Deverrouillage (deux commandes obligatoires)
        self._cmd_data(_CMD_COMMANDLOCK, 0x12)   # unlock
        self._cmd_data(_CMD_COMMANDLOCK, 0xB1)   # unlock commandes avancees

        self._write_cmd(_CMD_DISPLAYOFF)          # display off pendant init

        # Horloge : diviseur=1, frequence oscillateur=0xF
        self._cmd_data(_CMD_CLOCKDIV,    0xF1)

        # Mux ratio : 127 (128 lignes actives)
        self._cmd_data(_CMD_MUXRATIO,    0x7F)

        # Re-mappage et format couleur
        # 0x74 = 0b01110100 :
        #   bit0=0 : adressage colonne gauche->droite
        #   bit1=0 : pas de swap nibbles
        #   bit2=1 : ordre couleur BGR
        #   bit4=1 : balayage COM bas->haut (haut de l'ecran = ligne 0)
        #   bit5=1 : split COM odd/even
        #   bit6=1 : mode couleur 65K (RGB565)
        self._cmd_data(_CMD_SETREMAP,    0x74)

        # Ligne de depart : 0
        self._cmd_data(_CMD_STARTLINE,   0x00)

        # Offset d'affichage : 0
        self._cmd_data(_CMD_DISPLAYOFFSET, 0x00)

        # GPIO
        self._cmd_data(_CMD_SETGPIO,     0x00)

        # Fonction : VDD interne
        self._cmd_data(_CMD_FUNCTIONSELECT, 0x01)

        # VSL
        self._cmd_data(_CMD_SETVSL,      0xA0, 0xB5, 0x55)

        # Contraste R, G, B
        self._cmd_data(_CMD_CONTRASTABC, 0xC8, 0x80, 0xC8)

        # Contraste maitre : 0x0F = maximum
        self._cmd_data(_CMD_CONTRASTMASTER, 0x0F)

        # Amelioration affichage
        self._cmd_data(_CMD_DISPLAYENHANCE, 0xA4, 0x00, 0x00)

        # Pre-charge 1 et 2
        self._cmd_data(_CMD_PRECHARGE,   0x32)
        self._cmd_data(_CMD_PRECHARGE2,  0x01)

        # Niveau pre-charge
        self._cmd_data(_CMD_PRECHARGELEVEL, 0x17)

        # VCOMH
        self._cmd_data(_CMD_VCOMH,       0x05)

        # Affichage normal (non inverse)
        self._write_cmd(_CMD_NORMALDISPLAY)

        time.sleep_ms(100)

        # Effacer en noir et allumer
        self._fb.fill(BLACK)
        self.show()
        self._write_cmd(_CMD_DISPLAYON)

    # ── Controle affichage ────────────────────────────────────────────────────
    def reset(self):
        """Reset materiel du module."""
        self._rst(1); time.sleep_ms(100)
        self._rst(0); time.sleep_ms(100)
        self._rst(1); time.sleep_ms(100)

    def power_on(self):
        """Allume le panneau OLED."""
        self._write_cmd(_CMD_DISPLAYON)

    def power_off(self):
        """Eteint le panneau OLED (memoire RAM conservee)."""
        self._write_cmd(_CMD_DISPLAYOFF)

    def invert(self, state):
        """Inverse les couleurs (True = inverse)."""
        self._write_cmd(_CMD_INVERTDISPLAY if state else _CMD_NORMALDISPLAY)

    def all_on(self):
        """Allume tous les pixels (blanc — test)."""
        self._write_cmd(_CMD_DISPLAYALLON)

    def all_off(self):
        """Eteint tous les pixels (noir — test)."""
        self._write_cmd(_CMD_DISPLAYALLOFF)

    def rotate(self, angle):
        """
        Rotation de l'affichage via le registre SETREMAP (0xA0).

        Le registre 0xA0 du SSD1351 controle l'ordre de balayage
        des colonnes et des lignes directement dans le controleur.
        Aucun surcoût CPU a chaque show().

        angle : 0 / 90 / 180 / 270 (degres)

        Table de bits (octet 0xA0) :
          Bit 0 : direction colonne   (0=G->D, 1=D->G)
          Bit 1 : swap nibbles        (0=non,  1=oui)
          Bit 2 : ordre BGR           (1=BGR fixe)
          Bit 4 : direction scan COM  (0=haut->bas, 1=bas->haut)
          Bit 5 : split COM odd/even  (1=actif)
          Bit 6 : profondeur couleur  (1=65K, 0=262K)

        Valeurs calculees :
          0°   -> 0x74  (base : BGR + split + 65K)
          90°  -> 0x77  (+ col_inv + com_inv)
          180° -> 0x76  (+ col_inv)
          270° -> 0x75  (+ com_inv)
        """
        angle = angle % 360
        if angle not in (0, 90, 180, 270):
            raise ValueError("angle doit etre 0, 90, 180 ou 270")
        _remap = {0: 0x74, 90: 0x77, 180: 0x76, 270: 0x75}
        self._rotation = angle
        self._cmd_data(_CMD_SETREMAP, _remap[angle])

    def get_rotation(self):
        """Retourne l'angle de rotation courant (0 / 90 / 180 / 270)."""
        return self._rotation

    def set_contrast(self, r, g, b):
        """
        Ajuste le contraste individuel des sous-pixels.
        r, g, b : 0 (min) .. 255 (max)
        """
        self._cmd_data(_CMD_CONTRASTABC, r & 0xFF, g & 0xFF, b & 0xFF)

    def set_master_contrast(self, level):
        """
        Contraste global.
        level : 0 (min) .. 15 (max)
        """
        self._cmd_data(_CMD_CONTRASTMASTER, level & 0x0F)

    # ── Transfert buffer -> ecran ─────────────────────────────────────────────
    def show(self):
        """
        Transfere le framebuffer 128x128 vers la RAM du SSD1351.
        Colonnes : 0x00..0x7F (adressage direct, pas d'offset)
        Lignes   : 0x00..0x7F
        """
        self._cmd_data(_CMD_SETCOLUMN, 0x00, self.width - 1)
        self._cmd_data(_CMD_SETROW,    0x00, self.height - 1)
        self._write_cmd(_CMD_WRITERAM)
        self._cs(0); self._dc(1)
        self._spi.write(self._buf)
        self._cs(1)

    def show_region(self, x0, y0, x1, y1):
        """
        Transfere uniquement la zone (x0,y0)-(x1,y1) -> optimisation framerate.
        Gain typique : 2-5x sur des zones < 50% de l'ecran.
        """
        x0 = max(0, x0); y0 = max(0, y0)
        x1 = min(self.width - 1,  x1)
        y1 = min(self.height - 1, y1)
        self._cmd_data(_CMD_SETCOLUMN, x0, x1)
        self._cmd_data(_CMD_SETROW,    y0, y1)
        self._write_cmd(_CMD_WRITERAM)
        self._cs(0); self._dc(1)
        row_bytes = (x1 - x0 + 1) * 2
        for row in range(y0, y1 + 1):
            offset = (row * self.width + x0) * 2
            self._spi.write(self._buf[offset: offset + row_bytes])
        self._cs(1)

    # ── Scrolling materiel ───────────────────────────────────────────────────
    def start_scroll(self, start_row=0, end_row=127,
                     speed=0x00, direction=0):
        """
        Active le scrolling horizontal materiel du SSD1351.
        start_row : premiere ligne a scroller (0..127)
        end_row   : derniere ligne a scroller (0..127)
        speed     : 0x00=5fr, 0x01=64fr, 0x02=128fr, 0x03=256fr (lent)
        direction : 0 = droite, 1 = gauche (non supporte sur SSD1351 -> fixe)
        """
        self._cmd_data(_CMD_HORIZSCROLL,
                       0x00,            # A[7:0] dummy
                       start_row,       # B[6:0] start row
                       end_row,         # C[6:0] end row
                       speed,           # D[2:0] scroll speed
                       0x00)            # E dummy
        self._write_cmd(_CMD_STARTSCROLL)

    def stop_scroll(self):
        """Arrete le scrolling materiel."""
        self._write_cmd(_CMD_STOPSCROLL)

    # ── Primitives graphiques etendues ────────────────────────────────────────

    def draw_circle(self, cx, cy, r, color):
        """Cercle vide (algorithme de Bresenham)."""
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
        """Disque plein."""
        for dy in range(-r, r + 1):
            dx = int((r * r - dy * dy) ** 0.5)
            self._fb.hline(cx - dx, cy + dy, 2 * dx + 1, color)

    def draw_ellipse(self, cx, cy, rx, ry, color):
        """Ellipse vide."""
        x, y = 0, ry
        rx2, ry2 = rx * rx, ry * ry
        err = ry2 - rx2 * ry + rx2 // 4
        while ry2 * x < rx2 * y:
            for sx, sy in [(x,y),(-x,y),(x,-y),(-x,-y)]:
                px, py = cx + sx, cy + sy
                if 0 <= px < self.width and 0 <= py < self.height:
                    self._fb.pixel(px, py, color)
            if err < 0:
                x += 1; err += 2 * ry2 * x + ry2
            else:
                x += 1; y -= 1; err += 2 * ry2 * x - 2 * rx2 * y + ry2
        err = int(ry2 * (x + 0.5) ** 2 + rx2 * (y - 1) ** 2 - rx2 * ry2)
        while y >= 0:
            for sx, sy in [(x,y),(-x,y),(x,-y),(-x,-y)]:
                px, py = cx + sx, cy + sy
                if 0 <= px < self.width and 0 <= py < self.height:
                    self._fb.pixel(px, py, color)
            if err > 0:
                y -= 1; err -= 2 * rx2 * y + rx2
            else:
                x += 1; y -= 1; err += 2 * ry2 * x - 2 * rx2 * y + rx2

    def fill_ellipse(self, cx, cy, rx, ry, color):
        """Ellipse pleine."""
        for dy in range(-ry, ry + 1):
            dx = int(rx * (1 - (dy / ry) ** 2) ** 0.5)
            self._fb.hline(cx - dx, cy + dy, 2 * dx + 1, color)

    def draw_triangle(self, x0, y0, x1, y1, x2, y2, color):
        """Triangle vide."""
        self._fb.line(x0, y0, x1, y1, color)
        self._fb.line(x1, y1, x2, y2, color)
        self._fb.line(x2, y2, x0, y0, color)

    def fill_triangle(self, x0, y0, x1, y1, x2, y2, color):
        """Triangle plein (scanline)."""
        # Trier les sommets par y croissant
        pts = sorted([(x0,y0),(x1,y1),(x2,y2)], key=lambda p: p[1])
        (ax,ay),(bx,by),(cx,cy) = pts
        # Interpolation scanline
        def interp(x0,y0,x1,y1,y):
            if y1 == y0: return x0
            return int(x0 + (x1 - x0) * (y - y0) / (y1 - y0))
        for y in range(ay, cy + 1):
            if y <= by:
                xa = interp(ax,ay,cx,cy,y)
                xb = interp(ax,ay,bx,by,y)
            else:
                xa = interp(ax,ay,cx,cy,y)
                xb = interp(bx,by,cx,cy,y)
            if xa > xb: xa, xb = xb, xa
            self._fb.hline(xa, y, xb - xa + 1, color)

    def draw_rounded_rect(self, x, y, w, h, r, color):
        """Rectangle aux coins arrondis (vide)."""
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

    def fill_rounded_rect(self, x, y, w, h, r, color):
        """Rectangle aux coins arrondis (plein)."""
        self._fb.fill_rect(x + r, y,         w - 2*r, h,     color)
        self._fb.fill_rect(x,     y + r,     r,       h-2*r, color)
        self._fb.fill_rect(x+w-r, y + r,     r,       h-2*r, color)
        self.fill_circle(x + r,         y + r,         r, color)
        self.fill_circle(x + w - 1 - r, y + r,         r, color)
        self.fill_circle(x + r,         y + h - 1 - r, r, color)
        self.fill_circle(x + w - 1 - r, y + h - 1 - r, r, color)

    def draw_polygon(self, points, color, closed=True):
        """
        Polygone vide.
        points : liste de tuples [(x0,y0),(x1,y1),...] - min 2 points
        closed : True -> connecte le dernier point au premier
        """
        n = len(points)
        for i in range(n - 1):
            self._fb.line(points[i][0], points[i][1],
                          points[i+1][0], points[i+1][1], color)
        if closed and n >= 3:
            self._fb.line(points[-1][0], points[-1][1],
                          points[0][0],  points[0][1], color)

    def draw_cross(self, cx, cy, size, color, thickness=1):
        """Croix (+) centree en (cx, cy)."""
        half = size // 2
        for t in range(thickness):
            self._fb.hline(cx - half, cy + t - thickness//2, size, color)
            self._fb.vline(cx + t - thickness//2, cy - half, size, color)

    def draw_diamond(self, cx, cy, w, h, color):
        """Losange vide centre en (cx, cy)."""
        hw, hh = w // 2, h // 2
        self._fb.line(cx,      cy - hh, cx + hw, cy,      color)
        self._fb.line(cx + hw, cy,      cx,      cy + hh, color)
        self._fb.line(cx,      cy + hh, cx - hw, cy,      color)
        self._fb.line(cx - hw, cy,      cx,      cy - hh, color)

    def fill_diamond(self, cx, cy, w, h, color):
        """Losange plein."""
        hw, hh = w // 2, h // 2
        for dy in range(-hh, hh + 1):
            dx = int(hw * (1 - abs(dy) / hh))
            self._fb.hline(cx - dx, cy + dy, 2 * dx + 1, color)

    def draw_arc(self, cx, cy, r, start_deg, end_deg, color, step=1):
        """
        Arc de cercle de start_deg a end_deg (sens horaire).
        step : pas angulaire en degres (1 = haute qualite)
        """
        import math
        a = start_deg
        while a <= end_deg:
            rad = math.radians(a)
            px = int(cx + r * math.cos(rad))
            py = int(cy + r * math.sin(rad))
            if 0 <= px < self.width and 0 <= py < self.height:
                self._fb.pixel(px, py, color)
            a += step

    def fill_arc(self, cx, cy, r, start_deg, end_deg, color):
        """Secteur (camembert) plein."""
        import math
        for deg in range(int(start_deg), int(end_deg) + 1):
            rad = math.radians(deg)
            x1 = int(cx + r * math.cos(rad))
            y1 = int(cy + r * math.sin(rad))
            self._fb.line(cx, cy, x1, y1, color)

    def draw_text_large(self, text, x, y, scale, color, bg=None):
        """
        Texte agrandi par facteur scale.
        scale=2 -> 16x16 px/car, scale=3 -> 24x24 px/car.
        bg : couleur de fond (None = transparent)
        """
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
                elif bg is not None:
                    self._fb.fill_rect(x + sx * scale,
                                       y + sy * scale,
                                       scale, scale, bg)

    def gradient_fill(self, x, y, w, h, c_top, c_bot):
        """Degrade vertical lineaire de c_top (haut) a c_bot (bas)."""
        r0=(c_top>>11)&0x1F; g0=(c_top>>5)&0x3F; b0=c_top&0x1F
        r1=(c_bot>>11)&0x1F; g1=(c_bot>>5)&0x3F; b1=c_bot&0x1F
        for row in range(h):
            t = row / max(h - 1, 1)
            c = (int(r0+(r1-r0)*t) << 11) | \
                (int(g0+(g1-g0)*t) <<  5) | \
                 int(b0+(b1-b0)*t)
            self._fb.hline(x, y + row, w, c)

    def gradient_fill_h(self, x, y, w, h, c_left, c_right):
        """Degrade horizontal lineaire de c_left (gauche) a c_right (droite)."""
        r0=(c_left>>11)&0x1F;  g0=(c_left>>5)&0x3F;  b0=c_left&0x1F
        r1=(c_right>>11)&0x1F; g1=(c_right>>5)&0x3F; b1=c_right&0x1F
        for col in range(w):
            t = col / max(w - 1, 1)
            c = (int(r0+(r1-r0)*t) << 11) | \
                (int(g0+(g1-g0)*t) <<  5) | \
                 int(b0+(b1-b0)*t)
            self._fb.vline(x + col, y, h, c)

    def gradient_fill_radial(self, cx, cy, r_in, r_out, c_in, c_out):
        """
        Degrade radial de c_in (centre) a c_out (bord).
        r_in  : rayon interieur (debut du degrade)
        r_out : rayon exterieur (fin du degrade)
        """
        for dy in range(-r_out, r_out + 1):
            for dx in range(-r_out, r_out + 1):
                dist = (dx*dx + dy*dy) ** 0.5
                if dist > r_out: continue
                px, py = cx + dx, cy + dy
                if not (0 <= px < self.width and 0 <= py < self.height):
                    continue
                if dist <= r_in:
                    self._fb.pixel(px, py, c_in)
                else:
                    t = (dist - r_in) / (r_out - r_in)
                    self._fb.pixel(px, py, blend(c_in, c_out, t))

    def draw_progress_bar(self, x, y, w, h, pct,
                          fg=GREEN, bg=GRAY, border=WHITE, radius=0):
        """
        Barre de progression (0.0 .. 100.0).
        radius : 0 = coins droits, >0 = coins arrondis
        """
        pct = max(0.0, min(100.0, pct))
        f = int(w * pct / 100.0)
        if radius > 0:
            self.draw_rounded_rect(x, y, w, h, radius, border)
            if f > 2 * radius:
                self.fill_rounded_rect(x+1, y+1, f-2, h-2, radius, fg)
            if f < w - 2:
                self._fb.fill_rect(x+f, y+1, w-f-1, h-2, bg)
        else:
            self._fb.rect(x, y, w, h, border)
            if f > 2:     self._fb.fill_rect(x+1, y+1, f-2, h-2, fg)
            if f < w - 2: self._fb.fill_rect(x+f, y+1, w-f-1, h-2, bg)

    def draw_checkerboard(self, x, y, w, h, size, c1, c2):
        """Motif damier avec cases de cote size."""
        for row in range(0, h, size):
            for col in range(0, w, size):
                c = c1 if (row // size + col // size) % 2 == 0 else c2
                self._fb.fill_rect(x + col, y + row,
                                   min(size, w - col),
                                   min(size, h - row), c)

    def draw_sine_wave(self, x0, y_center, length, amplitude,
                       frequency, color, phase=0.0):
        """
        Trace une sinusoide.
        x0        : colonne de depart
        y_center  : ligne centrale
        length    : largeur en pixels
        amplitude : amplitude en pixels
        frequency : nombre de cycles sur length pixels
        phase     : dephasage initial (radians)
        """
        import math
        prev_y = None
        for px in range(length):
            t = px / length
            py = int(y_center + amplitude * math.sin(
                     2 * math.pi * frequency * t + phase))
            py = max(0, min(self.height - 1, py))
            if prev_y is not None:
                self._fb.line(x0 + px - 1, prev_y, x0 + px, py, color)
            prev_y = py

    def draw_image(self, x, y, w, h, data):
        """
        Affiche une image brute RGB565 (bytearray de w*h*2 octets).
        Les pixels sont en ordre row-major, RGB565 big-endian.
        """
        img = framebuf.FrameBuffer(bytearray(data), w, h, framebuf.RGB565)
        self._fb.blit(img, x, y)

    def draw_bitmap_mono(self, x, y, bitmap, w, h, fg, bg=-1):
        """
        Affiche un bitmap monochrome 1bpp (bytes/bytearray, MSB first).
        fg  : couleur des pixels '1'
        bg  : couleur des pixels '0' (-1 = transparent)
        """
        for row in range(h):
            for col in range(w):
                idx = (row * w + col) // 8
                bit = 7 - ((row * w + col) % 8)
                if bitmap[idx] & (1 << bit):
                    self._fb.pixel(x + col, y + row, fg)
                elif bg >= 0:
                    self._fb.pixel(x + col, y + row, bg)

    def draw_colorwheel(self, cx, cy, r_out, r_in=0):
        """
        Roue chromatique complete HSV.
        cx, cy  : centre
        r_out   : rayon exterieur
        r_in    : rayon interieur (0 = disque plein)
        """
        import math
        for dy in range(-r_out, r_out + 1):
            for dx in range(-r_out, r_out + 1):
                dist = (dx*dx + dy*dy) ** 0.5
                if dist > r_out or dist < r_in: continue
                px, py = cx + dx, cy + dy
                if not (0 <= px < self.width and 0 <= py < self.height):
                    continue
                hue = (math.degrees(math.atan2(dy, dx)) + 360) % 360
                sat = (dist - r_in) / (r_out - r_in)
                self._fb.pixel(px, py, hsv_to_rgb565(hue, sat, 1.0))

    def scroll_text(self, text, y, color, bg=BLACK, delay_ms=50):
        """
        Defilement de texte de droite a gauche sur la ligne y.
        Bloquant — utiliser la version async pour le multitâche.
        """
        full = text + "        "
        tw = 8 * len(full)
        for offset in range(tw):
            self._fb.fill_rect(0, y, self.width, 8, bg)
            self._fb.text(full, -offset, y, color)
            self.show_region(0, y, self.width - 1, y + 7)
            time.sleep_ms(delay_ms)

    def fade_in(self, steps=16, delay_ms=30):
        """Transition fondu depuis noir (contraste 0 -> max)."""
        self.show()
        for i in range(steps + 1):
            level = int(i * 15 / steps)
            self.set_master_contrast(level)
            time.sleep_ms(delay_ms)

    def fade_out(self, steps=16, delay_ms=30):
        """Transition fondu vers noir (contraste max -> 0)."""
        for i in range(steps, -1, -1):
            level = int(i * 15 / steps)
            self.set_master_contrast(level)
            time.sleep_ms(delay_ms)
        self.set_master_contrast(15)  # restaurer

    # ── Utilitaires ───────────────────────────────────────────────────────────
    def clear(self, color=BLACK):
        """Efface le buffer avec la couleur donnee et rafraichit."""
        self._fb.fill(color)
        self.show()

    def get_pixel(self, x, y):
        """Lit la couleur d'un pixel dans le buffer."""
        return self._fb.pixel(x, y)

    def __repr__(self):
        return "SSD1351 RGB OLED {}x{} px v1.0.0".format(
               self.width, self.height)
