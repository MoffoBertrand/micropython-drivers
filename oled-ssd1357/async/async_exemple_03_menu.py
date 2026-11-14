"""
async_exemple_03_menu.py
=========================================================
Exemple Async 3 — Menu interactif asynchrone
  Navigation par 3 boutons GPIO (HAUT, BAS, SELECT)
  Lecture boutons non bloquante via asyncio
  Affichage menu avec highlight + actions par item
  Demontre la gestion d'entrees utilisateur async
=========================================================
"""
import uasyncio as asyncio
from machine import Pin
from ssd1357_async import (SSD1357Async, color565,
                            BLACK, WHITE, RED, GREEN, BLUE,
                            YELLOW, CYAN, GRAY, ORANGE, MAGENTA)

# ── Configuration boutons (adapter selon votre cablage) ──────────────────────
PIN_HAUT    = 4    # Bouton haut
PIN_BAS     = 5    # Bouton bas
PIN_SELECT  = 6    # Bouton selection

# ── Gestionnaire de boutons asynchrone ────────────────────────────────────────
class BoutonAsync:
    """Lecteur de bouton avec debounce asynchrone."""

    DEBOUNCE_MS = 50

    def __init__(self, pin_num, pull=Pin.PULL_UP, actif_bas=True):
        self._pin       = Pin(pin_num, Pin.IN, pull)
        self._actif_bas = actif_bas
        self._presse    = False
        self._event     = asyncio.Event()

    def est_presse(self):
        val = self._pin.value()
        return (val == 0) if self._actif_bas else (val == 1)

    async def attendre_appui(self):
        """Coroutine bloquante jusqu'au prochain appui."""
        while True:
            if self.est_presse():
                await asyncio.sleep_ms(self.DEBOUNCE_MS)
                if self.est_presse():
                    # Attendre le relachement
                    while self.est_presse():
                        await asyncio.sleep_ms(10)
                    return True
            await asyncio.sleep_ms(10)

# ── Elements du menu ──────────────────────────────────────────────────────────
MENU_ITEMS = [
    "Luminosite",
    "Rotation",
    "Inversion",
    "Animation",
    "Capteurs",
    "A propos",
]

# ── Rendu du menu ─────────────────────────────────────────────────────────────
def draw_menu(oled, items, sel, titre="MENU"):
    """Affiche le menu avec l'element selectionne en surbrillance."""
    oled.fill(BLACK)
    # Titre
    oled.fill_rect(0, 0, 64, 14, color565(0, 60, 120))
    oled.text(titre[:8], 0, 3, WHITE)
    # Items (max 7 visibles sur 128 px - 14 titre - 10 bas = 104 px / 14 px par item)
    LINE_H = 14
    visible = min(len(items), 7)
    start   = max(0, sel - visible + 1) if sel >= visible else 0
    for i in range(visible):
        idx = start + i
        if idx >= len(items): break
        y = 16 + i * LINE_H
        if idx == sel:
            oled.fill_rect(0, y, 64, LINE_H, color565(0, 100, 200))
            oled.text("> " + items[idx][:6], 0, y + 3, WHITE)
        else:
            oled.text("  " + items[idx][:6], 0, y + 3, GRAY)
    # Indicateur de scroll
    if len(items) > visible:
        oled.text("{}/{}".format(sel+1, len(items)), 32, 118, GRAY)

# ── Actions du menu ───────────────────────────────────────────────────────────
async def action_luminosite(oled):
    """Ajustement du contraste par boutons."""
    btn_h = BoutonAsync(PIN_HAUT)
    btn_b = BoutonAsync(PIN_BAS)
    btn_s = BoutonAsync(PIN_SELECT)
    niveau = 15

    async def lire_boutons():
        nonlocal niveau
        while True:
            if btn_h.est_presse():
                niveau = min(15, niveau + 1)
                await asyncio.sleep_ms(150)
            elif btn_b.est_presse():
                niveau = max(0, niveau - 1)
                await asyncio.sleep_ms(150)
            elif btn_s.est_presse():
                return
            await asyncio.sleep_ms(20)

    while True:
        oled.fill(BLACK)
        oled.fill_rect(0, 0, 64, 14, color565(0, 60, 120))
        oled.text("LUMINOSI", 0, 3, WHITE)
        oled.draw_progress_bar(2, 24, 60, 14, niveau/15*100,
                               fg=YELLOW, bg=GRAY, border=WHITE)
        oled.text("Niv {:2d}".format(niveau), 12, 44, WHITE)
        oled.text("[SEL]=OK", 0, 112, GRAY)
        oled.set_master_contrast(niveau)
        await oled.show()

        if btn_s.est_presse():
            await asyncio.sleep_ms(200)
            break
        if btn_h.est_presse():
            niveau = min(15, niveau + 1)
            await asyncio.sleep_ms(150)
        elif btn_b.est_presse():
            niveau = max(0, niveau - 1)
            await asyncio.sleep_ms(150)
        await asyncio.sleep_ms(30)

async def action_rotation(oled):
    """Selection de l'orientation."""
    btn_h = BoutonAsync(PIN_HAUT)
    btn_b = BoutonAsync(PIN_BAS)
    btn_s = BoutonAsync(PIN_SELECT)
    angles = [0, 90, 180, 270]
    sel = 0
    while True:
        oled.fill(BLACK)
        oled.fill_rect(0, 0, 64, 14, color565(0, 60, 120))
        oled.text("ROTATION", 0, 3, WHITE)
        for i, a in enumerate(angles):
            y = 20 + i * 18
            if i == sel:
                oled.fill_rect(0, y, 64, 16, color565(0, 80, 160))
                oled.text("> {:3d} deg".format(a), 0, y+4, WHITE)
            else:
                oled.text("  {:3d} deg".format(a), 0, y+4, GRAY)
        oled.text("[SEL]=OK", 0, 112, GRAY)
        await oled.show()

        if btn_s.est_presse():
            oled.rotate(angles[sel])
            await asyncio.sleep_ms(300)
            break
        if btn_h.est_presse():
            sel = (sel - 1) % len(angles)
            await asyncio.sleep_ms(150)
        elif btn_b.est_presse():
            sel = (sel + 1) % len(angles)
            await asyncio.sleep_ms(150)
        await asyncio.sleep_ms(30)

async def action_animation(oled):
    """Animation demo courte (5 secondes)."""
    import math
    t0_ms = 0
    for frame in range(125):
        phase = frame * 0.15
        oled.fill(BLACK)
        oled.fill_rect(0, 0, 64, 12, color565(30, 0, 60))
        oled.text("ANIMAT. ", 0, 2, MAGENTA)
        for i in range(8):
            a = i * 3.14159 / 4 + phase
            r = 20 + int(8 * math.sin(phase * 2))
            x = 32 + int(r * math.cos(a))
            y = 70 + int(r * math.sin(a))
            c = color565(
                int(127 + 127 * math.cos(a)),
                int(127 + 127 * math.sin(a + 2)),
                int(127 + 127 * math.cos(a + 4))
            )
            oled.fill_circle(x, y, 5, c)
        await oled.show()
        await asyncio.sleep_ms(40)

async def action_a_propos(oled):
    """Page a propos."""
    btn_s = BoutonAsync(PIN_SELECT)
    oled.fill(BLACK)
    oled.fill_rect(0, 0, 64, 14, color565(0, 60, 120))
    oled.text("A PROPOS", 0, 3, WHITE)
    oled.text("SSD1357 ", 0, 18, CYAN)
    oled.text("Async   ", 0, 30, CYAN)
    oled.text("v1.0.0  ", 0, 42, YELLOW)
    oled.text("UB COT  ", 0, 58, GREEN)
    oled.text("GIA     ", 0, 70, GREEN)
    oled.text("Douala  ", 0, 82, GREEN)
    oled.text("[SEL]=OK", 0, 112, GRAY)
    await oled.show()
    await btn_s.attendre_appui()

ACTIONS = {
    0: action_luminosite,
    1: action_rotation,
    2: lambda oled: oled.invert(True) or asyncio.sleep_ms(1000),
    3: action_animation,
    4: None,   # capteurs (non implemente ici)
    5: action_a_propos,
}

# ── Boucle principale du menu ─────────────────────────────────────────────────
async def main():
    oled = SSD1357Async()
    await oled.init()

    btn_h = BoutonAsync(PIN_HAUT)
    btn_b = BoutonAsync(PIN_BAS)
    btn_s = BoutonAsync(PIN_SELECT)

    sel = 0
    print("Menu demarre. Boutons : HAUT={} BAS={} SELECT={}".format(
          PIN_HAUT, PIN_BAS, PIN_SELECT))

    while True:
        draw_menu(oled, MENU_ITEMS, sel)
        await oled.show()

        # Attendre un appui (polling non bloquant)
        await asyncio.sleep_ms(30)
        if btn_h.est_presse():
            sel = (sel - 1) % len(MENU_ITEMS)
            await asyncio.sleep_ms(150)
        elif btn_b.est_presse():
            sel = (sel + 1) % len(MENU_ITEMS)
            await asyncio.sleep_ms(150)
        elif btn_s.est_presse():
            await asyncio.sleep_ms(200)
            action = ACTIONS.get(sel)
            if action:
                await action(oled)
            oled.invert(False)   # restaurer si inversion

asyncio.run(main())
