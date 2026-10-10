from machine import Pin
from neopixel import NeoPixel

class Colour:
    RED = (255, 0, 0)
    GREEN = (0, 255, 0)
    BLUE = (0, 0, 255)
    CYAN = (0, 255, 255)
    MAGENTA = (255, 0, 255)
    YELLOW = (255, 255, 0)
    BLACK = (0, 0, 0)
    WHITE = (255, 255, 255)

class Pixel:
    def __init__(self, pin=16, col = Colour.BLACK, scale=1.0):
        self.scale = scale
        self.pin = Pin(pin, Pin.OUT)
        self.np = NeoPixel(self.pin, 1)
        self.colour(col)

    def colour(self, col):
        scaled_col = tuple(int(self.scale * x) for x in col)
        self.np[0] = scaled_col
        self.np.write()

    

