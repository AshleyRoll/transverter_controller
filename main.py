import sys
import machine
import micropython
import uasyncio as asyncio

from input_helpers import input_mhz
from pll import Pll
from pixel import Pixel, Colour
from machine import Pin

pixel = Pixel(scale=0.2)

# pin to drive out TX switching TX_Key_H
tx_enable = Pin(15, Pin.OUT, value=0)
ptt_in = Pin(14, machine.Pin.IN, machine.Pin.PULL_UP)
radio_ptt_out = Pin(26, Pin.OUT, value=0)

def pll_updated(enabled, config):
    if enabled:
        pixel.colour(Colour.GREEN)
    else:
        # ensure we are not in TX mode
        tx_enable.value(False)
        pixel.colour(Colour.BLACK)

pll = Pll(pll_updated)


# -------------------------------------------------------------
# PTT outputs
# -------------------------------------------------------------
is_tx_mode = False

def tx_mode():
    global tx_enable, pixel, is_tx_mode
    pixel.colour(Colour.RED)
    tx_enable.value(1)
    is_tx_mode = True
    print_live_status()

def rx_mode():
    global tx_enable, pixel, pll, is_tx_mode

    if pll.enabled:
        pixel.colour(Colour.GREEN)
    else:
        pixel.colour(Colour.BLACK)

    tx_enable.value(0)
    is_tx_mode = False
    print_live_status()

def radio_tx():
    global radio_ptt_out
    radio_ptt_out.value(1)

def radio_rx():
    global radio_ptt_out
    radio_ptt_out.value(1)


# -------------------------------------------------------------
# HARDWARE INTERRUPT HANDLER (ISR)
# -------------------------------------------------------------

# Global flag for thread-safe async interrupt handling
ptt_pin_flag = asyncio.ThreadSafeFlag()

def ptt_pin_isr(pin):
    ptt_pin_flag.set()

# -------------------------------------------------------------
# ASYNC and INTERRUPT WORKER TASKS
# -------------------------------------------------------------
async def pin_changed_worker(pin):
    global pll
    while True:
        await ptt_pin_flag.wait() # wait for the isr to set the flag
        await asyncio.sleep_ms(20) # simple debounce
        ptt_state = pin.value()
        
        # if the PLL is enabled, we update the tx driver
        # and the led colour
        if not pll.enabled:
            continue;

        if ptt_state == 0: # 0 = PTT pressed
            # enable TX - first our change over relay, then the radio PTT
            tx_mode()
            await asyncio.sleep_ms(100)
            radio_tx()
        else:
            # disable TX - drop out the radio, then our change over relay
            radio_rx()
            await asyncio.sleep_ms(100)
            rx_mode()

async def dummy_worker():
    while True:
        await asyncio.sleep_ms(500)

# -------------------------------------------------------------
# MENU ACTIONS
# -------------------------------------------------------------
def toggle_pll_enable():
    global pll
    pll.toggle_enable()
    print_pll_status()

    return False # no repaint needed

async def change_rf_frequency():
    global pll
    freq = await input_mhz(f"RF Output ({pll.config.rf_min}-{pll.config.rf_max}MHz): ", val=pll.config.rf_f)
    if freq < pll.config.rf_min or freq > pll.config.rf_max:
        print("out of range")
    else:
        pll.change_rf_frequency(freq)

    return True # repaint menu

async def change_if_frequency():
    global pll
    freq = await input_mhz(f"IF Input ({pll.config.if_min}-{pll.config.if_max}MHz): ", val=pll.config.if_f)
    if freq < pll.config.if_min or freq > pll.config.if_max:
        print("out of range")
    else:
        pll.change_if_frequency(freq)

    return True # repaint menu

def reset_config():
    global pll
    print("\r\nLoading configuration defaults...")
    pll.reset_config()

    return True # repaint menu

def make_safe():
    radio_rx()
    rx_mode()


# -------------------------------------------------------------
# CONFIG & DISPLAY
# -------------------------------------------------------------
menu_items = {
    b"e": ("Toggle PLL Enable", toggle_pll_enable, False),
    b"r": ("Change RF Frequency", change_rf_frequency, True),
    b"i": ("Change IF Frequency", change_if_frequency, True),
    b"c": ("Reset Config", reset_config, False),
}

def print_menu():
    global pll, current_mode
    # \x1b[H moves cursor to row 1, col 1. \x1b[J clears everything below it.
    print("\x1b[H\x1b[J", end="")
    print("=" * 40)

    print(f" STATUS:     ")
    print(f" PLL Enabled:       ")
    print(f" RF Freq: {pll.config.rf_f} MHz")
    print(f" IF Freq: {pll.config.if_f} MHz")
    print(f" PLL Freq: {pll.pll_f} MHz")
    print("=" * 40)
    for key, (description, _, _) in sorted(menu_items.items()):
        print(f" [{key.decode()}] {description}")
    print(" [q] Exit to MicroPython REPL")
    print("=" * 40)
    print_live_status()
    print_pll_status()

def print_live_status():
    global is_tx_mode
    # \x1b7      - Captures the user's exact current cursor position in terminal memory
    # \x1b[2;10H - Jumps directly to Row 2, Column 10 to write the live flag
    # \x1b[K     - Clears the rest of that specific line segment (removes old trailing text)
    # \x1b8      - Instantly drops the user back to exactly where they were typing
    mode_color = "\x1b[1;31m" if is_tx_mode else "\x1b[1;32m"
    mode_name = "TX" if is_tx_mode else "RX"
    print(f"\x1b7\x1b[2;10H{mode_color}[{mode_name}]\x1b[0m\x1b[K\x1b8", end="")

def print_pll_status():
    global pll
    mode_color = "\x1b[1;32m" if pll.enabled else "\x1b[1;31m"
    mode_name = "On" if pll.enabled else "Off"
    print(f"\x1b7\x1b[3;15H{mode_color}[{mode_name}]\x1b[0m\x1b[K\x1b8", end="")
# -------------------------------------------------------------
# MENU SYSTEM TASK
# -------------------------------------------------------------
class MenuExitException(Exception):
    pass


async def menu_loop():
    reader = asyncio.StreamReader(sys.stdin.buffer)
    print_menu()
    
    while True:
        char = await reader.read(1)
        char = char.lower()
        
        if char == b'q':
            print(f"\r\nExiting menu system...")
            make_safe()
            raise MenuExitException
        elif char in menu_items:
            action = menu_items[char]
            action_func = action[1]
            is_async = action[2]

            if is_async:
                repaint = await action_func()
            else:
                repaint = action_func()

            if repaint:
                print_menu()
        elif char in [b'\r', b'\n']:
            continue
        else:
            # Removed the try/except block that attempted a UTF-8 decode.
            # Prints the raw string representation of the byte string directly.
            print(f"\r\nInvalid option: '{str(char)}'. Try again.")
            print_menu()

# -------------------------------------------------------------
# CENTRALIZED SUPERVISOR
# -------------------------------------------------------------
async def run_application(ptt_interrupt_pin):
    background_tasks = [
        asyncio.create_task(pin_changed_worker(ptt_interrupt_pin)),
        asyncio.create_task(dummy_worker()), # Just drop new tasks here!
    ]
    
    try:
        await menu_loop()
    except MenuExitException:
        # Catch our intentional exit command from the menu loop
        pass
    finally:
        # Loop through and cancel every registered background worker automatically
        for task in background_tasks:
            task.cancel()
        
        # Let the event loop run for a microsecond to process all cancellations cleanly
        await asyncio.sleep_ms(0)

# -------------------------------------------------------------
# MAIN ASYNC INITIALISATION
# -------------------------------------------------------------
async def main():
    global ptt_in

    ptt_in.irq(trigger=machine.Pin.IRQ_RISING | machine.Pin.IRQ_FALLING, handler=ptt_pin_isr)
    
    try:
        await run_application(ptt_in) 
    finally:
        ptt_in.irq(handler=None)
        # return to RX mode
        make_safe()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\r\nInterrupted by user.")

