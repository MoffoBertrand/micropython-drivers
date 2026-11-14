"""
sx1262_async.py — Driver MicroPython asyncio pour SX1262 / LILYGO T3S3 V1.2
=============================================================================
Auteur  : Prof. MOFFO LONLA Bertrand — Labo GIA / ENSP, Université de Douala
Version : 1.0.0  —  Avril 2026

Basé sur sx1262.py v2.6.0 (version synchrone validée).
Porte les méthodes bloquantes en coroutines asyncio :
  - begin()    → async begin()
  - transmit() → async transmit()
  - receive()  → async receive()

Les méthodes SPI restent SYNCHRONES (le bus SPI ne supporte pas l'async
sur MicroPython ESP32-S3 — l'accès matériel est toujours bloquant mais
les attentes (BUSY, IRQ polling) cèdent le contrôle à la boucle d'événements
via await asyncio.sleep_ms(0) / await asyncio.sleep_ms(1)).

Brochage LILYGO T3S3 V1.2 :
  SCK=GPIO5  MISO=GPIO3  MOSI=GPIO6  CS=GPIO7
  RST=GPIO8  BUSY=GPIO34  DIO1=GPIO33

Utilisation typique :
    import asyncio
    from sx1262_async import SX1262Async, SF7, BW_125, CR_4_5

    async def main():
        radio = SX1262Async()
        ok = await radio.begin(freq=915e6, sf=SF7, bw=BW_125, cr=CR_4_5)
        # TX et RX en tâches parallèles
        asyncio.create_task(tx_task(radio))
        asyncio.create_task(rx_task(radio))
        await asyncio.sleep(0)   # laisser les tâches démarrer

    asyncio.run(main())
"""

import asyncio
from machine import SPI, Pin
import time

# ─── Registres ───────────────────────────────────────────────────────────────
REG_LR_SYNCWORD       = 0x0740
REG_TX_MODULATION     = 0x0889
REG_RX_GAIN           = 0x08AC
REG_OCP               = 0x08E7
REG_TX_CLAMP_CONFIG   = 0x08D8

# ─── Opcodes ─────────────────────────────────────────────────────────────────
RADIO_SET_SLEEP       = 0x84
RADIO_SET_STANDBY     = 0x80
RADIO_SET_TX          = 0x83
RADIO_SET_RX          = 0x82
RADIO_SET_RF_FREQ     = 0x86
RADIO_SET_PKT_TYPE    = 0x8A
RADIO_SET_TX_PARAMS   = 0x8E
RADIO_SET_MOD_PARAMS  = 0x8B
RADIO_SET_PKT_PARAMS  = 0x8C
RADIO_SET_DIO_IRQ     = 0x08
RADIO_GET_IRQ_STATUS  = 0x12
RADIO_CLR_IRQ_STATUS  = 0x02
RADIO_WRITE_REG       = 0x0D
RADIO_READ_REG        = 0x1D
RADIO_WRITE_BUFFER    = 0x0E
RADIO_READ_BUFFER     = 0x1E
RADIO_SET_REGULATOR   = 0x96
RADIO_CALIBRATE_IMG   = 0x98
RADIO_SET_PA_CONFIG   = 0x95
RADIO_SET_BUF_BASE    = 0x8F
RADIO_GET_RX_BUF_STAT = 0x13
RADIO_GET_PKT_STATUS  = 0x14
RADIO_SET_TCXO_MODE   = 0x97
RADIO_SET_DIO2_RF_SW  = 0x9D
RADIO_CALIBRATE       = 0x89

# ─── Constantes ──────────────────────────────────────────────────────────────
PACKET_TYPE_LORA      = 0x01
USE_DCDC              = 0x01
BOOSTED_GAIN          = 0x96
TCXO_CTRL_3_3V        = 0x07
ALL_DEVICES_CALIBRATE = 0x7F

IRQ_TX_DONE           = 0x0001
IRQ_RX_DONE           = 0x0002
IRQ_HEADER_ERROR      = 0x0020
IRQ_CRC_ERROR         = 0x0040
IRQ_RX_TX_TIMEOUT     = 0x0200
IRQ_RADIO_ALL         = 0xFFFF

# Spreading Factors
SF5  = 0x05; SF6  = 0x06; SF7  = 0x07; SF8  = 0x08
SF9  = 0x09; SF10 = 0x0A; SF11 = 0x0B; SF12 = 0x0C

# Bandwidths
BW_7   = 0x00; BW_10  = 0x08; BW_15  = 0x01; BW_20  = 0x09
BW_31  = 0x02; BW_41  = 0x0A; BW_62  = 0x03
BW_125 = 0x04; BW_250 = 0x05; BW_500 = 0x06

# Coding Rates
CR_4_5 = 0x01; CR_4_6 = 0x02; CR_4_7 = 0x03; CR_4_8 = 0x04

# SyncWords
LORA_PRIVATE_SYNCWORD = 0x1424
LORA_PUBLIC_SYNCWORD  = 0x3444


class SX1262Async:
    """
    Driver asyncio pour SX1262 — LILYGO T3S3 V1.2.

    Les attentes actives (BUSY, IRQ polling) utilisent await asyncio.sleep_ms()
    au lieu de time.sleep_ms() — ce qui cède le contrôle à la boucle
    d'événements pendant l'attente, permettant l'exécution parallèle
    d'autres coroutines (OLED, capteurs, console...).

    Le bus SPI reste synchrone (accès matériel non-async sur ESP32-S3).
    """

    def __init__(self, sck=5, miso=3, mosi=6, cs=7,
                 rst=8, busy=34, dio1=33, spi_freq=8_000_000):
        """Broches par défaut = LILYGO T3S3 V1.2."""
        self._spi  = SPI(1, baudrate=spi_freq, polarity=0, phase=0,
                         sck=Pin(sck), mosi=Pin(mosi), miso=Pin(miso))
        self._cs   = Pin(cs,   Pin.OUT, value=1)
        self._rst  = Pin(rst,  Pin.OUT, value=1)
        self._busy = Pin(busy, Pin.IN)
        self._dio1 = Pin(dio1, Pin.IN)
        # Paramètres sauvegardés
        self._freq = 915e6; self._sf = SF7; self._bw = BW_125
        self._cr   = CR_4_5; self._tx_power = 14; self._crc = True
        # Lock pour protéger l'accès SPI contre les accès concurrents
        self._lock = asyncio.Lock()

    # ─── SPI bas niveau (synchrone) ───────────────────────────────────────────

    def _check_busy_sync(self, timeout_ms=50):
        """Attente synchrone BUSY=0 — utilisée seulement dans begin()/reset()."""
        t0 = time.ticks_ms()
        while self._busy.value():
            if time.ticks_diff(time.ticks_ms(), t0) > timeout_ms:
                return False
            time.sleep_us(100)
        return True

    async def _check_busy(self, timeout_ms=50):
        """
        Attente asynchrone BUSY=0.
        Cède le contrôle à la boucle d'événements à chaque itération.
        """
        t0 = time.ticks_ms()
        while self._busy.value():
            if time.ticks_diff(time.ticks_ms(), t0) > timeout_ms:
                return False
            await asyncio.sleep_ms(0)   # yield — ne bloque pas les autres tâches
        return True

    def _spi_write(self, data):
        """Écriture SPI brute (synchrone — le matériel l'exige)."""
        self._cs(0)
        self._spi.write(bytes(data))
        self._cs(1)

    def _spi_read_write(self, tx):
        """Lecture/écriture SPI brute (synchrone)."""
        rx = bytearray(len(tx))
        self._cs(0)
        self._spi.write_readinto(bytearray(tx), rx)
        self._cs(1)
        return rx

    async def _write_command(self, opcode, *args):
        """Envoie une commande avec attente BUSY async avant et après."""
        await self._check_busy()
        self._spi_write(bytes([opcode]) + bytes(args))
        if opcode != RADIO_SET_SLEEP:
            await self._check_busy()

    def _write_register(self, addr, *vals):
        """Écriture registre (synchrone, pas de check_busy après)."""
        self._check_busy_sync()
        self._cs(0)
        self._spi.write(bytes([RADIO_WRITE_REG,
                               (addr >> 8) & 0xFF, addr & 0xFF]) + bytes(vals))
        self._cs(1)

    def _read_irq_status(self):
        """Lecture IRQ sans attente BUSY (lisible pendant TX/RX actif)."""
        rx = self._spi_read_write([RADIO_GET_IRQ_STATUS, 0xFF, 0xFF, 0xFF])
        return (rx[2] << 8) | rx[3]

    # ─── Reset & init ─────────────────────────────────────────────────────────

    def reset(self):
        """Reset matériel (synchrone — appelé avant la boucle asyncio)."""
        time.sleep_ms(10)
        self._rst(0); time.sleep_ms(2)
        self._rst(1); time.sleep_ms(25)
        self._check_busy_sync(timeout_ms=100)

    def check_device(self):
        """Vérifie la présence du SX1262 (synchrone)."""
        try:
            self._write_register(REG_LR_SYNCWORD, 0x14, 0x24)
            self._check_busy_sync()
            tx = bytearray([RADIO_READ_REG, 0x07, 0x40, 0xFF, 0xFF, 0xFF])
            rx = self._spi_read_write(tx)
            return rx[4] == 0x14 and rx[5] == 0x24
        except Exception:
            return False

    async def begin(self, freq=915e6, sf=SF7, bw=BW_125, cr=CR_4_5,
                    tx_power=14, sync_word=LORA_PRIVATE_SYNCWORD, crc=True):
        """
        Initialisation complète asynchrone du SX1262.
        Même séquence que sx1262.py v2.6.0, avec await sur les attentes.
        """
        self._freq = freq; self._sf = sf; self._bw = bw
        self._cr = cr; self._tx_power = tx_power; self._crc = crc

        async with self._lock:
            # 1. Reset
            self.reset()

            # 2. STANDBY RC
            await self._write_command(RADIO_SET_STANDBY, 0x00)

            # 3. DC-DC
            await self._write_command(RADIO_SET_REGULATOR, USE_DCDC)

            # 4. PA Config
            await self._write_command(RADIO_SET_PA_CONFIG, 0x04, 0x07, 0x00, 0x01)

            # 5. DIO3 → TCXO 3.3V (CRITIQUE — HPD17 module)
            await self._write_command(RADIO_SET_TCXO_MODE, TCXO_CTRL_3_3V,
                                      0x00, 0x00, 0x64)

            # 6. Calibration complète après TCXO
            await self._write_command(RADIO_CALIBRATE, ALL_DEVICES_CALIBRATE)
            await asyncio.sleep_ms(10)
            await self._check_busy(timeout_ms=1000)

            # 7. DIO2 → RF switch
            await self._write_command(RADIO_SET_DIO2_RF_SW, 0x01)

            # 8. PKT_TYPE LoRa
            await self._write_command(RADIO_SET_PKT_TYPE, PACKET_TYPE_LORA)

            # 9. RF Frequency
            frf = int(freq) * (1 << 25) // 32_000_000
            await self._write_command(RADIO_SET_RF_FREQ,
                                      (frf >> 24) & 0xFF, (frf >> 16) & 0xFF,
                                      (frf >>  8) & 0xFF,  frf        & 0xFF)

            # 10. Modulation
            ldro = 0x01 if (sf >= SF11 and bw == BW_125) else 0x00
            await self._write_command(RADIO_SET_MOD_PARAMS, sf, bw, cr, ldro)

            # 11. Buffer base
            await self._write_command(RADIO_SET_BUF_BASE, 0x00, 0x00)

            # 12. PKT params
            crc_val = 0x01 if crc else 0x00
            await self._write_command(RADIO_SET_PKT_PARAMS,
                                      0x00, 0x08, 0x00, 0xFF, crc_val, 0x00)

            # 13. IRQ
            await self._write_command(RADIO_SET_DIO_IRQ,
                                      0xFF, 0xFF,
                                      (IRQ_TX_DONE | IRQ_RX_TX_TIMEOUT) >> 8,
                                      (IRQ_TX_DONE | IRQ_RX_TX_TIMEOUT) & 0xFF,
                                      0x00, 0x00, 0x00, 0x00)

            # 14. High sensitivity
            self._write_register(REG_RX_GAIN, BOOSTED_GAIN)

            # 15. Errata §15.2 TX_CLAMP
            self._write_register(REG_TX_CLAMP_CONFIG, 0x1E)
            self._write_register(REG_TX_CLAMP_CONFIG, 0x1F)

            # 16. OCP
            self._write_register(REG_OCP, 0x38)

            # 17. TX Params
            await self._write_command(RADIO_SET_TX_PARAMS, tx_power & 0xFF, 0x04)

            # 18. SyncWord
            self._write_register(REG_LR_SYNCWORD,
                                 (sync_word >> 8) & 0xFF,
                                  sync_word       & 0xFF)

            # 19. STANDBY final propre (pas de CALIBRATE_IMAGE)
            await self._write_command(RADIO_SET_STANDBY, 0x00)

        return self.check_device()

    # ─── Émission asynchrone ──────────────────────────────────────────────────

    async def transmit(self, data, timeout_ms=5000):
        """
        Envoie un paquet LoRa de manière asynchrone.

        L'attente TxDone utilise await asyncio.sleep_ms(1) au lieu de
        time.sleep_ms(1) — le thread principal reste libre pendant l'émission
        (~83 ms pour SF7/BW125 à 915 MHz).

        Retourne True si TxDone, False si timeout.
        """
        if not data or len(data) > 255:
            raise ValueError("Payload vide ou > 255 octets")

        async with self._lock:
            # 0. STANDBY + reconfiguration minimale
            await self._check_busy()
            self._spi_write([RADIO_SET_STANDBY, 0x00])
            await self._check_busy()
            self._spi_write([RADIO_SET_PA_CONFIG, 0x04, 0x07, 0x00, 0x01])
            await self._check_busy()
            self._spi_write([RADIO_SET_TX_PARAMS, self._tx_power & 0xFF, 0x04])
            await self._check_busy()

            # 1. PKT_PARAMS
            crc_val = 0x01 if self._crc else 0x00
            await self._check_busy()
            self._spi_write([RADIO_SET_PKT_PARAMS,
                             0x00, 0x08, 0x00, len(data), crc_val, 0x00])
            await self._check_busy()

            # 2. Write buffer
            await self._check_busy()
            self._cs(0)
            self._spi.write(bytes([RADIO_WRITE_BUFFER, 0x00]) + bytes(data))
            self._cs(1)
            await self._check_busy()

            # 3. Errata §15.1
            tx_mod_val = 0x04 if self._bw == BW_500 else 0x05
            await self._check_busy()
            self._spi_write([RADIO_WRITE_REG, 0x08, 0x89, tx_mod_val])

            # 4. CLR_IRQ
            await self._check_busy()
            self._spi_write([RADIO_CLR_IRQ_STATUS, 0xFF, 0xFF])
            await self._check_busy()

            # 5. SET_TX
            tval = min((timeout_ms << 6), 0xFFFFFF)
            await self._check_busy()
            self._spi_write([RADIO_SET_TX,
                             (tval >> 16) & 0xFF,
                             (tval >>  8) & 0xFF,
                              tval        & 0xFF])
            # Pas de check_busy — chip en TX actif (BUSY=1)

            # 6. Polling IRQ asynchrone
            t0 = time.ticks_ms()
            while True:
                flags = self._read_irq_status()

                if flags & IRQ_TX_DONE:
                    while self._busy.value():
                        await asyncio.sleep_ms(0)
                    self._spi_write([RADIO_CLR_IRQ_STATUS, 0xFF, 0xFF])
                    return True

                if flags & IRQ_RX_TX_TIMEOUT:
                    while self._busy.value():
                        await asyncio.sleep_ms(0)
                    self._spi_write([RADIO_CLR_IRQ_STATUS, 0xFF, 0xFF])
                    return False

                if time.ticks_diff(time.ticks_ms(), t0) > timeout_ms + 500:
                    self._spi_write([RADIO_CLR_IRQ_STATUS, 0xFF, 0xFF])
                    return False

                await asyncio.sleep_ms(1)   # yield — libère la boucle d'événements

    # ─── Réception asynchrone ─────────────────────────────────────────────────

    async def receive(self, timeout_ms=0, max_len=255):
        """
        Reçoit un paquet LoRa de manière asynchrone.

        Le polling RxDone utilise await asyncio.sleep_ms(1) — la boucle
        d'événements reste active pendant toute la fenêtre d'écoute
        (jusqu'à plusieurs secondes en RX continu).

        Retourne (bytes, rssi_dbm, snr_db) ou None si timeout/erreur.
        """
        async with self._lock:
            # STANDBY + PKT_PARAMS
            await self._write_command(RADIO_SET_STANDBY, 0x00)
            crc_val = 0x01 if self._crc else 0x00
            await self._check_busy()
            self._spi_write([RADIO_SET_PKT_PARAMS,
                             0x00, 0x08, 0x00, max_len & 0xFF, crc_val, 0x00])
            await self._check_busy()

            # Reconfigurer IRQ pour RX
            await self._check_busy()
            self._spi_write([RADIO_SET_DIO_IRQ,
                             0xFF, 0xFF,
                             (IRQ_RX_DONE | IRQ_RX_TX_TIMEOUT) >> 8,
                             (IRQ_RX_DONE | IRQ_RX_TX_TIMEOUT) & 0xFF,
                             0x00, 0x00, 0x00, 0x00])
            await self._check_busy()

            # CLR_IRQ
            self._spi_write([RADIO_CLR_IRQ_STATUS, 0xFF, 0xFF])
            await self._check_busy()

            # SET_RX
            tval = 0xFFFFFF if timeout_ms == 0 else min((timeout_ms << 6), 0xFFFFFE)
            await self._check_busy()
            self._spi_write([RADIO_SET_RX,
                             (tval >> 16) & 0xFF,
                             (tval >>  8) & 0xFF,
                              tval        & 0xFF])

            # Polling IRQ asynchrone — cède le contrôle toutes les 1 ms
            t0 = time.ticks_ms()
            while True:
                flags = self._read_irq_status()

                if flags & IRQ_RX_DONE:
                    while self._busy.value():
                        await asyncio.sleep_ms(0)
                    break

                if flags & (IRQ_RX_TX_TIMEOUT | IRQ_CRC_ERROR | IRQ_HEADER_ERROR):
                    while self._busy.value():
                        await asyncio.sleep_ms(0)
                    self._spi_write([RADIO_CLR_IRQ_STATUS, 0xFF, 0xFF])
                    return None

                if timeout_ms > 0 and time.ticks_diff(time.ticks_ms(), t0) > timeout_ms + 1000:
                    self._spi_write([RADIO_CLR_IRQ_STATUS, 0xFF, 0xFF])
                    return None

                await asyncio.sleep_ms(1)   # yield

            # Stopper RX
            await self._write_command(RADIO_SET_STANDBY, 0x00)
            self._spi_write([RADIO_CLR_IRQ_STATUS, 0xFF, 0xFF])

            # Lire buffer
            rx_buf = self._spi_read_write([RADIO_GET_RX_BUF_STAT, 0xFF, 0xFF, 0xFF])
            pkt_len  = rx_buf[2]
            rx_start = rx_buf[3]
            if pkt_len == 0:
                return None

            await self._check_busy()
            cmd = bytearray([RADIO_READ_BUFFER, rx_start, 0xFF]) + bytearray(pkt_len)
            rx  = self._spi_read_write(cmd)
            payload = bytes(rx[3:3 + pkt_len])

            # RSSI / SNR
            ps = self._spi_read_write([RADIO_GET_PKT_STATUS, 0xFF, 0xFF, 0xFF, 0xFF])
            rssi = -ps[2] / 2
            snr  = ps[3] / 4 if ps[3] < 128 else (ps[3] - 256) / 4

            return payload, rssi, snr

    # ─── Utilitaires ──────────────────────────────────────────────────────────

    async def standby(self):
        await self._write_command(RADIO_SET_STANDBY, 0x00)

    async def sleep(self, warm=True):
        await self._write_command(RADIO_SET_SLEEP, 0x04 if warm else 0x00)

    def __repr__(self):
        bw_map = {BW_125:125, BW_250:250, BW_500:500, BW_62:62}
        return (f"SX1262Async(freq={self._freq/1e6:.1f} MHz, SF={self._sf}, "
                f"BW={bw_map.get(self._bw,'?')} kHz, CR=4/{self._cr+4}, "
                f"TxPwr={self._tx_power} dBm)")
