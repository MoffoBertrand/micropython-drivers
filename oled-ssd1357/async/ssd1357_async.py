"""
ssd1357_async.py — Driver MicroPython ASYNCHRONE pour RGB OLED 0.96" SSD1357
==============================================================================
Version asynchrone de ssd1357.py v6.0.0 basee sur uasyncio.

Principes de conception
-----------------------
1. DOUBLE BUFFER : deux buffers RAM (avant/arriere).
   - Le buffer ARRIERE est modifie par les taches graphiques.
   - La tache show_task() echange les buffers et pousse vers l'ecran.
   - Aucun blocage SPI pendant le dessin.

2. VERROU SPI : asyncio.Lock() protege le bus SPI.
   Les methodes show() et show_region() sont des coroutines (async).

3. TACHE D'AFFICHAGE AUTONOME : start_refresh(fps) lance une tache
   qui rafraichit l'ecran a la frequence demandee en arriere-plan.

4. API MIXTE : toutes les primitives graphiques restent SYNCHRONES
   (fill, pixel, text, fill_rect...). Seul le transfert SPI est async.

5. COMPATIBILITE : l'API synchrone de ssd1357.py est preservee.
   show_sync() et show_region_sync() permettent un usage bloquant
   si necessaire (hors boucle asyncio).

Architecture des buffers
------------------------
  _buf_back  : buffer modifie par les primitives graphiques (tache courante)
  _buf_front : buffer envoye vers l'ecran par show_task()
  _swap()    : echange atomique des deux pointeurs

Utilisation typique
-------------------
  import uasyncio as asyncio
  from ssd1357_async import SSD1357Async, BLACK, WHITE, RED

  async def main():
      oled = SSD1357Async()
      await oled.init()                    # init async (resets non bloquants)
      oled.start_refresh(fps=25)           # tache de rafraichissement 25 fps

      # Tache 1 : animation OLED
      async def animation():
          x = 0
          while True:
              oled.fill(BLACK)
              oled.fill_circle(x % 64, 64, 10, RED)
              oled.mark_dirty()            # signale qu'une frame est prete
              x += 2
              await asyncio.sleep_ms(40)

      # Tache 2 : autre traitement concurrent
      async def sensor():
          while True:
              # lecture capteur, MQTT, etc.
              await asyncio.sleep_ms(500)

      await asyncio.gather(animation(), sensor())

  asyncio.run(main())

Auteur  : Prof. MOFFO LONLA Bertrand — UB COT / Labo GIA Douala
Version : 1.0.0 — base sur ssd1357.py v6.0.0 (Waveshare)
"""

import framebuf
import time
import uasyncio as asyncio
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


def color565(r, g, b):
    """Convertit R, G, B (0-255) -> RGB565."""
    return ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)


class SSD1357Async:
    """
    Driver asynchrone SSD1357 — RGB OLED 0.96" Waveshare (portrait 64x128).

    Parametres hardware (valides sur materiel) :
      Colonnes : 0x20..0x5F  |  Remap : 0x60, 0x00
      StartLine : 0x00       |  MuxRatio : 0x7F

    Toutes les primitives graphiques (fill, pixel, text, line, rect,
    fill_rect, blit, scroll...) sont SYNCHRONES — elles modifient le
    buffer arriere sans bloquer la boucle evenementielle.

    Seuls show() et show_region() sont des coroutines async.
    """

    WIDTH      = 64
    HEIGHT     = 128
    _COL_START = 0x20
    _COL_END   = 0x5F

    def __init__(self, spi_id=1, sck=11, mosi=13, cs=10,
                 dc=9, rst=8, baudrate=16_000_000):

        self.width  = self.WIDTH
        self.height = self.HEIGHT

        # Broches
        self._cs  = Pin(cs,  Pin.OUT, value=1)
        self._dc  = Pin(dc,  Pin.OUT, value=0)
        self._rst = Pin(rst, Pin.OUT, value=1)

        # Bus SPI
        self._spi = SPI(spi_id, baudrate=baudrate, polarity=0, phase=0,
                        sck=Pin(sck), mosi=Pin(mosi), miso=None)

        # ── Double buffer ────────────────────────────────────────────────────
        # _buf_back  : modifie par les primitives graphiques
        # _buf_front : envoye a l'ecran par show_task
        BUF_SIZE = self.width * self.height * 2
        self._buf_back  = bytearray(BUF_SIZE)
        self._buf_front = bytearray(BUF_SIZE)

        # FrameBuffer pointe sur le buffer arriere
        self._fb = framebuf.FrameBuffer(
                       self._buf_back, self.width, self.height, framebuf.RGB565)

        # ── Synchronisation async ────────────────────────────────────────────
        self._lock        = asyncio.Lock()   # protege le bus SPI
        self._dirty       = asyncio.Event()  # signale une frame prete
        self._refresh_task = None            # handle de la tache de refresh
        self._running     = False

        self._rotation    = 0
        self._fps_target  = 25
        self._frame_count = 0              # compteur de frames affichees

    # ── Delegation FrameBuffer (primitives synchrones) ───────────────────────
    def __getattr__(self, name):
        if name.startswith('_'):
            raise AttributeError(name)
        return getattr(self._fb, name)

    # ── SPI bas niveau (synchrone — appele sous verrou) ──────────────────────
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

    # ── Reset asynchrone ─────────────────────────────────────────────────────
    async def _async_reset(self):
        """Reset non bloquant — cede le CPU pendant les delais."""
        self._rst(1); await asyncio.sleep_ms(100)
        self._rst(0); await asyncio.sleep_ms(100)
        self._rst(1); await asyncio.sleep_ms(100)

    # ── Initialisation asynchrone ────────────────────────────────────────────
    async def init(self):
        """
        Initialise le module de maniere non bloquante.
        DOIT etre appelee avec await avant toute utilisation.

        Exemple :
            oled = SSD1357Async()
            await oled.init()
        """
        await self._async_reset()

        self._cmd_data(0xFD, 0x12)        # command lock
        self._write_cmd(0xAE)             # display off

        self._cmd_data(0x15, 0x20, 0x5F)  # colonnes 0x20..0x5F
        self._cmd_data(0x75, 0x00, 0x7F)  # lignes 0x00..0x7F
        self._cmd_data(0xA0, 0x60, 0x00)  # remap
        self._cmd_data(0xA1, 0x00)        # StartLine
        self._cmd_data(0xA2, 0x00)        # DisplayOffset
        self._cmd_data(0xB1, 0x84)
        self._cmd_data(0xB3, 0x20)
        self._cmd_data(0xB6, 0x01)
        self._cmd_data(0xBB, 0x00)
        self._cmd_data(0xBE, 0x07)
        self._cmd_data(0xC7, 0x0F)
        self._cmd_data(0xC1, 0x32, 0x29, 0x53)
        self._cmd_data(0xCA, 0x7F)

        await asyncio.sleep_ms(100)
        self._write_cmd(0xAF)             # display on

        self._cmd_data(0x15, 0x20, 0x5F)
        self._cmd_data(0x75, 0x00, 0x7F)
        self._write_cmd(0x5C)

        self._fb.fill(BLACK)
        await self.show()

    # ── Swap des buffers ─────────────────────────────────────────────────────
    def _swap_buffers(self):
        """
        Echange atomique des buffers avant/arriere.
        Copie le buffer arriere vers le buffer avant,
        puis repointe le FrameBuffer sur le buffer arriere vide.
        Le buffer avant sera envoye a l'ecran.
        """
        # Copier arriere -> avant
        self._buf_front[:] = self._buf_back
        # Le FrameBuffer continue de pointer sur _buf_back
        # (les primitives continuent de dessiner en arriere)

    # ── Signalement dirty ────────────────────────────────────────────────────
    def mark_dirty(self):
        """
        Signale qu'une nouvelle frame est prete a afficher.
        Appeler apres avoir dessine une scene complete.
        La tache de refresh detectera cet evenement et declenchera show().

        Exemple :
            oled.fill(BLACK)
            oled.text('Hello', 0, 0, WHITE)
            oled.mark_dirty()   # <- declenche le prochain rafraichissement
        """
        self._dirty.set()

    # ── show() asynchrone ────────────────────────────────────────────────────
    async def show(self):
        """
        Transfere le buffer arriere vers l'ecran de maniere non bloquante.
        Acquiert le verrou SPI, echange les buffers, envoie les donnees.
        """
        async with self._lock:
            self._swap_buffers()
            self._cmd_data(0x15, self._COL_START, self._COL_END)
            self._cmd_data(0x75, 0x00, 0x7F)
            self._write_cmd(0x5C)
            self._cs(0); self._dc(1)
            self._spi.write(self._buf_front)
            self._cs(1)
            self._frame_count += 1

    # ── show_region() asynchrone ─────────────────────────────────────────────
    async def show_region(self, x0, y0, x1, y1):
        """
        Mise a jour partielle non bloquante.
        Plus rapide que show() pour des zones de petite taille.
        x0, x1 : indices framebuf [0..63]
        y0, y1 : indices framebuf [0..127]
        """
        x0 = max(0, x0); y0 = max(0, y0)
        x1 = min(self.width - 1,  x1)
        y1 = min(self.height - 1, y1)
        async with self._lock:
            self._cmd_data(0x15,
                           x0 + self._COL_START,
                           x1 + self._COL_START)
            self._cmd_data(0x75, y0, y1)
            self._write_cmd(0x5C)
            self._cs(0); self._dc(1)
            row_bytes = (x1 - x0 + 1) * 2
            for row in range(y0, y1 + 1):
                offset = (row * self.width + x0) * 2
                self._spi.write(self._buf_back[offset: offset + row_bytes])
            self._cs(1)
            self._frame_count += 1

    # ── show_sync() synchrone (usage sans boucle asyncio) ────────────────────
    def show_sync(self):
        """
        Version BLOQUANTE de show() — pour usage hors boucle asyncio.
        Equivalent a ssd1357.py v6.0.0 show().
        """
        self._cmd_data(0x15, self._COL_START, self._COL_END)
        self._cmd_data(0x75, 0x00, 0x7F)
        self._write_cmd(0x5C)
        self._cs(0); self._dc(1)
        self._spi.write(self._buf_back)
        self._cs(1)

    def show_region_sync(self, x0, y0, x1, y1):
        """Version BLOQUANTE de show_region()."""
        x0 = max(0, x0); y0 = max(0, y0)
        x1 = min(self.width - 1,  x1)
        y1 = min(self.height - 1, y1)
        self._cmd_data(0x15, x0+self._COL_START, x1+self._COL_START)
        self._cmd_data(0x75, y0, y1)
        self._write_cmd(0x5C)
        self._cs(0); self._dc(1)
        row_bytes = (x1 - x0 + 1) * 2
        for row in range(y0, y1 + 1):
            offset = (row * self.width + x0) * 2
            self._spi.write(self._buf_back[offset: offset + row_bytes])
        self._cs(1)

    # ── Tache de rafraichissement autonome ───────────────────────────────────
    async def _refresh_loop(self, fps):
        """
        Tache interne : attend un signal dirty puis pousse le buffer.
        Si aucun signal en 1/fps secondes, ne rafraichit pas (economie CPU).
        """
        period_ms = max(10, 1000 // fps)
        self._running = True
        while self._running:
            try:
                # Attendre une frame prete ou timeout
                await asyncio.wait_for_ms(self._dirty.wait(), period_ms)
                self._dirty.clear()
                await self.show()
            except asyncio.TimeoutError:
                pass   # Pas de nouvelle frame — on attend

    def start_refresh(self, fps=25):
        """
        Lance la tache de rafraichissement automatique en arriere-plan.

        fps : frequence cible (1..60). Recommande : 25 pour animations,
              10 pour affichage statique.

        La tache attend mark_dirty() pour rafraichir — si aucune frame
        n'est signalee, l'ecran n'est pas re-envoye (economie SPI).

        Exemple :
            oled.start_refresh(fps=30)
            # puis dans la tache graphique :
            oled.fill(BLACK)
            oled.text('Hello', 0, 0, WHITE)
            oled.mark_dirty()
        """
        self._fps_target   = fps
        self._refresh_task = asyncio.create_task(self._refresh_loop(fps))
        return self._refresh_task

    def stop_refresh(self):
        """Arrete la tache de rafraichissement."""
        self._running = False
        if self._refresh_task is not None:
            self._refresh_task.cancel()
            self._refresh_task = None

    # ── Controle affichage ────────────────────────────────────────────────────
    async def reset(self):
        """Reset asynchrone."""
        await self._async_reset()

    def power_on(self):   self._write_cmd(0xAF)
    def power_off(self):  self._write_cmd(0xAE)

    def invert(self, state):
        self._write_cmd(0xA7 if state else 0xA6)

    def rotate(self, angle):
        """Rotation 0/90/180/270 via registre REMAP."""
        angle = angle % 360
        if angle not in (0, 90, 180, 270):
            raise ValueError("angle doit etre 0, 90, 180 ou 270")
        _remap = {0: 0x60, 90: 0x63, 180: 0x72, 270: 0x71}
        self._rotation = angle
        self._cmd_data(0xA0, _remap[angle], 0x00)

    def get_rotation(self):
        return self._rotation

    def set_contrast(self, r, g, b):
        self._cmd_data(0xC1, r & 0xFF, g & 0xFF, b & 0xFF)

    def set_master_contrast(self, level):
        self._cmd_data(0xC7, level & 0x0F)

    async def clear(self, color=BLACK):
        """Efface le buffer et rafraichit (async)."""
        self._fb.fill(color)
        await self.show()

    def clear_sync(self, color=BLACK):
        """Version synchrone de clear()."""
        self._fb.fill(color)
        self.show_sync()

    # ── Stats ────────────────────────────────────────────────────────────────
    def get_frame_count(self):
        """Retourne le nombre total de frames affichees."""
        return self._frame_count

    def reset_frame_count(self):
        self._frame_count = 0

    # ── Primitives graphiques etendues (synchrones) ───────────────────────────
    # Toutes modifient _buf_back via self._fb

    def draw_circle(self, cx, cy, r, color):
        """Cercle vide (Bresenham)."""
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
        """Texte agrandi par facteur scale."""
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
        r0=(c_top>>11)&0x1F; g0=(c_top>>5)&0x3F; b0=c_top&0x1F
        r1=(c_bot>>11)&0x1F; g1=(c_bot>>5)&0x3F; b1=c_bot&0x1F
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

    def __repr__(self):
        return "SSD1357Async RGB OLED {}x{} px v1.0.0".format(
               self.width, self.height)
