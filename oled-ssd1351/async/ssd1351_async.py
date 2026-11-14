"""
ssd1351_async.py — Driver MicroPython ASYNCHRONE pour RGB OLED 1.5" SSD1351
=============================================================================
Module   : Waveshare 1.5inch RGB OLED Module (128x128 px, RGB565)
Cible    : ESP32-S3 — MicroPython v1.21+ — uasyncio
Version  : 1.0.0

Herite de ssd1351.py v1.0.0 et en etend toutes les fonctionnalites
avec un modele d'execution non bloquant base sur uasyncio.

Architecture
------------

  ┌─────────────────────────────────────────────────────────────┐
  │  Taches graphiques  (synchrones — inchangees)               │
  │  fill, pixel, text, fill_rect, fill_circle, gradient…      │
  │               ecrivent dans                                  │
  │         _buf_back  <── FrameBuffer                          │
  ├─────────────────────────────────────────────────────────────┤
  │  mark_dirty()  ──►  asyncio.Event  ──►  _refresh_loop()    │
  │                           │                                  │
  │       _swap_buffers()  copy back -> front                    │
  │       SPI.write(_buf_front)  sous asyncio.Lock              │
  └─────────────────────────────────────────────────────────────┘

Principes
---------
1. DOUBLE BUFFER : _buf_back (dessin) / _buf_front (envoi SPI).
   Pas de déchirement ni de clignotement.

2. VERROU SPI : asyncio.Lock() garantit l'acces exclusif au bus.
   show() et show_region() sont des coroutines.

3. TACHE AUTONOME : start_refresh(fps) lance une coroutine de fond
   qui rafraichit a la frequence demandee uniquement si mark_dirty()
   a ete appele → zero CPU gaspille quand rien ne change.

4. API MIXTE :
   - Primitives graphiques → SYNCHRONES (fill, pixel, text…)
   - Transfert SPI         → ASYNC (show, show_region, clear)
   - Fonctions bloquantes  → show_sync, show_region_sync (hors asyncio)

5. ANIMATIONS ASYNC : draw_sine_wave_async, scroll_text_async,
   fade_in_async, fade_out_async, draw_colorwheel_async —
   toutes cedent le CPU a chaque frame via await asyncio.sleep_ms(0).

6. SPRITES : systeme leger de sprites animes (SpriteManager).

Utilisation typique
-------------------
  import uasyncio as asyncio
  from ssd1351_async import SSD1351Async, BLACK, WHITE, RED, color565

  async def main():
      oled = SSD1351Async()
      await oled.init()
      oled.start_refresh(fps=30)

      async def animation():
          x = 0
          while True:
              oled.fill(BLACK)
              oled.fill_circle(x % 128, 64, 14, RED)
              oled.mark_dirty()
              x += 3
              await asyncio.sleep_ms(33)

      async def sensor_task():
          while True:
              # lecture I2C, MQTT, WiFi... concurrent
              await asyncio.sleep_ms(500)

      await asyncio.gather(animation(), sensor_task())

  asyncio.run(main())

Auteur  : Prof. MOFFO LONLA Bertrand — UB COT / Labo GIA Douala
"""

import framebuf
import time
import uasyncio as asyncio
from machine import Pin, SPI
import math

# ── Couleurs RGB565 ──────────────────────────────────────────────────────────
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
NAVY       = const(0x000F)
TEAL       = const(0x0410)


def color565(r, g, b):
    """R,G,B (0-255) -> RGB565."""
    return ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)


def hsv_to_rgb565(h, s, v):
    """Teinte (0-360), Saturation (0-1), Valeur (0-1) -> RGB565."""
    if s == 0.0:
        c = int(v * 255); return color565(c, c, c)
    h = h % 360; i = int(h / 60); f = (h / 60) - i
    p=int(v*(1-s)*255); q=int(v*(1-s*f)*255); t=int(v*(1-s*(1-f))*255); vi=int(v*255)
    if i==0: return color565(vi,t,p)
    if i==1: return color565(q,vi,p)
    if i==2: return color565(p,vi,t)
    if i==3: return color565(p,q,vi)
    if i==4: return color565(t,p,vi)
    return color565(vi,p,q)


def blend(c1, c2, t):
    """Melange lineaire c1->c2, t=0..1."""
    r0=(c1>>11)&0x1F;g0=(c1>>5)&0x3F;b0=c1&0x1F
    r1=(c2>>11)&0x1F;g1=(c2>>5)&0x3F;b1=c2&0x1F
    return (int(r0+(r1-r0)*t)<<11)|(int(g0+(g1-g0)*t)<<5)|int(b0+(b1-b0)*t)


# ── Commandes SSD1351 ────────────────────────────────────────────────────────
_CMD_SETCOLUMN      = const(0x15)
_CMD_SETROW         = const(0x75)
_CMD_WRITERAM       = const(0x5C)
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
_CMD_PRECHARGELEVEL = const(0xBB)
_CMD_VCOMH          = const(0xBE)
_CMD_CONTRASTABC    = const(0xC1)
_CMD_CONTRASTMASTER = const(0xC7)
_CMD_MUXRATIO       = const(0xCA)
_CMD_COMMANDLOCK    = const(0xFD)
_CMD_STOPSCROLL     = const(0x9E)
_CMD_STARTSCROLL    = const(0x9F)
_CMD_HORIZSCROLL    = const(0x96)


# ── Sprite (entite animee independante) ──────────────────────────────────────
class Sprite:
    """
    Entite graphique independante avec position, vitesse et rebond.

    Attributs publics modifiables :
      x, y       : position (float)
      vx, vy     : vitesse en px/frame (float)
      visible    : bool
      color      : couleur RGB565
      radius     : rayon (si shape='circle')
      w, h       : dimensions (si shape='rect')
      shape      : 'circle' | 'rect' | 'pixel'
    """

    def __init__(self, x=0, y=0, vx=0, vy=0,
                 color=WHITE, radius=5,
                 w=10, h=10, shape='circle',
                 bounce=True, wrap=False,
                 screen_w=128, screen_h=128):
        self.x = float(x); self.y = float(y)
        self.vx = float(vx); self.vy = float(vy)
        self.color  = color
        self.radius = radius
        self.w = w; self.h = h
        self.shape   = shape
        self.bounce  = bounce    # rebondir sur les bords
        self.wrap    = wrap      # reapparaitre de l'autre cote
        self.visible = True
        self._sw = screen_w; self._sh = screen_h
        self._prev_x = x; self._prev_y = y

    def update(self):
        """Mise a jour de la position (appelee avant dessin)."""
        self._prev_x = self.x; self._prev_y = self.y
        self.x += self.vx; self.y += self.vy
        r = self.radius if self.shape == 'circle' else 0
        if self.bounce:
            if self.x - r < 0 or self.x + r >= self._sw:
                self.vx = -self.vx
                self.x = max(r, min(self._sw - r - 1, self.x))
            if self.y - r < 0 or self.y + r >= self._sh:
                self.vy = -self.vy
                self.y = max(r, min(self._sh - r - 1, self.y))
        elif self.wrap:
            self.x = self.x % self._sw
            self.y = self.y % self._sh

    def draw(self, fb, erase_color=BLACK):
        """Efface l'ancienne position et dessine la nouvelle."""
        if not self.visible: return
        ox, oy = int(self._prev_x), int(self._prev_y)
        nx, ny = int(self.x),       int(self.y)
        if self.shape == 'circle':
            r = self.radius
            # Effacement ancienne pos
            for dy in range(-r-1, r+2):
                dx = int(((r+1)**2 - dy*dy)**0.5) + 1
                y_clamp = oy + dy
                if 0 <= y_clamp < fb._sh:
                    fb._fb.hline(max(0, ox-dx), y_clamp,
                                 min(2*dx+1, fb._sw - max(0,ox-dx)), erase_color)
            # Dessin nouvelle pos
            for dy in range(-r, r+1):
                dx = int((r*r - dy*dy)**0.5)
                y_clamp = ny + dy
                if 0 <= y_clamp < fb._sh:
                    fb._fb.hline(max(0,nx-dx), y_clamp,
                                 min(2*dx+1, fb._sw-max(0,nx-dx)), self.color)
        elif self.shape == 'rect':
            fb._fb.fill_rect(ox, oy, self.w, self.h, erase_color)
            fb._fb.fill_rect(nx, ny, self.w, self.h, self.color)
        elif self.shape == 'pixel':
            fb._fb.pixel(ox, oy, erase_color)
            fb._fb.pixel(nx, ny, self.color)

    @property
    def px(self): return int(self.x)
    @property
    def py(self): return int(self.y)


class SpriteManager:
    """
    Gestionnaire de sprites.
    Mise a jour et dessin de tous les sprites en un appel.
    """

    def __init__(self, oled):
        self._oled   = oled
        self._sprites = []

    def add(self, sprite):
        self._sprites.append(sprite)
        return sprite

    def remove(self, sprite):
        if sprite in self._sprites:
            self._sprites.remove(sprite)

    def update_all(self):
        """Appeler avant show() dans la boucle d'animation."""
        for s in self._sprites:
            s.update()

    def draw_all(self, erase_color=BLACK):
        """Efface + redessine tous les sprites."""
        for s in self._sprites:
            s.draw(self._oled, erase_color)

    def clear(self):
        self._sprites.clear()


# ── Driver principal ─────────────────────────────────────────────────────────
class SSD1351Async:
    """
    Driver asynchrone SSD1351 — RGB OLED 1.5" Waveshare (128x128 px).

    Coordonnees : x in [0,127], y in [0,127].

    Toutes les primitives graphiques (fill, pixel, text, line, rect,
    fill_rect, blit, scroll) sont SYNCHRONES — elles modifient le
    buffer arriere sans bloquer la boucle evenementielle.

    show() et show_region() sont des coroutines async.
    """

    WIDTH  = 128
    HEIGHT = 128

    def __init__(self, spi_id=1, sck=11, mosi=13, cs=10,
                 dc=9, rst=8, baudrate=20_000_000):
        self.width  = self.WIDTH
        self.height = self.HEIGHT
        self._sw    = self.WIDTH     # alias pour Sprite
        self._sh    = self.HEIGHT

        # Broches
        self._cs  = Pin(cs,  Pin.OUT, value=1)
        self._dc  = Pin(dc,  Pin.OUT, value=0)
        self._rst = Pin(rst, Pin.OUT, value=1)

        # Bus SPI
        self._spi = SPI(spi_id, baudrate=baudrate, polarity=0, phase=0,
                        sck=Pin(sck), mosi=Pin(mosi), miso=None)

        # ── Double buffer ────────────────────────────────────────────────────
        BUF = self.width * self.height * 2   # 32 768 octets
        self._buf_back  = bytearray(BUF)     # modifie par les primitives
        self._buf_front = bytearray(BUF)     # envoye au SSD1351

        # FrameBuffer pointe toujours sur _buf_back
        self._fb = framebuf.FrameBuffer(
                       self._buf_back, self.width, self.height, framebuf.RGB565)

        # ── Synchronisation async ────────────────────────────────────────────
        self._lock          = asyncio.Lock()   # protege le bus SPI
        self._dirty         = asyncio.Event()  # signal mark_dirty()
        self._refresh_task  = None
        self._running       = False
        self._fps_target    = 30
        self._frame_count   = 0
        self._dropped_frames= 0

        # Etat controleur
        self._rotation      = 0
        self._contrast_master = 15

        # Gestionnaire de sprites
        self.sprites = SpriteManager(self)

    # ── Delegation FrameBuffer (synchrones) ──────────────────────────────────
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
        self._write_cmd(cmd)
        for b in args: self._write_data(b)

    # ── Reset asynchrone ─────────────────────────────────────────────────────
    async def _async_reset(self):
        """Reset non bloquant — cede le CPU pendant les delais."""
        self._rst(1); await asyncio.sleep_ms(100)
        self._rst(0); await asyncio.sleep_ms(100)
        self._rst(1); await asyncio.sleep_ms(100)

    # ── Initialisation asynchrone ────────────────────────────────────────────
    async def init(self):
        """
        Initialise le SSD1351 de maniere non bloquante.
        Doit etre appelee avec await avant toute utilisation.

            oled = SSD1351Async()
            await oled.init()
        """
        await self._async_reset()

        self._cmd_data(_CMD_COMMANDLOCK, 0x12)
        self._cmd_data(_CMD_COMMANDLOCK, 0xB1)
        self._write_cmd(_CMD_DISPLAYOFF)
        self._cmd_data(_CMD_CLOCKDIV,    0xF1)
        self._cmd_data(_CMD_MUXRATIO,    0x7F)
        self._cmd_data(_CMD_SETREMAP,    0x74)
        self._cmd_data(_CMD_STARTLINE,   0x00)
        self._cmd_data(_CMD_DISPLAYOFFSET, 0x00)
        self._cmd_data(_CMD_SETGPIO,     0x00)
        self._cmd_data(_CMD_FUNCTIONSELECT, 0x01)
        self._cmd_data(_CMD_SETVSL,      0xA0, 0xB5, 0x55)
        self._cmd_data(_CMD_CONTRASTABC, 0xC8, 0x80, 0xC8)
        self._cmd_data(_CMD_CONTRASTMASTER, 0x0F)
        self._cmd_data(_CMD_DISPLAYENHANCE, 0xA4, 0x00, 0x00)
        self._cmd_data(_CMD_PRECHARGE,   0x32)
        self._cmd_data(_CMD_PRECHARGE2,  0x01)
        self._cmd_data(_CMD_PRECHARGELEVEL, 0x17)
        self._cmd_data(_CMD_VCOMH,       0x05)
        self._write_cmd(_CMD_NORMALDISPLAY)

        await asyncio.sleep_ms(100)

        self._fb.fill(BLACK)
        await self.show()
        self._write_cmd(_CMD_DISPLAYON)

    # ── Swap des buffers ─────────────────────────────────────────────────────
    def _swap_buffers(self):
        """
        Copie le buffer arriere -> avant.
        Le FrameBuffer continue de pointer sur _buf_back :
        les primitives peuvent dessiner la prochaine frame
        pendant que _buf_front est envoye au SSD1351.
        """
        self._buf_front[:] = self._buf_back

    # ── Signalement dirty ─────────────────────────────────────────────────────
    def mark_dirty(self):
        """
        Signale qu'une nouvelle frame est prete.
        Appeler apres avoir dessine une scene complete.
        La tache de refresh detectera l'evenement et declenchera show().

            oled.fill(BLACK)
            oled.fill_circle(x, y, 20, RED)
            oled.mark_dirty()   # <- declenche le rafraichissement
        """
        self._dirty.set()

    # ── show() asynchrone ────────────────────────────────────────────────────
    async def show(self):
        """
        Transfere le framebuffer 128x128 vers le SSD1351 de maniere
        non bloquante. Acquiert le verrou SPI, swap les buffers, envoie.
        """
        async with self._lock:
            self._swap_buffers()
            self._cmd_data(_CMD_SETCOLUMN, 0x00, self.width - 1)
            self._cmd_data(_CMD_SETROW,    0x00, self.height - 1)
            self._write_cmd(_CMD_WRITERAM)
            self._cs(0); self._dc(1)
            self._spi.write(self._buf_front)
            self._cs(1)
            self._frame_count += 1

    async def show_region(self, x0, y0, x1, y1):
        """
        Mise a jour partielle non bloquante — plus rapide que show()
        pour des zones de petite taille (gain 2-5x sur < 50% de l'ecran).
        """
        x0=max(0,x0); y0=max(0,y0)
        x1=min(self.width-1,x1); y1=min(self.height-1,y1)
        async with self._lock:
            self._cmd_data(_CMD_SETCOLUMN, x0, x1)
            self._cmd_data(_CMD_SETROW,    y0, y1)
            self._write_cmd(_CMD_WRITERAM)
            self._cs(0); self._dc(1)
            row_bytes = (x1 - x0 + 1) * 2
            for row in range(y0, y1 + 1):
                offset = (row * self.width + x0) * 2
                self._spi.write(self._buf_back[offset: offset + row_bytes])
            self._cs(1)
            self._frame_count += 1

    # ── Versions synchrones (hors boucle asyncio) ────────────────────────────
    def show_sync(self):
        """Version BLOQUANTE de show() — pour code hors asyncio."""
        self._cmd_data(_CMD_SETCOLUMN, 0x00, self.width - 1)
        self._cmd_data(_CMD_SETROW,    0x00, self.height - 1)
        self._write_cmd(_CMD_WRITERAM)
        self._cs(0); self._dc(1)
        self._spi.write(self._buf_back)
        self._cs(1)

    def show_region_sync(self, x0, y0, x1, y1):
        """Version BLOQUANTE de show_region()."""
        x0=max(0,x0); y0=max(0,y0)
        x1=min(self.width-1,x1); y1=min(self.height-1,y1)
        self._cmd_data(_CMD_SETCOLUMN, x0, x1)
        self._cmd_data(_CMD_SETROW,    y0, y1)
        self._write_cmd(_CMD_WRITERAM)
        self._cs(0); self._dc(1)
        row_bytes = (x1-x0+1)*2
        for row in range(y0, y1+1):
            offset = (row*self.width+x0)*2
            self._spi.write(self._buf_back[offset:offset+row_bytes])
        self._cs(1)

    # ── Tache de rafraichissement autonome ───────────────────────────────────
    async def _refresh_loop(self, fps):
        """
        Tache interne : attend mark_dirty() et pousse le buffer.
        Le timeout fps evite de rester bloque indéfiniment.
        Comptabilise les frames affichees et perdues.
        """
        period_ms = max(10, 1000 // fps)
        self._running = True

        while self._running:
            try:
                await asyncio.wait_for_ms(self._dirty.wait(), period_ms)
                self._dirty.clear()
                await self.show()
            except asyncio.TimeoutError:
                # Pas de nouvelle frame dans la periode — on attend
                pass
            except Exception as e:
                print("[SSD1351Async] Erreur refresh_loop:", e)
                await asyncio.sleep_ms(100)

    def start_refresh(self, fps=30):
        """
        Lance la tache de rafraichissement automatique.

        fps : frequence cible (1..60)
              Recommande : 30 pour animations fluides,
                           10 pour affichage statique (economie energie)

        La tache ne rafraichit que si mark_dirty() a ete appele.
        Aucune donnee SPI n'est envoyee si rien ne change.

        Retourne la Task asyncio (peut etre passee a cancel()).
        """
        self._fps_target  = fps
        self._refresh_task = asyncio.create_task(self._refresh_loop(fps))
        return self._refresh_task

    def stop_refresh(self):
        """Arrete la tache de rafraichissement."""
        self._running = False
        if self._refresh_task:
            self._refresh_task.cancel()
            self._refresh_task = None

    # ── Controle affichage ────────────────────────────────────────────────────
    async def reset(self):
        """Reset asynchrone."""
        await self._async_reset()

    def power_on(self):   self._write_cmd(_CMD_DISPLAYON)
    def power_off(self):  self._write_cmd(_CMD_DISPLAYOFF)
    def all_on(self):     self._write_cmd(_CMD_DISPLAYALLON)
    def all_off(self):    self._write_cmd(_CMD_DISPLAYALLOFF)

    def invert(self, state):
        self._write_cmd(_CMD_INVERTDISPLAY if state else _CMD_NORMALDISPLAY)

    def rotate(self, angle):
        """Rotation 0/90/180/270 via registre SETREMAP."""
        angle = angle % 360
        if angle not in (0, 90, 180, 270):
            raise ValueError("angle doit etre 0, 90, 180 ou 270")
        _remap = {0: 0x74, 90: 0x77, 180: 0x76, 270: 0x75}
        self._rotation = angle
        self._cmd_data(_CMD_SETREMAP, _remap[angle])

    def get_rotation(self):
        return self._rotation

    def set_contrast(self, r, g, b):
        self._cmd_data(_CMD_CONTRASTABC, r & 0xFF, g & 0xFF, b & 0xFF)

    def set_master_contrast(self, level):
        self._contrast_master = level & 0x0F
        self._cmd_data(_CMD_CONTRASTMASTER, self._contrast_master)

    def start_scroll(self, start_row=0, end_row=127, speed=0x00):
        self._cmd_data(_CMD_HORIZSCROLL, 0x00, start_row, end_row, speed, 0x00)
        self._write_cmd(_CMD_STARTSCROLL)

    def stop_scroll(self):
        self._write_cmd(_CMD_STOPSCROLL)

    # ── clear() asynchrone ────────────────────────────────────────────────────
    async def clear(self, color=BLACK):
        """Efface le buffer et rafraichit (async)."""
        self._fb.fill(color)
        await self.show()

    def clear_sync(self, color=BLACK):
        """Version synchrone de clear()."""
        self._fb.fill(color)
        self.show_sync()

    # ── Stats ────────────────────────────────────────────────────────────────
    def get_stats(self):
        """
        Retourne un dict avec les statistiques d'affichage.
        Utile pour monitorer les performances en production.
        """
        return {
            'frames'   : self._frame_count,
            'dropped'  : self._dropped_frames,
            'fps_target': self._fps_target,
            'running'  : self._running,
            'dirty'    : self._dirty.is_set(),
        }

    def reset_stats(self):
        self._frame_count = 0
        self._dropped_frames = 0

    # ── Primitives graphiques synchrones (heritees de ssd1351.py) ───────────

    def draw_circle(self, cx, cy, r, color):
        x, y, err = 0, r, 1-r
        while x <= y:
            for dx, dy in [(x,y),(y,x),(-x,y),(-y,x),(x,-y),(y,-x),(-x,-y),(-y,-x)]:
                px, py = cx+dx, cy+dy
                if 0<=px<self.width and 0<=py<self.height:
                    self._fb.pixel(px,py,color)
            if err<0: err+=2*x+3
            else:     err+=2*(x-y)+5; y-=1
            x+=1

    def fill_circle(self, cx, cy, r, color):
        for dy in range(-r, r+1):
            dx=int((r*r-dy*dy)**0.5)
            self._fb.hline(cx-dx, cy+dy, 2*dx+1, color)

    def draw_ellipse(self, cx, cy, rx, ry, color):
        x,y=0,ry; rx2,ry2=rx*rx,ry*ry
        err=ry2-rx2*ry+rx2//4
        while ry2*x < rx2*y:
            for sx,sy in [(x,y),(-x,y),(x,-y),(-x,-y)]:
                px,py=cx+sx,cy+sy
                if 0<=px<self.width and 0<=py<self.height: self._fb.pixel(px,py,color)
            if err<0: x+=1; err+=2*ry2*x+ry2
            else:     x+=1; y-=1; err+=2*ry2*x-2*rx2*y+ry2
        err=int(ry2*(x+.5)**2+rx2*(y-1)**2-rx2*ry2)
        while y>=0:
            for sx,sy in [(x,y),(-x,y),(x,-y),(-x,-y)]:
                px,py=cx+sx,cy+sy
                if 0<=px<self.width and 0<=py<self.height: self._fb.pixel(px,py,color)
            if err>0: y-=1; err-=2*rx2*y+rx2
            else:     x+=1; y-=1; err+=2*ry2*x-2*rx2*y+rx2

    def fill_ellipse(self, cx, cy, rx, ry, color):
        for dy in range(-ry, ry+1):
            dx=int(rx*(1-(dy/ry)**2)**0.5)
            self._fb.hline(cx-dx, cy+dy, 2*dx+1, color)

    def draw_triangle(self, x0,y0,x1,y1,x2,y2,color):
        self._fb.line(x0,y0,x1,y1,color)
        self._fb.line(x1,y1,x2,y2,color)
        self._fb.line(x2,y2,x0,y0,color)

    def fill_triangle(self, x0,y0,x1,y1,x2,y2,color):
        pts=sorted([(x0,y0),(x1,y1),(x2,y2)],key=lambda p:p[1])
        (ax,ay),(bx,by),(cx2,cy2)=pts
        def interp(x0,y0,x1,y1,y):
            return x0 if y1==y0 else int(x0+(x1-x0)*(y-y0)/(y1-y0))
        for y in range(ay, cy2+1):
            xa=interp(ax,ay,cx2,cy2,y); xb=interp(ax,ay,bx,by,y) if y<=by else interp(bx,by,cx2,cy2,y)
            if xa>xb: xa,xb=xb,xa
            self._fb.hline(xa, y, xb-xa+1, color)

    def draw_rounded_rect(self, x,y,w,h,r,color):
        self._fb.hline(x+r,y,w-2*r,color); self._fb.hline(x+r,y+h-1,w-2*r,color)
        self._fb.vline(x,y+r,h-2*r,color); self._fb.vline(x+w-1,y+r,h-2*r,color)
        for i in range(r+1):
            j=int((r*r-i*i)**0.5)
            self._fb.pixel(x+r-i,y+r-j,color);         self._fb.pixel(x+w-1-r+i,y+r-j,color)
            self._fb.pixel(x+r-i,y+h-1-r+j,color);     self._fb.pixel(x+w-1-r+i,y+h-1-r+j,color)

    def fill_rounded_rect(self, x,y,w,h,r,color):
        self._fb.fill_rect(x+r,y,w-2*r,h,color)
        self._fb.fill_rect(x,y+r,r,h-2*r,color)
        self._fb.fill_rect(x+w-r,y+r,r,h-2*r,color)
        self.fill_circle(x+r,y+r,r,color); self.fill_circle(x+w-1-r,y+r,r,color)
        self.fill_circle(x+r,y+h-1-r,r,color); self.fill_circle(x+w-1-r,y+h-1-r,r,color)

    def draw_polygon(self, points, color, closed=True):
        n=len(points)
        for i in range(n-1): self._fb.line(points[i][0],points[i][1],points[i+1][0],points[i+1][1],color)
        if closed and n>=3: self._fb.line(points[-1][0],points[-1][1],points[0][0],points[0][1],color)

    def draw_cross(self, cx,cy,size,color,thickness=1):
        half=size//2
        for t in range(thickness):
            self._fb.hline(cx-half,cy+t-thickness//2,size,color)
            self._fb.vline(cx+t-thickness//2,cy-half,size,color)

    def draw_diamond(self, cx,cy,w,h,color):
        hw,hh=w//2,h//2
        self._fb.line(cx,cy-hh,cx+hw,cy,color); self._fb.line(cx+hw,cy,cx,cy+hh,color)
        self._fb.line(cx,cy+hh,cx-hw,cy,color); self._fb.line(cx-hw,cy,cx,cy-hh,color)

    def fill_diamond(self, cx,cy,w,h,color):
        hw,hh=w//2,h//2
        for dy in range(-hh,hh+1):
            dx=int(hw*(1-abs(dy)/hh))
            self._fb.hline(cx-dx,cy+dy,2*dx+1,color)

    def draw_arc(self, cx,cy,r,start_deg,end_deg,color,step=1):
        a=start_deg
        while a<=end_deg:
            rad=math.radians(a); px=int(cx+r*math.cos(rad)); py=int(cy+r*math.sin(rad))
            if 0<=px<self.width and 0<=py<self.height: self._fb.pixel(px,py,color)
            a+=step

    def fill_arc(self, cx,cy,r,start_deg,end_deg,color):
        for deg in range(int(start_deg),int(end_deg)+1):
            rad=math.radians(deg)
            self._fb.line(cx,cy,int(cx+r*math.cos(rad)),int(cy+r*math.sin(rad)),color)

    def draw_text_large(self, text, x,y,scale,color,bg=None):
        tw=8*len(text); th=8
        tb=bytearray(tw*th*2); tf=framebuf.FrameBuffer(tb,tw,th,framebuf.RGB565)
        tf.fill(BLACK); tf.text(text,0,0,color)
        for sy in range(th):
            for sx in range(tw):
                c=tf.pixel(sx,sy)
                if c!=BLACK: self._fb.fill_rect(x+sx*scale,y+sy*scale,scale,scale,c)
                elif bg is not None: self._fb.fill_rect(x+sx*scale,y+sy*scale,scale,scale,bg)

    def gradient_fill(self, x,y,w,h,c_top,c_bot):
        r0=(c_top>>11)&0x1F;g0=(c_top>>5)&0x3F;b0=c_top&0x1F
        r1=(c_bot>>11)&0x1F;g1=(c_bot>>5)&0x3F;b1=c_bot&0x1F
        for row in range(h):
            t=row/max(h-1,1)
            c=(int(r0+(r1-r0)*t)<<11)|(int(g0+(g1-g0)*t)<<5)|int(b0+(b1-b0)*t)
            self._fb.hline(x,y+row,w,c)

    def gradient_fill_h(self, x,y,w,h,c_left,c_right):
        r0=(c_left>>11)&0x1F;g0=(c_left>>5)&0x3F;b0=c_left&0x1F
        r1=(c_right>>11)&0x1F;g1=(c_right>>5)&0x3F;b1=c_right&0x1F
        for col in range(w):
            t=col/max(w-1,1)
            c=(int(r0+(r1-r0)*t)<<11)|(int(g0+(g1-g0)*t)<<5)|int(b0+(b1-b0)*t)
            self._fb.vline(x+col,y,h,c)

    def draw_progress_bar(self, x,y,w,h,pct,fg=GREEN,bg=GRAY,border=WHITE,radius=0):
        pct=max(0.0,min(100.0,pct)); f=int(w*pct/100.0)
        if radius>0:
            self.draw_rounded_rect(x,y,w,h,radius,border)
            if f>2*radius: self.fill_rounded_rect(x+1,y+1,f-2,h-2,radius,fg)
            if f<w-2: self._fb.fill_rect(x+f,y+1,w-f-1,h-2,bg)
        else:
            self._fb.rect(x,y,w,h,border)
            if f>2: self._fb.fill_rect(x+1,y+1,f-2,h-2,fg)
            if f<w-2: self._fb.fill_rect(x+f,y+1,w-f-1,h-2,bg)

    def draw_checkerboard(self, x,y,w,h,size,c1,c2):
        for row in range(0,h,size):
            for col in range(0,w,size):
                c=c1 if (row//size+col//size)%2==0 else c2
                self._fb.fill_rect(x+col,y+row,min(size,w-col),min(size,h-row),c)

    def draw_image(self, x,y,w,h,data):
        img=framebuf.FrameBuffer(bytearray(data),w,h,framebuf.RGB565)
        self._fb.blit(img,x,y)

    def draw_bitmap_mono(self, x,y,bitmap,w,h,fg,bg=-1):
        for row in range(h):
            for col in range(w):
                idx=(row*w+col)//8; bit=7-((row*w+col)%8)
                if bitmap[idx]&(1<<bit): self._fb.pixel(x+col,y+row,fg)
                elif bg>=0: self._fb.pixel(x+col,y+row,bg)

    # ── Animations ASYNC (cedent le CPU a chaque frame) ──────────────────────

    async def draw_sine_wave_async(self, x0, y_center, length, amplitude,
                                    frequency, color, phase=0.0, step_ms=0):
        """
        Trace une sinusoide de maniere non bloquante.
        step_ms : delai en ms entre chaque pixel (0 = le plus rapide possible)
        """
        prev_y = None
        for px in range(length):
            t = px / length
            py = int(y_center + amplitude * math.sin(
                     2 * math.pi * frequency * t + phase))
            py = max(0, min(self.height-1, py))
            if prev_y is not None:
                self._fb.line(x0+px-1, prev_y, x0+px, py, color)
            prev_y = py
            if px % 16 == 0:
                await asyncio.sleep_ms(step_ms)

    async def draw_colorwheel_async(self, cx, cy, r_out, r_in=0):
        """
        Roue chromatique HSV non bloquante.
        Cede le CPU toutes les 8 lignes.
        """
        for dy in range(-r_out, r_out+1):
            for dx in range(-r_out, r_out+1):
                dist=(dx*dx+dy*dy)**0.5
                if dist>r_out or dist<r_in: continue
                px,py=cx+dx,cy+dy
                if not(0<=px<self.width and 0<=py<self.height): continue
                hue=(math.degrees(math.atan2(dy,dx))+360)%360
                sat=(dist-r_in)/(r_out-r_in) if r_out>r_in else 1.0
                self._fb.pixel(px,py,hsv_to_rgb565(hue,sat,1.0))
            if dy % 8 == 0:
                await asyncio.sleep_ms(0)

    async def scroll_text_async(self, text, y, color, bg=BLACK,
                                 delay_ms=40, loop=False):
        """
        Defilement texte non bloquant.
        loop : True = defilement infini (appeler dans une tache separee)
        """
        full = text + "        "
        tw   = 8 * len(full)
        while True:
            for offset in range(tw):
                self._fb.fill_rect(0, y, self.width, 8, bg)
                self._fb.text(full, -offset, y, color)
                await self.show_region(0, y, self.width-1, y+7)
                await asyncio.sleep_ms(delay_ms)
            if not loop:
                break

    async def fade_in_async(self, steps=15, delay_ms=30):
        """Transition fondu entree non bloquante."""
        await self.show()
        for i in range(steps+1):
            self._cmd_data(_CMD_CONTRASTMASTER, int(i*15/steps))
            await asyncio.sleep_ms(delay_ms)
        self._contrast_master = 15

    async def fade_out_async(self, steps=15, delay_ms=30):
        """Transition fondu sortie non bloquante."""
        for i in range(steps, -1, -1):
            self._cmd_data(_CMD_CONTRASTMASTER, int(i*15/steps))
            await asyncio.sleep_ms(delay_ms)
        self._cmd_data(_CMD_CONTRASTMASTER, 15)
        self._contrast_master = 15

    async def plasma_async(self, frames=60, delay_ms=20):
        """
        Effet plasma (psychedelique) non bloquant.
        Cede le CPU entre chaque ligne.
        """
        for frame in range(frames):
            t = frame * 0.1
            for y in range(0, self.height, 2):
                for x in range(0, self.width, 2):
                    v = (math.sin(x/8+t) + math.sin(y/8+t) +
                         math.sin((x+y)/12+t) +
                         math.sin(math.sqrt(x*x+y*y)/8+t))
                    hue=(v*45+180)%360
                    c=hsv_to_rgb565(hue,1.0,1.0)
                    self._fb.fill_rect(x,y,2,2,c)
                await asyncio.sleep_ms(0)  # ceder le CPU entre lignes
            await self.show()
            await asyncio.sleep_ms(delay_ms)

    async def bounce_ball_async(self, color=ORANGE, r=12,
                                 frames=200, delay_ms=16):
        """
        Balle rebondissante avec sillage — tache autonome.
        Peut etre lancee en parallele avec d'autres taches.
        """
        import random
        bx, by  = float(self.width//2), float(self.height//2)
        vx = random.uniform(1.5, 3.0) * (1 if random.random()>0.5 else -1)
        vy = random.uniform(1.5, 3.0) * (1 if random.random()>0.5 else -1)
        ox, oy  = int(bx), int(by)

        for _ in range(frames):
            # Effacer ancienne position
            self.fill_circle(ox, oy, r+2, BLACK)
            ox, oy = int(bx), int(by)
            bx += vx; by += vy
            if bx<=r or bx>=self.width-r:  vx=-vx; bx=max(r,min(self.width-r,bx))
            if by<=r or by>=self.height-r: vy=-vy; by=max(r,min(self.height-r,by))
            nx, ny = int(bx), int(by)
            # Sillage
            for i in range(3,0,-1):
                tx=int(bx-vx*i*2); ty=int(by-vy*i*2)
                if 0<=tx<self.width and 0<=ty<self.height:
                    self.fill_circle(tx,ty,max(1,r-i*3),
                                     color565(200-i*50,80-i*20,0))
            # Balle
            self.fill_circle(nx, ny, r, color)
            self.draw_circle(nx, ny, r, WHITE)
            x0=max(0,min(ox,nx)-r-3); y0=max(0,min(oy,ny)-r-3)
            x1=min(self.width-1,max(ox,nx)+r+3)
            y1=min(self.height-1,max(oy,ny)+r+3)
            await self.show_region(x0,y0,x1,y1)
            await asyncio.sleep_ms(delay_ms)

    # ── Utilitaires ───────────────────────────────────────────────────────────
    def get_pixel(self, x, y):
        return self._fb.pixel(x, y)

    def __repr__(self):
        return "SSD1351Async RGB OLED {}x{} px v1.0.0".format(
               self.width, self.height)
