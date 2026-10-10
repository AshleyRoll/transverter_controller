import sys
import select
import machine
import micropython

from input_helpers import input_mhz
from pll import Pll
from pixel import Pixel, Colour

pixel = Pixel(scale=0.2)

def pll_updated(enabled, config):
    if enabled:
        pixel.colour(Colour.GREEN)
    else:
        pixel.colour(Colour.BLACK)

pll = Pll(pll_updated)

# -------------------------------------------------------------
# MENU ACTIONS
# -------------------------------------------------------------

def toggle_pll_enable():
    global pll
    pll.toggle_enable()

def change_rf_frequency():
    global pll
    freq = input_mhz(f"RF Output ({pll.config.rf_min}-{pll.config.rf_max}MHz): ", val=pll.config.rf_f)
    if freq < pll.config.rf_min or freq > pll.config.rf_max:
        print("out of range")
    else:
        pll.change_rf_frequency(freq)

def change_if_frequency():
    global pll
    freq = input_mhz(f"IF Input ({pll.config.if_min}-{pll.config.if_max}MHz): ", val=pll.config.if_f)
    if freq < pll.config.if_min or freq > pll.config.if_max:
        print("out of range")
    else:
        pll.change_if_frequency(freq)

def reset_config():
    global pll
    print("\r\nLoading configuration defaults...")
    pll.reset_config()


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
    global pll
    # \r\n ensures formatting is completely pristine in minicom
    print("\r\n\r\n" + "="*30)
    print(f" PLL: { pll.pll_f }MHz Enabled: { pll.enabled }")
    print(f" RF: { pll.config.rf_f }MHz IF: { pll.config.if_f }MHz")
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

