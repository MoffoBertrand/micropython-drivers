# ld2420.py - MicroPython Driver for HLK-LD2420 24 GHz mmWave Radar
#
# Supports BOTH sensor output modes (auto-detected):
#   ASCII mode (fw v1.6.x simple mode):  "ON\r\n" / "OFF\r\n" / "Range XX\r\n"
#   Binary mode (fw energy mode):         F4F3F2F1...F8F7F6F5
#
# Command mode always uses binary protocol (0x08/0x07).
#
# Target: Waveshare ESP32-S3-Pico with MicroPython
# University of Buea - College of Technology
# Prof. MOFFO LONLA Bertrand - May 2026

from machine import UART
import time
import struct

# Protocol constants
DATA_HEADER = b'\xF4\xF3\xF2\xF1'
DATA_FOOTER = b'\xF8\xF7\xF6\xF5'
CMD_HEADER  = b'\xFD\xFC\xFB\xFA'
CMD_FOOTER  = b'\x04\x03\x02\x01'

CMD_OPEN_CMD    = 0x00FF
CMD_CLOSE_CMD   = 0x00FE
CMD_READ_VER    = 0x0000
CMD_READ_PARAMS = 0x0008
CMD_SET_PARAMS  = 0x0007
CMD_RESTART     = 0x0068
CMD_RESP_MASK   = 0x0100

PARAM_MIN_GATE = 0x0000
PARAM_MAX_GATE = 0x0001
PARAM_TIMEOUT  = 0x0004
MAX_GATES      = 16
GATE_CM        = 70


class LD2420:
    """Driver for HLK-LD2420.  Auto-detects ASCII vs binary output."""

    def __init__(self, uart_id=1, tx_pin=11, rx_pin=12,
                 baudrate=115200):
        self.uart = UART(uart_id, baudrate=baudrate,
                         tx=tx_pin, rx=rx_pin,
                         bits=8, parity=None, stop=1)
        self._in_cmd_mode = False

        # Public data
        self.presence    = False
        self.distance    = 0        # cm (gate * 70 in ASCII mode)
        self.gate        = 0        # raw gate number (ASCII mode)
        self.gate_energy = [0] * MAX_GATES
        self.valid       = False
        self.timestamp   = 0
        self.mode        = None     # 'ascii' or 'binary', auto-detected

        # Buffers
        self._line_buf = b''
        self._bin_buf  = bytearray(256)
        self._bin_idx  = 0

        # Filtering & throttling
        self._min_dist = 0
        self._max_dist = 1200
        self._update_interval = 0
        self._last_update = 0

        # Callbacks
        self._on_detection    = None
        self._on_state_change = None
        self._on_data_update  = None
        self._last_state      = False

    # --- Callbacks ---

    def on_detection(self, cb):
        """cb(distance_cm) called when target is present."""
        self._on_detection = cb

    def on_state_change(self, cb):
        """cb(old_present: bool, new_present: bool) on transitions."""
        self._on_state_change = cb

    def on_data_update(self, cb):
        """cb(ld2420_instance) called on every valid reading."""
        self._on_data_update = cb

    def set_distance_range(self, min_cm, max_cm):
        self._min_dist = min_cm
        self._max_dist = max_cm

    def set_update_interval(self, ms):
        self._update_interval = ms

    # --- Main loop entry ---

    def update(self):
        """Read and parse UART data.  Call frequently."""
        if self._update_interval > 0:
            now = time.ticks_ms()
            if time.ticks_diff(now, self._last_update) < self._update_interval:
                return
            self._last_update = now

        while self.uart.any():
            b = self.uart.read(1)
            if b is None:
                break
            bv = b[0]

            # Auto-detect on first byte
            if self.mode is None:
                self.mode = 'binary' if bv == 0xF4 else 'ascii'

            if self.mode == 'ascii':
                self._ascii_byte(bv)
            else:
                self._binary_byte(bv)

    # ============================================================
    #     ASCII MODE: "ON\r\n" / "OFF\r\n" / "Range XX\r\n"
    # ============================================================

    def _ascii_byte(self, bv):
        if bv == 0x0A:  # \n -> end of line
            line = self._line_buf.decode('ascii', 'ignore').strip()
            self._line_buf = b''
            if line:
                self._parse_line(line)
        elif bv != 0x0D:  # skip \r
            self._line_buf += bytes([bv])
            if len(self._line_buf) > 64:
                self._line_buf = b''

    def _parse_line(self, line):
        if line == 'ON':
            self.presence = True
            self.valid = True
            self.timestamp = time.ticks_ms()
            self._invoke_callbacks()
        elif line == 'OFF':
            self.presence = False
            self.distance = 0
            self.gate = 0
            self.valid = True
            self.timestamp = time.ticks_ms()
            self._invoke_callbacks()
        elif line.startswith('Range'):
            parts = line.split()
            if len(parts) >= 2:
                try:
                    self.distance = int(parts[1])  # already in cm
                except ValueError:
                    pass

    # ============================================================
    #     BINARY MODE: F4F3F2F1 ... F8F7F6F5
    # ============================================================

    def _binary_byte(self, bv):
        self._bin_buf[self._bin_idx] = bv
        self._bin_idx += 1
        if self._bin_idx >= len(self._bin_buf):
            self._bin_idx = 0
            return
        if self._bin_idx >= 4:
            if bytes(self._bin_buf[self._bin_idx-4:self._bin_idx]) == DATA_FOOTER:
                self._parse_binary()
                self._bin_idx = 0

    def _parse_binary(self):
        buf = bytes(self._bin_buf[:self._bin_idx])
        hp = buf.find(DATA_HEADER)
        if hp < 0 or hp + 9 > self._bin_idx:
            return
        dlen = struct.unpack_from('<H', buf, hp + 4)[0]
        payload = buf[hp+6: hp+6+dlen]
        if len(payload) < 3:
            return
        self.presence = (payload[0] != 0)
        self.distance = struct.unpack_from('<H', payload, 1)[0]
        if len(payload) >= 35:
            for g in range(MAX_GATES):
                off = 3 + g * 2
                if off + 1 < len(payload):
                    self.gate_energy[g] = struct.unpack_from('<H', payload, off)[0]
        self.valid = True
        self.timestamp = time.ticks_ms()
        self._invoke_callbacks()

    # ============================================================
    #     CALLBACKS
    # ============================================================

    def _invoke_callbacks(self):
        d = self.distance
        if d < self._min_dist or d > self._max_dist:
            return
        if self.presence != self._last_state:
            if self._on_state_change:
                self._on_state_change(self._last_state, self.presence)
            self._last_state = self.presence
        if self._on_detection and self.presence:
            self._on_detection(d)
        if self._on_data_update:
            self._on_data_update(self)

    def is_fresh(self, max_age_ms=2000):
        if not self.valid:
            return False
        return time.ticks_diff(time.ticks_ms(), self.timestamp) < max_age_ms

    # ============================================================
    #     COMMAND MODE (binary protocol, always works)
    # ============================================================

    def _send_cmd(self, cmd_id, payload=b''):
        dlen = 2 + len(payload)
        frame = (CMD_HEADER + struct.pack('<H', dlen) +
                 struct.pack('<H', cmd_id) + payload + CMD_FOOTER)
        self.uart.write(frame)
        time.sleep_ms(50)

    def _read_response(self, expected_cmd, timeout_ms=1000):
        rbuf = bytearray(256)
        idx = 0
        start = time.ticks_ms()
        while time.ticks_diff(time.ticks_ms(), start) < timeout_ms:
            if self.uart.any():
                b = self.uart.read(1)
                if b:
                    rbuf[idx] = b[0]; idx += 1
                    if idx >= len(rbuf): return None
                    if idx >= 4 and bytes(rbuf[idx-4:idx]) == CMD_FOOTER:
                        data = bytes(rbuf[:idx])
                        hp = data.find(CMD_HEADER)
                        if hp >= 0 and hp + 8 <= idx:
                            dl = struct.unpack_from('<H', data, hp+4)[0]
                            rc = struct.unpack_from('<H', data, hp+6)[0]
                            if rc == expected_cmd and dl > 2:
                                return data[hp+8: hp+6+dl]
                        return None
            else:
                time.sleep_ms(5)
        return None

    def open_command_mode(self):
        while self.uart.any(): self.uart.read(64)
        time.sleep_ms(100)
        self._send_cmd(CMD_OPEN_CMD, struct.pack('<H', 1))
        resp = self._read_response(CMD_OPEN_CMD | CMD_RESP_MASK)
        if resp and len(resp) >= 2:
            self._in_cmd_mode = (struct.unpack_from('<H', resp, 0)[0] == 0)
            return self._in_cmd_mode
        return False

    def close_command_mode(self):
        self._send_cmd(CMD_CLOSE_CMD)
        self._read_response(CMD_CLOSE_CMD | CMD_RESP_MASK)
        self._in_cmd_mode = False
        self.mode = None  # re-detect after exit

    @property
    def in_command_mode(self):
        return self._in_cmd_mode

    def read_firmware_version(self):
        if not self._in_cmd_mode and not self.open_command_mode():
            return ''
        self._send_cmd(CMD_READ_VER)
        resp = self._read_response(CMD_READ_VER | CMD_RESP_MASK)
        if resp and len(resp) >= 4:
            if struct.unpack_from('<H', resp, 0)[0] == 0:
                sl = struct.unpack_from('<H', resp, 2)[0]
                if sl > 0 and 4 + sl <= len(resp):
                    return resp[4:4+sl].decode('ascii', 'ignore')
        return ''

    def _read_param(self, pname):
        self._send_cmd(CMD_READ_PARAMS, struct.pack('<H', pname))
        resp = self._read_response(CMD_READ_PARAMS | CMD_RESP_MASK)
        if resp and len(resp) >= 6:
            if struct.unpack_from('<H', resp, 0)[0] == 0:
                return struct.unpack_from('<I', resp, 2)[0]
        return None

    def _set_param(self, pname, value):
        self._send_cmd(CMD_SET_PARAMS, struct.pack('<HI', pname, value))
        resp = self._read_response(CMD_SET_PARAMS | CMD_RESP_MASK)
        return resp and len(resp) >= 2 and struct.unpack_from('<H', resp, 0)[0] == 0

    def set_gate_range(self, min_g, max_g):
        return self._set_param(PARAM_MIN_GATE, min_g) and self._set_param(PARAM_MAX_GATE, max_g)

    def set_timeout(self, s):
        return self._set_param(PARAM_TIMEOUT, s)

    def set_gate_threshold(self, gate, trig, hold):
        if gate >= MAX_GATES: return False
        return self._set_param(0x0010+gate, trig) and self._set_param(0x0020+gate, hold)

    def read_config(self):
        if not self._in_cmd_mode: return None
        cfg = {'min_gate':0, 'max_gate':0, 'timeout':0,
               'trigger_thresh':[0]*MAX_GATES, 'hold_thresh':[0]*MAX_GATES}
        for key, pn in [('min_gate',PARAM_MIN_GATE), ('max_gate',PARAM_MAX_GATE), ('timeout',PARAM_TIMEOUT)]:
            v = self._read_param(pn)
            if v is not None: cfg[key] = v
        for g in range(MAX_GATES):
            v = self._read_param(0x0010+g)
            if v is not None: cfg['trigger_thresh'][g] = v
            v = self._read_param(0x0020+g)
            if v is not None: cfg['hold_thresh'][g] = v
        return cfg

    def write_config(self, cfg):
        if not self._in_cmd_mode: return False
        ok = True
        ok = ok and self._set_param(PARAM_MIN_GATE, cfg['min_gate'])
        ok = ok and self._set_param(PARAM_MAX_GATE, cfg['max_gate'])
        ok = ok and self._set_param(PARAM_TIMEOUT, cfg['timeout'])
        for g in range(MAX_GATES):
            ok = ok and self._set_param(0x0010+g, cfg['trigger_thresh'][g])
            ok = ok and self._set_param(0x0020+g, cfg['hold_thresh'][g])
        return ok

    def restart(self):
        if not self._in_cmd_mode: self.open_command_mode()
        self._send_cmd(CMD_RESTART)
        self._in_cmd_mode = False
        self.mode = None
        time.sleep_ms(500)
