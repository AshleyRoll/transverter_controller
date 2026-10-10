import sys
import select
import machine
import micropython

from input_helpers import input_mhz
from max2870 import MAX2870
from config import Config
from pixel import Pixel, Colour

# Disable Ctrl+C from breaking into REPL while our loop handles it
#micropython.kbd_intr(-1)

     
def calculate_pll_frequency():
    global config
    return (config.rf_f-config.if_f) / 2.0

config = Config.load_from_file()
pll_f = 0.0
pll_enabled = False

pixel = Pixel(scale=0.2)

def update_pll(enable):
    global pll_f
    pll_f = calculate_pll_frequency()
    pll.set_frequency(pll_f * 1_000_000, optimize_r=True)
    if enable:
        pll.set_output(rfa=True, apwr=3)
        pll.begin()
        pixel.colour(Colour.GREEN)
    else:
        pll.set_output(rfa=False, apwr=0)
        pll.power_down()
        pixel.colour(Colour.BLACK)


# initial setup and enable PLL
pll = MAX2870(spi_id=0, sck=6, mosi=7, le=5, ce=3)
pll.set_reference(config.pll_ref_f * 1_000_000)
update_pll(True)
pll_enabled = True


# -------------------------------------------------------------
# MENU ACTIONS
# -------------------------------------------------------------

def toggle_pll_enable():
    global pll_enabled
    pll_enabled = not pll_enabled
    update_pll(pll_enabled) 

def change_rf_frequency():
    global config
    freq = input_mhz(f"RF Output ({config.rf_min}-{config.rf_max}MHz): ", val=config.rf_f)
    if freq < config.rf_min or freq > config.rf_max:
        print("out of range")
    else:
        config.rf_f = freq
        update_pll(pll_enabled)
        config.save_to_file()

def change_if_frequency():
    global config
    freq = input_mhz(f"IF Input ({config.if_min}-{config.if_max}MHz): ", val=config.if_f)
    if freq < config.if_min or freq > config.if_max:
        print("out of range")
    else:
        config.if_f = freq
        update_pll(pll_enabled)
        config.save_to_file()

def reset_config():
    global config
    print("\r\nLoading configuration defaults...")
    config = Config()
    config.save_to_file()
    update_pll(pll_enabled)


# -------------------------------------------------------------
# CONFIG & DISPLAY
# -------------------------------------------------------------
menu_items = {
    b"e": ("Toggle PLL Enable", toggle_pll_enable),
    b"r": ("Change RF Frequency", change_rf_frequency),
    b"i": ("Change IF Frequency", change_if_frequency),
    b"c": ("Reset Config", reset_config),

}

def print_menu():
    global config
    # \r\n ensures formatting is completely pristine in minicom
    print("\r\n\r\n" + "="*30)
    print(f" PLL: { pll_f }MHz Enabled: { pll_enabled }")
    print(f" RF: { config.rf_f }MHz IF: { config.if_f }MHz")
    print("="*30)
    for key, (description, _) in sorted(menu_items.items()):
        print(f" [{key.decode()}] {description}")
    print("\r\n [q] Exit to MicroPython REPL")
    print("="*30)
    print("Enter choice: ", end="")

# -------------------------------------------------------------
# MAIN LOOP
# -------------------------------------------------------------
def main():
    poll_object = select.poll()
    # Explicitly register the raw buffer rather than the text wrapper
    poll_object.register(sys.stdin.buffer, select.POLLIN)

    print_menu()
    
    try:
        while True:
            # Poll with a snappy 20ms timeout
            if poll_object.poll(20):
                # Read exactly 1 raw byte straight from the USB buffer
                char = sys.stdin.buffer.read(1).lower()
                
                if char == b'q':
                    print(f"\r\nExiting menu system...")
                    break
                elif char in menu_items:
                    action_func = menu_items[char][1]
                    action_func()
                    print_menu()
                elif char in [b'\r', b'\n']:
                    # Ignore standalone carriage returns or line feeds sent by minicom
                    continue
                else:
                    # Catch and report any stray characters
                    try:
                        char_str = char.decode('utf-8')
                    except:
                        char_str = str(char)
                    print(f"\r\nInvalid option: '{char_str}'. Try again.")
                    print_menu()
    finally:
        # CRITICAL: Re-enable Ctrl+C completely so the REPL responds normally
        micropython.kbd_intr(3)

if __name__ == '__main__':
    main()

