
from max2870 import MAX2870
from config import Config

class Pll:
    def __init__(self, on_update=None):
        self.config = Config.load_from_file()
        self.pll_f = 0.0
        self.enabled = False
        self.on_update = on_update
        # initial setup and enable PLL
        self.pll = MAX2870(spi_id=0, sck=6, mosi=7, le=5, ce=3)
        self.pll.set_reference(self.config.pll_ref_f * 1_000_000)
        self._update_pll(True)

    def _calculate_pll_frequency(self):
        return (self.config.rf_f - self.config.if_f) / 2.0

    def _update_pll(self, enable):
        self.pll_f = self._calculate_pll_frequency()
        self.pll.set_frequency(self.pll_f * 1_000_000, optimize_r=True)
        if enable:
            self.pll.set_output(rfa=True, apwr=3)
            self.pll.begin()
            self.enabled = True
            if self.on_update:
                self.on_update(self.enabled, self.config) 
        else:
            self.pll.set_output(rfa=False, apwr=0)
            self.pll.power_down()
            self.enabled = False
            if self.on_update:
                self.on_update(self.enabled, self.config) 

    def enable(self, enable=True):
        self._update_pll(enable)

    def toggle_enable(self):
        self.enable(not self.enabled)

    def change_rf_frequency(self, freq):
        if freq >= self.config.rf_min and freq <= self.config.rf_max:
            self.config.rf_f = freq
            self._update_pll(self.enabled)
            self.config.save_to_file()
        
    def change_if_frequency(self, freq):
        if freq >= self.config.if_min and freq <= self.config.if_max:
            self.config.if_f = freq
            self._update_pll(self.enabled)
            self.config.save_to_file()
           
    def reset_config(self):
        self.config = Config()
        self.config.save_to_file()
        self._update_pll(self.enabled)

