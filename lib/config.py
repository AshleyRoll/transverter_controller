import json

class Config:
    """All Frequencies are in MHz"""
    __slots__ = ("rf_min", "rf_max", "if_min", "if_max", "rf_f", "if_f", "pll_ref_f")

    def __init__(self, rf_f=10_368.1, if_f=146.5, pll_ref_f=10.0, rf_min=9_000, rf_max=12_000, if_min=100, if_max=500):
        self.rf_min = rf_min
        self.rf_max = rf_max
        self.if_min = if_min
        self.if_max = if_max

        self.rf_f = rf_f
        self.if_f = if_f
        self.pll_ref_f = pll_ref_f

    def save_to_file(self, filename="config.json"):
        try:
            with open(filename, "w") as f:
                # self.__dict__ extracts the instance variables as a dictionary
                json.dump(self.__dict__, f)
            print("Configuration saved successfully!")
            return True
        except Exception as e:
            print("Failed to save:", e)
            return False

    @classmethod
    def load_from_file(cls, filename="config.json"):
        try:
            with open(filename, "r") as f:
                data = json.load(f)
            
            # Create a new instance using the unpacked dictionary data
            return cls(**data)
        except Exception as e:
            print("Failed to load file, creating default config:", e)
            return cls()  # Return a default instance if file doesn't exist
