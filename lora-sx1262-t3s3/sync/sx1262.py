"""
sx1262.py — Driver MicroPython SX1262 pour LILYGO T3S3 V1.2
============================================================
Auteur  : Prof. MOFFO LONLA Bertrand — Labo GIA / ENSP, Université de Douala
Version : 2.1.0  —  Avril 2026

Inspiré de la bibliothèque SX126XLT de Stuart Robinson (MIT License)
https://github.com/StuartsProjects/SX12XX-LoRa

Brochage LILYGO T3S3 V1.2 (fiche technique officielle) :
  SCK=GPIO5  MISO=GPIO3  MOSI=GPIO6  CS=GPIO7
  RST=GPIO8  BUSY=GPIO34  DIO1=GPIO33

Changelog :
  v1.x — Versions de développement (corrections progressives)
  v2.0.0 — Réécriture complète inspirée SX126XLT (Stuart Robinson)
    v2.1.0 — Correction TCXO (cause racine ExecFail SET_TX) :
              DIO3→TCXO_3.3V + calibrateDevice(ALL) + DIO2→RF_switch
              _write_register sans _check_busy final (CmdError faux) :
    * readCommand()  : dummy byte = 0xFF (conforme SX126XLT)
    * Timeout SET_TX/RX : ms × 64 (conforme setTx()/setRx() SX126XLT)
    * Errata §15.1  : REG_TX_MODULATION 0x0889 appliqué avant SET_TX
    * Errata §15.2  : REG_TX_CLAMP_CONFIG 0x08D8 = 0x1E→0x1F (PA fix)
    * setHighSensitivity : REG_RX_GAIN 0x08AC = 0x96 (BOOSTED_GAIN)
    * writeCommand() : _check_busy() avant ET après (sauf SET_SLEEP)
    * transmit() : attend DIO1 via polling IRQ sans _check_busy()
    * receive()  : idem, STANDBY après RxDone
    * Buffer base : TX=0x00, RX=0x00 (aligné SX126XLT)
    * Preamble = 8 symboles (aligné SX126XLT)
"""

from machine import SPI, Pin
import time

# ─── Adresses registres ───────────────────────────────────────────────────────
REG_LR_SYNCWORD       = 0x0740
REG_TX_MODULATION     = 0x0889   # Errata §15.1 — modulation fix BW
REG_RX_GAIN           = 0x08AC   # Boosted gain / high sensitivity
REG_OCP               = 0x08E7   # Over-Current Protection
REG_TX_CLAMP_CONFIG   = 0x08D8   # Errata §15.2 — PA clamping fix

# ─── Opcodes SX1262 ──────────────────────────────────────────────────────────
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
RADIO_GET_STATUS      = 0xC0
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
RADIO_SET_TCXO_MODE   = 0x97   # DIO3 → TCXO control
RADIO_SET_DIO2_RF_SW  = 0x9D   # DIO2 → RF switch control
RADIO_CALIBRATE       = 0x89   # Calibration complète

# ─── Constantes ──────────────────────────────────────────────────────────────
PACKET_TYPE_LORA      = 0x01
USE_DCDC              = 0x01
BOOSTED_GAIN          = 0x96

IRQ_TX_DONE           = 0x0001
IRQ_RX_DONE           = 0x0002
IRQ_HEADER_ERROR      = 0x0020
IRQ_CRC_ERROR         = 0x0040
IRQ_RX_TX_TIMEOUT     = 0x0200
IRQ_RADIO_ALL         = 0xFFFF

# Spreading Factors
SF5  = 0x05; SF6  = 0x06; SF7  = 0x07; SF8  = 0x08
SF9  = 0x09; SF10 = 0x0A; SF11 = 0x0B; SF12 = 0x0C

# Bandwidths (valeur registre SX1262)
BW_7   = 0x00; BW_10  = 0x08; BW_15  = 0x01; BW_20  = 0x09
BW_31  = 0x02; BW_41  = 0x0A; BW_62  = 0x03
BW_125 = 0x04; BW_250 = 0x05; BW_500 = 0x06

# Coding Rates
CR_4_5 = 0x01; CR_4_6 = 0x02; CR_4_7 = 0x03; CR_4_8 = 0x04

# SyncWords
LORA_PRIVATE_SYNCWORD = 0x1424
LORA_PUBLIC_SYNCWORD  = 0x3444
# TCXO tension (HPD17 module = 3.3V)
TCXO_CTRL_3_3V        = 0x07
ALL_DEVICES_CALIBRATE = 0x7F   # calibrer tous les blocs
LORA_PUBLIC_SYNCWORD  = 0x3444


class SX1262:
    """
    Driver MicroPython pour SX1262 — LILYGO T3S3 V1.2.
    Inspiré de SX126XLT (Stuart Robinson, MIT License).

    Exemple :
        radio = SX1262()
        ok = radio.begin(freq=915e6, sf=SF7, bw=BW_125, cr=CR_4_5, tx_power=14)
        radio.transmit(b"Hello 915 !")
        result = radio.receive(timeout_ms=5000)
        if result:
            data, rssi, snr = result
            print(data, rssi, snr)
    """

    def __init__(self, sck=5, miso=3, mosi=6, cs=7,
                 rst=8, busy=34, dio1=33, spi_freq=8_000_000):
        """Broches par défaut = LILYGO T3S3 V1.2 (fiche technique officielle)."""
        self._spi  = SPI(1, baudrate=spi_freq, polarity=0, phase=0,
                         sck=Pin(sck), mosi=Pin(mosi), miso=Pin(miso))
        self._cs   = Pin(cs,   Pin.OUT, value=1)
        self._rst  = Pin(rst,  Pin.OUT, value=1)
        self._busy = Pin(busy, Pin.IN)
        self._dio1 = Pin(dio1, Pin.IN)
        # Paramètres sauvegardés
        self._freq = 915e6; self._sf = SF7; self._bw = BW_125
        self._cr   = CR_4_5; self._tx_power = 14; self._crc = True

    # ─── SPI bas niveau ───────────────────────────────────────────────────────

    def _check_busy(self, timeout_ms=10):
        """Attend BUSY=0 (d'après checkBusy() SX126XLT — timeout 10 ms)."""
        t0 = time.ticks_ms()
        while self._busy.value():
            if time.ticks_diff(time.ticks_ms(), t0) > timeout_ms:
                return False
            time.sleep_us(100)
        return True

    def _write_command(self, opcode, *args):
        """
        Envoie une commande (d'après writeCommand() SX126XLT).
        _check_busy() avant ET après, sauf pour SET_SLEEP.
        """
        self._check_busy()
        self._cs(0)
        self._spi.write(bytes([opcode]) + bytes(args))
        self._cs(1)
        if opcode != RADIO_SET_SLEEP:
            self._check_busy()

    def _read_command(self, opcode, n_data):
        """
        Lit n_data octets (d'après readCommand() SX126XLT).
        Dummy byte = 0xFF (conforme SX126XLT, pas 0x00).
        """
        self._check_busy()
        tx = bytearray([opcode, 0xFF] + [0xFF] * n_data)
        rx = bytearray(len(tx))
        self._cs(0)
        self._spi.write_readinto(tx, rx)
        self._cs(1)
        return rx[2:]

    def _write_register(self, addr, *vals):
        """
        Écrit des octets dans les registres internes.
        D'après writeRegisters() SX126XLT : checkBusy() AVANT seulement.
        Pas de checkBusy() après — WRITE_REGISTER ne met pas à jour
        cmd_status comme les commandes normales (sinon → CmdError faux).
        """
        self._check_busy()
        self._cs(0)
        self._spi.write(bytes([RADIO_WRITE_REG,
                               (addr >> 8) & 0xFF, addr & 0xFF])
                        + bytes(vals))
        self._cs(1)
        # PAS de _check_busy() ici — intentionnel (voir SX126XLT writeRegisters)

    def _read_register(self, addr, n=1):
        """Lit n octets depuis un registre interne."""
        self._check_busy()
        tx = bytearray([RADIO_READ_REG,
                        (addr >> 8) & 0xFF, addr & 0xFF,
                        0xFF] + [0xFF] * n)
        rx = bytearray(len(tx))
        self._cs(0)
        self._spi.write_readinto(tx, rx)
        self._cs(1)
        return rx[4:]

    def _read_irq_status(self):
        """
        Lit IRQ status SANS _check_busy() — intentionnel.
        Le SX1262 maintient BUSY=1 pendant TX/RX actif.
        GET_IRQ_STATUS est lisible à tout moment (datasheet §13.3.2).
        """
        tx = bytearray([RADIO_GET_IRQ_STATUS, 0xFF, 0xFF, 0xFF])
        rx = bytearray(4)
        self._cs(0)
        self._spi.write_readinto(tx, rx)
        self._cs(1)
        return (rx[2] << 8) | rx[3]

    def _clear_irq(self, mask=IRQ_RADIO_ALL):
        """Efface les flags IRQ (avec _check_busy)."""
        self._check_busy()
        self._cs(0)
        self._spi.write(bytes([RADIO_CLR_IRQ_STATUS,
                               (mask >> 8) & 0xFF, mask & 0xFF]))
        self._cs(1)
        self._check_busy()

    # ─── Reset & vérification ─────────────────────────────────────────────────

    def reset(self):
        """
        Reset matériel (d'après resetDevice() SX126XLT) :
        delay(10) → RST LOW 2ms → RST HIGH → delay(25) → checkBusy()
        """
        time.sleep_ms(10)
        self._rst(0)
        time.sleep_ms(2)
        self._rst(1)
        time.sleep_ms(25)
        self._check_busy(timeout_ms=100)

    def check_device(self):
        """Vérifie la présence du SX1262 via lecture/écriture SyncWord."""
        try:
            self._write_register(REG_LR_SYNCWORD, 0x14, 0x24)
            back = self._read_register(REG_LR_SYNCWORD, 2)
            return back[0] == 0x14 and back[1] == 0x24
        except Exception:
            return False

    # ─── Initialisation ───────────────────────────────────────────────────────

    def begin(self, freq=915e6, sf=SF7, bw=BW_125, cr=CR_4_5,
              tx_power=14, sync_word=LORA_PRIVATE_SYNCWORD, crc=True):
        """
        Initialisation complète SX1262 en mode LoRa.
        Séquence alignée sur setupLoRa() de SX126XLT (Stuart Robinson).
        """
        self._freq = freq; self._sf = sf; self._bw = bw
        self._cr   = cr;   self._tx_power = tx_power; self._crc = crc

        # Séquence EXACTE de setupLoRa() de SX126XLT (Stuart Robinson)
        # complétée avec les workarounds erratas SX1262

        # 1. Reset matériel
        self.reset()

        # 2. STANDBY RC — obligatoire en premier
        self._write_command(RADIO_SET_STANDBY, 0x00)

        # 3. Régulateur DC-DC
        self._write_command(RADIO_SET_REGULATOR, USE_DCDC)

        # 4. PA Config : dutycycle=0x04, hpMax=0x07, deviceSel=0x00(SX1262), paLut=0x01
        self._write_command(RADIO_SET_PA_CONFIG, 0x04, 0x07, 0x00, 0x01)

        # 5. DIO3 → TCXO control 3.3V (CRITIQUE sur HPD17/T3S3 V1.2)
        # Le module HPD17 utilise un TCXO 32 MHz alimenté par DIO3.
        # Sans cette commande, le PLL ne démarre pas → SET_TX ExecFail.
        # timeout = 0x000064 = 100 × 15.625µs = ~1.56 ms (délai démarrage TCXO)
        self._write_command(RADIO_SET_TCXO_MODE, TCXO_CTRL_3_3V,
                            0x00, 0x00, 0x64)

        # 6. Calibration complète de tous les blocs (requis après TCXO)
        # 0x7F = ALLDevices : RC13M, RC64K, PLL, ADC, BULK_P, BULK_N, IMG
        self._write_command(RADIO_CALIBRATE, ALL_DEVICES_CALIBRATE)
        time.sleep_ms(10)   # calibration ~3.5 ms selon datasheet
        self._check_busy(timeout_ms=500)

        # 7. DIO2 → RF switch control (antenne TX/RX)
        self._write_command(RADIO_SET_DIO2_RF_SW, 0x01)

        # 8. Type paquet : LoRa
        self._write_command(RADIO_SET_PKT_TYPE, PACKET_TYPE_LORA)

        # 9. Fréquence RF
        frf = int(freq) * (1 << 25) // 32_000_000
        self._write_command(RADIO_SET_RF_FREQ,
                            (frf >> 24) & 0xFF, (frf >> 16) & 0xFF,
                            (frf >>  8) & 0xFF,  frf        & 0xFF)

        # 10. Modulation : SF, BW, CR, LDRO
        ldro = 0x01 if (sf >= SF11 and bw == BW_125) else 0x00
        self._write_command(RADIO_SET_MOD_PARAMS, sf, bw, cr, ldro)

        # 11. Buffer base : TX=0x00, RX=0x00
        self._write_command(RADIO_SET_BUF_BASE, 0x00, 0x00)

        # 12. Paramètres paquet : preamble=8, header explicite, 255o, CRC, IQ normal
        crc_val = 0x01 if crc else 0x00
        self._write_command(RADIO_SET_PKT_PARAMS,
                            0x00, 0x08, 0x00, 0xFF, crc_val, 0x00)

        # 13. IRQ global — tous masques actifs sur DIO1
        self._write_command(RADIO_SET_DIO_IRQ,
                            0xFF, 0xFF,
                            (IRQ_TX_DONE | IRQ_RX_TX_TIMEOUT) >> 8,
                            (IRQ_TX_DONE | IRQ_RX_TX_TIMEOUT) & 0xFF,
                            0x00, 0x00, 0x00, 0x00)

        # 14. High sensitivity RX (BOOSTED_GAIN)
        self._write_register(REG_RX_GAIN, BOOSTED_GAIN)

        # 15. Errata §15.2 — TX_CLAMP_CONFIG (PA fix)
        self._write_register(REG_TX_CLAMP_CONFIG, 0x1E)
        self._write_register(REG_TX_CLAMP_CONFIG, 0x1F)

        # 16. OCP = 0x38 → 140 mA
        self._write_register(REG_OCP, 0x38)

        # 17. TX Params : puissance + ramp 200 µs
        self._write_command(RADIO_SET_TX_PARAMS, tx_power & 0xFF, 0x04)

        # 18. SyncWord
        self._write_register(REG_LR_SYNCWORD,
                             (sync_word >> 8) & 0xFF,
                              sync_word       & 0xFF)

        # 19. Calibration image 915 MHz (902–928 MHz)
        self._write_command(RADIO_CALIBRATE_IMG, 0xE1, 0xE9)
        self._check_busy(timeout_ms=500)

        return self.check_device()

    # ─── Émission ─────────────────────────────────────────────────────────────

    def _apply_tx_mod_errata(self):
        """
        Errata §15.1 — REG_TX_MODULATION 0x0889.
        Appliqué avant SET_TX (d'après set_REGTXMODULATION() et setTx() SX126XLT).
        BW=500 kHz : bit2=0 ; BW<500 kHz : bit2=1.
        """
        v = self._read_register(REG_TX_MODULATION, 1)[0]
        v = (v & 0xFB) if self._bw == BW_500 else (v | 0x04)
        self._write_register(REG_TX_MODULATION, v)

    def transmit(self, data, timeout_ms=5000):
        """
        Envoie un paquet LoRa (d'après transmit() SX126XLT).
        Retourne True si TxDone, False si timeout.
        """
        if not data or len(data) > 255:
            raise ValueError("Payload vide ou > 255 octets")

        self._write_command(RADIO_SET_STANDBY, 0x00)

        # Mettre à jour longueur payload dans PKT_PARAMS
        crc_val = 0x01 if self._crc else 0x00
        self._write_command(RADIO_SET_PKT_PARAMS,
                            0x00, 0x08, 0x00, len(data), crc_val, 0x00)

        # Écrire payload dans buffer SX1262 (base 0x00)
        self._check_busy()
        self._cs(0)
        self._spi.write(bytes([RADIO_WRITE_BUFFER, 0x00]) + bytes(data))
        self._cs(1)
        self._check_busy()

        # Errata §15.1 — doit être appliqué AVANT SET_TX
        self._apply_tx_mod_errata()

        # Reconfigurer IRQ pour TX
        self._write_command(RADIO_SET_DIO_IRQ,
                            0xFF, 0xFF,
                            (IRQ_TX_DONE | IRQ_RX_TX_TIMEOUT) >> 8,
                            (IRQ_TX_DONE | IRQ_RX_TX_TIMEOUT) & 0xFF,
                            0x00, 0x00, 0x00, 0x00)
        self._clear_irq()

        # SET_TX — timeout : ms × 64 (d'après setTx() SX126XLT)
        tval = min((timeout_ms << 6), 0xFFFFFF)
        self._check_busy()
        self._cs(0)
        self._spi.write(bytes([RADIO_SET_TX,
                               (tval >> 16) & 0xFF,
                               (tval >>  8) & 0xFF,
                                tval        & 0xFF]))
        self._cs(1)
        # Pas de _check_busy() ici — chip en mode TX actif (BUSY=1)

        # Polling IRQ sans _check_busy (TX actif)
        t0 = time.ticks_ms()
        while True:
            irq = self._read_irq_status()
            if irq & IRQ_TX_DONE:
                self._check_busy()
                self._clear_irq()
                return True
            if irq & IRQ_RX_TX_TIMEOUT:
                self._check_busy()
                self._clear_irq()
                return False
            if time.ticks_diff(time.ticks_ms(), t0) > timeout_ms + 500:
                self._clear_irq()
                return False
            time.sleep_ms(1)

    # ─── Réception ────────────────────────────────────────────────────────────

    def receive(self, timeout_ms=0, max_len=255):
        """
        Reçoit un paquet LoRa (d'après receive() SX126XLT).
        Retourne (bytes, rssi, snr) ou None si timeout/erreur.
        """
        self._write_command(RADIO_SET_STANDBY, 0x00)

        # PKT_PARAMS avec max_len
        crc_val = 0x01 if self._crc else 0x00
        self._write_command(RADIO_SET_PKT_PARAMS,
                            0x00, 0x08, 0x00, max_len & 0xFF, crc_val, 0x00)

        # Reconfigurer IRQ pour RX
        self._write_command(RADIO_SET_DIO_IRQ,
                            0xFF, 0xFF,
                            (IRQ_RX_DONE | IRQ_RX_TX_TIMEOUT) >> 8,
                            (IRQ_RX_DONE | IRQ_RX_TX_TIMEOUT) & 0xFF,
                            0x00, 0x00, 0x00, 0x00)
        self._clear_irq()

        # SET_RX — timeout : ms × 64, 0xFFFFFF = continu
        tval = 0xFFFFFF if timeout_ms == 0 else min((timeout_ms << 6), 0xFFFFFE)
        self._check_busy()
        self._cs(0)
        self._spi.write(bytes([RADIO_SET_RX,
                               (tval >> 16) & 0xFF,
                               (tval >>  8) & 0xFF,
                                tval        & 0xFF]))
        self._cs(1)

        # Polling IRQ sans _check_busy (RX actif)
        t0 = time.ticks_ms()
        while True:
            irq = self._read_irq_status()
            if irq & IRQ_RX_DONE:
                self._check_busy()
                break
            if irq & (IRQ_RX_TX_TIMEOUT | IRQ_CRC_ERROR | IRQ_HEADER_ERROR):
                self._check_busy()
                self._clear_irq()
                return None
            if timeout_ms > 0 and time.ticks_diff(time.ticks_ms(), t0) > timeout_ms + 1000:
                self._clear_irq()
                return None
            time.sleep_ms(1)

        # Arrêter la réception (comme setMode(STDBY_RC) dans receive() SX126XLT)
        self._write_command(RADIO_SET_STANDBY, 0x00)
        self._clear_irq()

        # Lire statut buffer
        buf_stat = self._read_command(RADIO_GET_RX_BUF_STAT, 2)
        pkt_len  = buf_stat[0]
        rx_start = buf_stat[1]
        if pkt_len == 0:
            return None

        # Lire payload
        self._check_busy()
        cmd = bytearray([RADIO_READ_BUFFER, rx_start, 0xFF]) + bytearray(pkt_len)
        rx  = bytearray(len(cmd))
        self._cs(0)
        self._spi.write_readinto(cmd, rx)
        self._cs(1)
        payload = bytes(rx[3:3 + pkt_len])

        # RSSI et SNR
        pkt_stat = self._read_command(RADIO_GET_PKT_STATUS, 3)
        rssi = -pkt_stat[0] / 2
        snr  = pkt_stat[1] / 4 if pkt_stat[1] < 128 else (pkt_stat[1] - 256) / 4

        return payload, rssi, snr

    # ─── Utilitaires ──────────────────────────────────────────────────────────

    def standby(self):
        self._write_command(RADIO_SET_STANDBY, 0x00)

    def sleep(self, warm=True):
        self._write_command(RADIO_SET_SLEEP, 0x04 if warm else 0x00)

    def set_frequency(self, freq):
        self._write_command(RADIO_SET_STANDBY, 0x00)
        frf = int(freq) * (1 << 25) // 32_000_000
        self._write_command(RADIO_SET_RF_FREQ,
                            (frf >> 24) & 0xFF, (frf >> 16) & 0xFF,
                            (frf >>  8) & 0xFF,  frf        & 0xFF)
        self._freq = freq

    def set_tx_power(self, dbm):
        self._write_command(RADIO_SET_STANDBY, 0x00)
        self._write_command(RADIO_SET_TX_PARAMS, dbm & 0xFF, 0x04)
        self._tx_power = dbm

    def __repr__(self):
        bw_map = {BW_125: 125, BW_250: 250, BW_500: 500,
                  BW_62: 62, BW_41: 41, BW_31: 31}
        return (f"SX1262(freq={self._freq/1e6:.1f} MHz, SF={self._sf}, "
                f"BW={bw_map.get(self._bw,'?')} kHz, CR=4/{self._cr+4}, "
                f"TxPwr={self._tx_power} dBm)")

