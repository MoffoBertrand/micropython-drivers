# eeprom24c01_async.py — Version asynchrone du pilote EEPROM 24C01
# À utiliser avec asyncio (MicroPython uasyncio).
#
# Différences avec eeprom24c01.py (version synchrone) :
#   - write()      → coroutine : await asyncio.sleep_ms(5) après chaque page
#   - write_byte() → coroutine (délègue à write)
#   - erase()      → coroutine (boucle d'effacement — 16 pages × 5 ms = 80 ms total)
#
# Les méthodes de LECTURE restent SYNCHRONES :
#   read(), read_byte(), dump()
#   La lecture EEPROM 24C01 est immédiate (pas d'attente matérielle post-commande).
#
# Importance du await sur les écritures :
#   Le cycle d'écriture page de la 24C01 dure jusqu'à 5 ms (tWR).
#   Pendant ce temps, l'EEPROM est occupée (ACK polling non supporté sur
#   l'API writeto de MicroPython). Sans await, on bloquerait le scheduler
#   5 ms par page écrite — sensible dans une boucle asyncio à 20 Hz.
#
# Usage :
#   import asyncio, eeprom24c01_async as eep_mod
#   from machine import Pin, I2C
#
#   i2c = I2C(0, sda=Pin(8), scl=Pin(9), freq=400_000)
#   eep = eep_mod.EEPROM24C01(i2c)
#
#   async def sauvegarder():
#       await eep.write(0x00, b'Hello')   # async — libère pendant tWR
#       data = eep.read(0x00, 5)          # sync  — lecture immédiate
#       print(data)

import asyncio

_ADDR      = 0x50
_SIZE      = 128
_PAGE_SIZE = 8


class EEPROM24C01:
    """Pilote EEPROM 24C01 asynchrone — 128 octets (I²C 0x50).

    Méthodes d'écriture : COROUTINES (await requis — cycle tWR = 5 ms/page).
    Méthodes de lecture  : SYNCHRONES (pas d'attente matérielle).

    SIZE : constante de classe = 128 (octets).
    """

    SIZE = _SIZE

    def __init__(self, i2c, addr=_ADDR):
        self._i2c  = i2c
        self._addr = addr
        print(f"EEPROM 24C01 OK (adresse 0x{addr:02X}, {_SIZE} octets)")

    # ── Coroutines (écriture) ─────────────────────────────────────────────

    async def write(self, addr, data):
        """Écrit data à partir de l'adresse addr. Gère les frontières de page.

        Libère le scheduler pendant chaque cycle d'écriture page (5 ms).

        Paramètres
        ----------
        addr : adresse de départ (0x00–0x7F)
        data : bytes ou bytearray à écrire
        """
        self._check(addr, len(data))
        data = bytes(data)
        offset = 0
        while offset < len(data):
            page_off   = (addr + offset) % _PAGE_SIZE
            chunk_size = min(_PAGE_SIZE - page_off, len(data) - offset)
            chunk_addr = (addr + offset) & 0x7F
            self._i2c.writeto(self._addr, bytes([chunk_addr]) + data[offset:offset+chunk_size])
            await asyncio.sleep_ms(5)   # ← libère le scheduler (tWR ≤ 5 ms)
            offset += chunk_size

    async def write_byte(self, addr, value):
        """Écrit un seul octet. Coroutine — libère pendant tWR."""
        await self.write(addr, bytes([value & 0xFF]))

    async def erase(self, fill=0xFF):
        """Efface toute l'EEPROM (16 pages × 5 ms = 80 ms). Coroutine.

        Libère le scheduler entre chaque page effacée.
        """
        for page in range(_SIZE // _PAGE_SIZE):
            base = page * _PAGE_SIZE
            self._i2c.writeto(self._addr, bytes([base]) + bytes([fill] * _PAGE_SIZE))
            await asyncio.sleep_ms(5)   # ← libère entre chaque page
        print(f"EEPROM effacée (0x{fill:02X})")

    # ── Méthodes synchrones (lecture) ─────────────────────────────────────

    def read(self, addr, n):
        """Lit n octets à partir de addr. Synchrone — lecture immédiate."""
        self._check(addr, n)
        self._i2c.writeto(self._addr, bytes([addr & 0x7F]))
        return self._i2c.readfrom(self._addr, n)

    def read_byte(self, addr):
        """Lit un seul octet. Synchrone."""
        return self.read(addr, 1)[0]

    def dump(self):
        """Affiche le contenu complet en hexadécimal. Synchrone."""
        data = self.read(0x00, _SIZE)
        print(f"── EEPROM 24C01 dump (0x00–0x{_SIZE-1:02X}) ──")
        for i in range(0, _SIZE, 16):
            row = data[i:i+16]
            hex_str = ' '.join(f'{b:02X}' for b in row)
            asc_str = ''.join(chr(b) if 0x20 <= b < 0x7F else '.' for b in row)
            print(f"  {i:02X}: {hex_str}  {asc_str}")

    # ── Interne ──────────────────────────────────────────────────────────

    def _check(self, addr, length):
        if addr < 0 or addr >= _SIZE:
            raise ValueError(f"Adresse hors plage : 0x{addr:02X}")
        if addr + length > _SIZE:
            raise ValueError(f"Dépassement : addr=0x{addr:02X} + {length} > {_SIZE}")
