"""
async_exemple_04_jeu.py — SSD1351Async RGB OLED 1.5"
Exemple Async 4 : Mini-jeu Snake asynchrone
  Tache 1 : moteur de jeu (logique serpent) @ 10 fps
  Tache 2 : rendu OLED @ 25 fps
  Tache 3 : lecture joystick ADC (X=GPIO4, Y=GPIO5)
  Tache 4 : affichage score console

Le jeu tourne independamment du rendu — exemple de
separation logique / affichage via asyncio.
"""
import uasyncio as asyncio
import random
from machine import ADC, Pin
from ssd1351_async import (SSD1351Async, color565, hsv_to_rgb565,
                            BLACK, WHITE, RED, GREEN, BLUE,
                            YELLOW, CYAN, GRAY, ORANGE)

# ── Configuration ─────────────────────────────────────────────────────────────
CELL    = 8          # taille d'une cellule en pixels
COLS    = 16         # 128 / 8 = 16 colonnes
ROWS    = 16         # 128 / 8 = 16 lignes
SPEED_MS = 150       # periode du moteur de jeu

# ── Etat du jeu ───────────────────────────────────────────────────────────────
class GameState:
    def __init__(self):
        self.reset()

    def reset(self):
        cx, cy = COLS//2, ROWS//2
        self.snake  = [(cx, cy), (cx-1, cy), (cx-2, cy)]
        self.dir    = (1, 0)    # direction courante
        self.next_dir = (1, 0)  # direction demandee
        self.food   = self._new_food()
        self.score  = 0
        self.alive  = True
        self.level  = 1

    def _new_food(self):
        while True:
            f = (random.randint(0, COLS-1), random.randint(0, ROWS-1))
            if f not in self.snake:
                return f

    def step(self):
        if not self.alive: return
        self.dir = self.next_dir
        hx, hy = self.snake[0]
        nx, ny = hx + self.dir[0], hy + self.dir[1]
        # Collision murs
        if not (0 <= nx < COLS and 0 <= ny < ROWS):
            self.alive = False; return
        # Collision propre corps
        if (nx, ny) in self.snake:
            self.alive = False; return
        self.snake.insert(0, (nx, ny))
        if (nx, ny) == self.food:
            self.score += 10
            self.level  = 1 + self.score // 50
            self.food   = self._new_food()
        else:
            self.snake.pop()

gs = GameState()

# ── Tache 1 : Moteur de jeu ───────────────────────────────────────────────────
async def tache_moteur():
    global gs
    while True:
        period = max(60, SPEED_MS - gs.level * 10)
        gs.step()
        if not gs.alive:
            await asyncio.sleep_ms(2000)
            gs.reset()
        await asyncio.sleep_ms(period)

# ── Tache 2 : Rendu OLED ──────────────────────────────────────────────────────
async def tache_rendu(oled):
    oled.start_refresh(fps=25)
    while True:
        oled.fill(BLACK)
        # Grille (optionnelle - allege visuellement)
        # for x in range(0, 128, CELL): oled.vline(x, 0, 128, color565(10,10,10))
        # Nourriture (clignotante)
        import time
        blink = (time.ticks_ms() // 250) % 2
        fx, fy = gs.food
        c_food = RED if blink else color565(200, 0, 0)
        oled.fill_rect(fx*CELL+1, fy*CELL+1, CELL-2, CELL-2, c_food)
        # Serpent
        for i, (sx, sy) in enumerate(gs.snake):
            t   = i / max(len(gs.snake)-1, 1)
            hue = 120 - t * 60   # vert -> jaune le long du corps
            c   = hsv_to_rgb565(hue, 1.0, 1.0 - t * 0.4)
            oled.fill_rect(sx*CELL+1, sy*CELL+1, CELL-2, CELL-2, c)
        # Tete mise en valeur
        hx, hy = gs.snake[0]
        oled.fill_rect(hx*CELL, hy*CELL, CELL, CELL, WHITE)
        oled.fill_rect(hx*CELL+2, hy*CELL+2, CELL-4, CELL-4,
                       color565(0, 200, 0))
        # Score
        oled.fill_rect(0, 120, 128, 8, color565(0,20,0))
        oled.text("Score:{:4d} Lv:{}".format(gs.score, gs.level), 0, 120, WHITE)
        # Game over
        if not gs.alive:
            oled.fill_rounded_rect(20, 44, 88, 40, 6, color565(100,0,0))
            oled.draw_rounded_rect(20, 44, 88, 40, 6, RED)
            oled.text(" GAME OVER!     ", 20, 54, RED)
            oled.text(" Score:{:4d}     ".format(gs.score), 20, 66, YELLOW)

        oled.mark_dirty()
        await asyncio.sleep_ms(40)

# ── Tache 3 : Joystick ADC ────────────────────────────────────────────────────
async def tache_joystick():
    """
    Lit un joystick analogique 2 axes.
    GPIO4 = axe X, GPIO5 = axe Y.
    Centre = ~2048 (1.65V), seuil de detection = 20% de la plage.
    """
    try:
        adc_x = ADC(Pin(4)); adc_x.atten(ADC.ATTN_11DB); adc_x.width(ADC.WIDTH_12BIT)
        adc_y = ADC(Pin(5)); adc_y.atten(ADC.ATTN_11DB); adc_y.width(ADC.WIDTH_12BIT)
        SEUIL = 820   # 4095 * 0.2
        CENTER = 2048
        while True:
            x = adc_x.read(); y = adc_y.read()
            dx, dy = x - CENTER, y - CENTER
            if abs(dx) > SEUIL or abs(dy) > SEUIL:
                if abs(dx) > abs(dy):   # axe X dominant
                    new_dir = (1,0) if dx > 0 else (-1,0)
                else:                    # axe Y dominant
                    new_dir = (0,1) if dy > 0 else (0,-1)
                # Interdire demi-tour
                cd = gs.dir
                if not (new_dir[0] == -cd[0] and new_dir[1] == -cd[1]):
                    gs.next_dir = new_dir
    except Exception:
        # Joystick non connecte : mouvements automatiques (demo)
        import time
        DIRS = [(1,0),(0,1),(-1,0),(0,-1)]
        idx  = 0
        while True:
            await asyncio.sleep_ms(1200)
            idx = (idx+1) % 4
            gs.next_dir = DIRS[idx]
        return
    while True:
        await asyncio.sleep_ms(80)

# ── Tache 4 : Console ─────────────────────────────────────────────────────────
async def tache_console():
    while True:
        await asyncio.sleep_ms(3000)
        print("[Snake] Score={} Level={} Alive={} Longueur={}".format(
              gs.score, gs.level, gs.alive, len(gs.snake)))

# ── MAIN ──────────────────────────────────────────────────────────────────────
async def main():
    oled = SSD1351Async()
    await oled.init()

    # Ecran titre
    oled.fill(BLACK)
    oled.gradient_fill(0, 0, 128, 128, color565(0,40,0), BLACK)
    oled.draw_rounded_rect(14, 30, 100, 68, 8, GREEN)
    oled.draw_text_large("SNAKE", 18, 44, 2, GREEN)
    oled.text("Async uasyncio  ", 14, 76, CYAN)
    oled.text("Joystick GPIO4/5", 14, 88, GRAY)
    await oled.show()
    await asyncio.sleep_ms(2000)

    print("Jeu Snake async demarre (45 s)...")
    try:
        await asyncio.wait_for(
            asyncio.gather(
                tache_moteur(),
                tache_rendu(oled),
                tache_joystick(),
                tache_console(),
            ),
            45
        )
    except asyncio.TimeoutError:
        pass

    oled.stop_refresh()
    await oled.clear()
    oled.draw_text_large("FIN", 28, 50, 4, YELLOW)
    oled.text("Score final:{:3d}".format(gs.score), 0, 110, WHITE)
    await oled.show()
    print("Score final :", gs.score)

asyncio.run(main())
