"""
MAX2870 23.5 MHz - 6 GHz fractional/integer-N synthesizer driver
for MicroPython on the Raspberry Pi Pico (RP2040 / RP2350).

Wiring (defaults, all configurable):
    Pico GP2 (SPI0 SCK)  -> MAX2870 CLK
    Pico GP3 (SPI0 MOSI) -> MAX2870 DATA
    Pico GP5             -> MAX2870 LE
    Pico GP6             -> MAX2870 CE
    Pico GP7 (optional)  -> MAX2870 RF_EN
    Pico GP8 (optional)  <- MAX2870 LD (lock detect)

Example:
    from max2870 import MAX2870

    pll = MAX2870(spi_id=0, sck=2, mosi=3, le=5, ce=6, rf_en=7, ld=8)
    pll.set_reference(100_000_000)              # 100 MHz reference
    pll.set_frequency(915_000_000, optimize_r=True)
    pll.set_output(rfa=True, apwr=3)            # RFOUTA on, max power
    pll.begin()                                 # power-up sequence + enable outputs
    print(pll.actual_hz, pll.wait_lock())

    pll.set_frequency(1_234_567_890)            # retune on the fly
"""

from machine import Pin, SPI
import time


class MAX2870:
    # Device limits
    F_OUT_MIN = 23_500_000
    F_OUT_MAX = 6_000_000_000
    F_VCO_MIN = 3_000_000_000
    PFD_MAX_FRAC = 50_000_000
    PFD_MAX_INT = 105_000_000
    MOD_MAX = 4095

    def __init__(self, spi_id=0, sck=2, mosi=3, le=5, ce=6, rf_en=None,
                 ld=None, baudrate=1_000_000):
        """
        spi_id   : hardware SPI bus (0 or 1); sck/mosi must be valid for that bus
        sck,mosi : GPIO numbers for SPI clock and data (MAX2870 CLK / DATA)
        le       : GPIO for load-enable (latch)
        ce       : GPIO for chip enable, or None if tied high
        rf_en    : GPIO for the RF_EN pin, or None if tied high
        ld       : GPIO for the lock-detect output, or None
        """
        self._spi = SPI(spi_id, baudrate=baudrate, polarity=0, phase=0,
                        bits=8, firstbit=SPI.MSB, sck=Pin(sck), mosi=Pin(mosi))
        self._le = Pin(le, Pin.OUT, value=0)
        self._ce = Pin(ce, Pin.OUT, value=0) if ce is not None else None
        self._rf_en = Pin(rf_en, Pin.OUT, value=0) if rf_en is not None else None
        self._ld = Pin(ld, Pin.IN) if ld is not None else None

        # Reference settings
        self.ref_hz = 100_000_000
        self.r_div = 1
        self.ref_doubler = False
        self.ref_div2 = False

        # Loop / mode settings (adjust to match your loop filter)
        self.cp_current = 15        # charge-pump current code 0..15
        self.low_spur = False       # False = low-noise mode, True = low-spur mode
        self.mux = 0                # MUXOUT function, 4-bit code (0 = tri-state)

        # Output settings
        self.rfa_en = True
        self.apwr = 3               # 0..3
        self.rfb_en = False
        self.bpwr = 0               # 0..3
        self.rfb_fundamental = False  # False: RFOUTB = RFOUTA, True: RFOUTB = VCO

        self._target_hz = None
        self._optimize_r = False
        self._plan = None
        self._started = False
        self.actual_hz = None
        self.error_hz = None

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------
    @property
    def f_pfd(self):
        """Phase-detector frequency in Hz."""
        return self._pfd(self.r_div)

    def _ref_ratio(self, r):
        num = self.ref_hz * (2 if self.ref_doubler else 1)
        den = r * (2 if self.ref_div2 else 1)
        return num, den

    def _pfd(self, r):
        num, den = self._ref_ratio(r)
        return num / den

    def set_reference(self, freq_hz, r_div=1, doubler=False, div2=False):
        """Set reference input frequency and R-counter settings.
        f_pfd = f_ref * (1 + doubler) / (r_div * (1 + div2))"""
        if not 1 <= r_div <= 1023:
            raise ValueError("r_div must be 1..1023")
        self.ref_hz = int(round(freq_hz))
        self.r_div = int(r_div)
        self.ref_doubler = bool(doubler)
        self.ref_div2 = bool(div2)
        if self._target_hz is not None:
            self.set_frequency(self._target_hz, self._optimize_r)

    def set_frequency(self, freq_hz, optimize_r=False):
        """
        Calculate divider settings for the target RFOUTA frequency (Hz).
        If the device has been started, registers are written immediately.
        optimize_r=True searches R for an exact solution at the highest PFD.
        Returns the actual output frequency in Hz.
        """
        f_out = int(round(freq_hz))
        if not self.F_OUT_MIN <= f_out <= self.F_OUT_MAX:
            raise ValueError("Frequency must be 23.5 MHz .. 6 GHz")

        diva = 0
        while (f_out << diva) < self.F_VCO_MIN:
            diva += 1
        f_vco = f_out << diva

        r = self.r_div
        sol = None
        if optimize_r:
            for cand in range(1, 1024):
                if self._pfd(cand) < 1_000_000:
                    break
                sol = self._solve(f_vco, cand, exact_only=True)
                if sol:
                    r = cand
                    break
        if sol is None:
            sol = self._solve(f_vco, r)
        if sol is None:
            raise ValueError(
                "No valid N/FRAC/MOD for %d Hz with f_pfd=%.0f Hz (limits: "
                "frac-N pfd<=50 MHz, N 19..4091; int-N pfd<=105 MHz, N 16..65535)"
                % (f_out, self._pfd(r)))

        n, frac, mod, int_mode = sol
        num, den = self._ref_ratio(r)
        vco_actual = ((n * mod + frac) * num) / (mod * den)

        self.r_div = r
        self._target_hz = f_out
        self._optimize_r = optimize_r
        self._plan = {"n": n, "frac": frac, "mod": mod, "int_mode": int_mode,
                      "diva": diva}
        self.actual_hz = vco_actual / (1 << diva)
        self.error_hz = self.actual_hz - f_out

        if self._started:
            self._write_all()
        return self.actual_hz

    def set_output(self, rfa=True, apwr=3, rfb=False, bpwr=0,
                   rfb_fundamental=False):
        """Configure RFOUTA/RFOUTB enables and power (0..3)."""
        self.rfa_en = bool(rfa)
        self.apwr = apwr & 3
        self.rfb_en = bool(rfb)
        self.bpwr = bpwr & 3
        self.rfb_fundamental = bool(rfb_fundamental)
        self._apply_rf_en_pin()
        if self._started:
            self._write_reg(self._build(True)[4])

    def set_charge_pump(self, code):
        """Charge-pump current code 0..15 (choose per your loop filter)."""
        self.cp_current = code & 0xF
        if self._started:
            self._write_all()

    # ------------------------------------------------------------------
    # Divider maths
    # ------------------------------------------------------------------
    @staticmethod
    def _gcd(a, b):
        while b:
            a, b = b, a % b
        return a

    def _solve(self, f_vco, r, exact_only=False):
        """Return (n, frac, mod, int_mode) or None."""
        num, den = self._ref_ratio(r)
        pfd = num / den
        n, rem = divmod(f_vco * den, num)   # N_total = n + rem/num

        if rem == 0:
            if pfd <= self.PFD_MAX_INT and 16 <= n <= 65535:
                return (n, 0, 2, True)
            return None

        if pfd > self.PFD_MAX_FRAC or not 19 <= n <= 4091:
            return None

        g = self._gcd(rem, num)
        mod = num // g
        if mod <= self.MOD_MAX:
            return (n, rem // g, mod, False)
        if exact_only:
            return None

        # Best approximation with MOD <= 4095
        best = (n, 0, 2, rem)                       # round down
        if n + 1 <= 4091 and num - rem < rem:
            best = (n + 1, 0, 2, num - rem)         # round up
        for m in range(2, self.MOD_MAX + 1):
            fr = (rem * m + num // 2) // num
            if fr <= 0 or fr >= m:
                continue
            err = abs(fr * num - rem * m) / m
            if err < best[3]:
                best = (n, fr, m, err)
        return (best[0], best[1], best[2], False)

    # ------------------------------------------------------------------
    # Register construction / SPI
    # ------------------------------------------------------------------
    def _build(self, outputs=True):
        if self._plan is None:
            raise RuntimeError("Call set_frequency() first")
        p = self._plan
        pfd = self.f_pfd

        r0 = (int(p["int_mode"]) << 31) | (p["n"] << 15) | (p["frac"] << 3)

        cpl = 0 if p["int_mode"] else 1
        r1 = (cpl << 29) | (1 << 15) | (p["mod"] << 3) | 1

        lds = 1 if pfd > 32_000_000 else 0
        r2 = ((lds << 31)
              | ((3 if self.low_spur else 0) << 29)
              | ((self.mux & 7) << 26)
              | (int(self.ref_doubler) << 25)
              | (int(self.ref_div2) << 24)
              | (self.r_div << 14)
              | ((self.cp_current & 0xF) << 9)
              | (int(p["int_mode"]) << 8)        # LDF: 1 = int-N
              | (1 << 6)                         # PDP: positive polarity
              | 2)

        r3 = (1 << 3) | 3                        # CDIV = 1

        bs = int(round(pfd / 50_000))
        bs = max(1, min(1023, bs))
        rfa = self.rfa_en and outputs
        rfb = self.rfb_en and outputs
        r4 = ((0b011000 << 26)
              | (((bs >> 8) & 3) << 24)
              | (1 << 23)                        # FB = 1 (fundamental feedback)
              | (p["diva"] << 20)
              | ((bs & 0xFF) << 12)
              | (int(self.rfb_fundamental) << 9)
              | (int(rfb) << 8)
              | (self.bpwr << 6)
              | (int(rfa) << 5)
              | (self.apwr << 3)
              | 4)

        r5 = (1 << 24) | (1 << 22) | (((self.mux >> 3) & 1) << 18) | 5
        return [r0, r1, r2, r3, r4, r5]

    @property
    def registers(self):
        """Current register values [R0..R5] (for debugging)."""
        return self._build(True)

    def _write_reg(self, value):
        self._le.value(0)
        self._spi.write(value.to_bytes(4, "big"))
        self._le.value(1)
        self._le.value(0)

    def _write_all(self, outputs=True):
        regs = self._build(outputs)
        for i in (5, 4, 3, 2, 1, 0):
            self._write_reg(regs[i])

    def write_raw(self, regs):
        """Write six raw 32-bit words in order R5..R0 (regs given as [R0..R5])."""
        for i in (5, 4, 3, 2, 1, 0):
            self._write_reg(regs[i])

    # ------------------------------------------------------------------
    # Control
    # ------------------------------------------------------------------
    def _apply_rf_en_pin(self):
        if self._rf_en is not None:
            self._rf_en.value(1 if (self.rfa_en or self.rfb_en) else 0)

    def begin(self):
        """Power-up sequence: registers programmed twice, then outputs enabled."""
        if self._plan is None:
            raise RuntimeError("Call set_frequency() first")
        if self._rf_en is not None:
            self._rf_en.value(0)
        if self._ce is not None:
            self._ce.value(1)
        time.sleep_ms(20)
        self._write_all(outputs=False)
        time.sleep_ms(20)
        self._write_all(outputs=False)      # second write starts VCO selection
        time.sleep_ms(20)
        self._started = True
        self._write_reg(self._build(True)[4])   # enable outputs
        self._apply_rf_en_pin()

    def power_down(self):
        """Pull CE low (or disable outputs if CE is not wired)."""
        if self._rf_en is not None:
            self._rf_en.value(0)
        if self._ce is not None:
            self._ce.value(0)
        self._started = False

    def locked(self):
        """True if the LD pin reads high (requires ld pin)."""
        if self._ld is None:
            raise RuntimeError("No LD pin configured")
        return bool(self._ld.value())

    def wait_lock(self, timeout_ms=1000):
        """Poll LD until locked or timeout. Returns True if locked."""
        t0 = time.ticks_ms()
        while time.ticks_diff(time.ticks_ms(), t0) < timeout_ms:
            if self.locked():
                return True
            time.sleep_ms(1)
        return False

    def __repr__(self):
        return "<MAX2870 target=%s actual=%s pfd=%.0f>" % (
            self._target_hz, self.actual_hz, self.f_pfd)
