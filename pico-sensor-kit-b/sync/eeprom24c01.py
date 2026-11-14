# eeprom24c01.py — Pilote MicroPython pour EEPROM 24C01
# 128 octets, I²C adresse 0x50 (A0=A1=A2=GND)
# Waveshare Pico-Sensor-Kit-B : I²C bus 0 (GPIO8 SDA, GPIO9 SCL)
#
# Limitations matérielles :
#   - Capacité totale : 128 octets (adresses 0x00–0x7F)
#   - Adresse sur 1 octet (≠ AT24C256 qui utilise 2 octets)
#   - Écriture par page de 8 octets (ne pas traverser une frontière de page)
#   - Cycle d'écriture : 5 ms max
#
# Usage :
#   from machine import Pin, I2C
#   import eeprom24c01
#   i2c  = I2C(0, sda=Pin(8), scl=Pin(9), freq=400_000)
#   eep  = eeprom24c01.EEPROM24C01(i2c)
#   eep.write(0x00, b'Hello')
#   data = eep.read(0x00, 5)
#   eep.dump()

import time

_ADDR      = 0x50
_SIZE      = 128
_PAGE_SIZE = 8


class EEPROM24C01:
    """Pilote EEPROM 24C01 — 128 octets (I²C 0x50)."""

    SIZE = _SIZE   # accessible comme constante de classe

    def __init__(self, i2c, addr=_ADDR):
        self._i2c  = i2c
        self._addr = addr
        print(f"EEPROM 24C01 OK (adresse 0x{addr:02X}, {_SIZE} octets)")

    # ── API publique ──────────────────────────────────────────────────────

    def write(self, addr, data):
        """Écrit data (bytes ou bytearray) à partir de l'adresse addr.

        Gère automatiquement les frontières de page (8 octets).

        Paramètres
        ----------
        addr : adresse de départ (0x00–0x7F)
        data : octets à écrire
        """
        self._check(addr, len(data))
        data = bytes(data)
        offset = 0
        while offset < len(data):
            page_offset = (addr + offset) % _PAGE_SIZE
            chunk_size  = min(_PAGE_SIZE - page_offset, len(data) - offset)
            chunk_addr  = (addr + offset) & 0x7F
            self._i2c.writeto(self._addr, bytes([chunk_addr]) + data[offset:offset+chunk_size])
            time.sleep_ms(5)
            offset += chunk_size

    def write_byte(self, addr, value):
        """Écrit un seul octet à l'adresse addr."""
        self.write(addr, bytes([value & 0xFF]))

    def read(self, addr, n):
        """Lit n octets à partir de l'adresse addr. Retourne bytes.

        Paramètres
        ----------
        addr : adresse de départ (0x00–0x7F)
        n    : nombre d'octets à lire
        """
        self._check(addr, n)
        self._i2c.writeto(self._addr, bytes([addr & 0x7F]))
        return self._i2c.readfrom(self._addr, n)

    def read_byte(self, addr):
        """Lit un seul octet à l'adresse addr. Retourne int."""
        return self.read(addr, 1)[0]

    def erase(self, fill=0xFF):
        """Efface toute l'EEPROM avec la valeur fill (défaut 0xFF = vierge)."""
        for page in range(_SIZE // _PAGE_SIZE):
            base = page * _PAGE_SIZE
            self._i2c.writeto(self._addr, bytes([base]) + bytes([fill] * _PAGE_SIZE))
            time.sleep_ms(5)
        print(f"EEPROM effacée (0x{fill:02X})")

    def dump(self):
        """Affiche le contenu complet de l'EEPROM (format hexadécimal)."""
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
            raise ValueError(f"Adresse hors plage : 0x{addr:02X} (max 0x{_SIZE-1:02X})")
        if addr + length > _SIZE:
            raise ValueError(
                f"Dépassement : addr=0x{addr:02X} + {length} > {_SIZE} octets"
            )
