import sys
import select

def input_mhz(prompt="Enter frequency in MHz: ", val=None):
    print(f"\r\n{prompt}", end="")
    input_bytes = bytearray()

    # Pre-load the default value if provided
    if val is not None:
        # Convert float/int to a string format, then encode to bytes manually via an array
        default_str = f"{val:.2f}" if isinstance(val, float) else str(val)
        input_bytes.extend(default_str.encode('ascii'))
        # Print it so the user can see it on the terminal screen
        sys.stdout.write(default_str)
    
    poll_object = select.poll()
    poll_object.register(sys.stdin.buffer, select.POLLIN)
    
    while True:
        if poll_object.poll(20):
            char = sys.stdin.buffer.read(1)
            if not char:
                continue
                
            byte_val = char[0]  # Extract the single integer byte value
            
            # Handle Enter key (\r or \n)
            if byte_val == 13 or byte_val == 10:  # 13 = \r, 10 = \n
                if not input_bytes:
                    print("\r\nError: Input cannot be empty.")
                    print(prompt, end="")
                    continue
                try:
                    # float() accepts a bytearray directly in MicroPython
                    value = float(input_bytes)
                    print("\r")  # Clean carriage return line finish
                    return value
                except ValueError:
                    print("\r\nError: Invalid decimal number. Try again.")
                    # Re-initialize the bytearray using standard constructor syntax
                    input_bytes = bytearray()
                    print(prompt, end="")
                    continue
                    
            # Handle Backspace / Delete keys (127 = Del/Backspace, 8 = Backspace)
            elif byte_val == 127 or byte_val == 8:
                if len(input_bytes) > 0:
                    # Correct MicroPython way to remove the last item from a bytearray
                    input_bytes = input_bytes[:-1]
                    # Backspace, overwrite with space, backspace again to move cursor back
                    sys.stdout.write('\b \b')
                    
            # Allow digits (48-57), period (46), and minus sign (45)
            elif (48 <= byte_val <= 57) or byte_val == 46 or byte_val == 45:
                input_bytes.append(byte_val)
                # Echo the raw character byte straight back to minicom
                sys.stdout.buffer.write(char)

