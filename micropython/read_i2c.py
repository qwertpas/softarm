import serial
import time
import sys

# --- CONFIGURATION ---
SERIAL_PORT = '/dev/tty.usbmodem101'  # Match the port from espgui.py
BAUD_RATE = 115200

# I2C PIN CONFIGURATION (Change these to match your wiring!)
# Common ESP32-S3 defaults might be SDA=8, SCL=9 or SDA=42, SCL=41 depending on the board.
PIN_SDA = 1  # Example: GPIO 1
PIN_SCL = 2  # Example: GPIO 2
I2C_FREQ = 100000

class ESPI2C:
    def __init__(self, port=SERIAL_PORT, baud=BAUD_RATE):
        self.ser = serial.Serial(port, baud, timeout=1)
        self.connect_and_init()

    def connect_and_init(self):
        print(f"Connecting to {self.ser.port}...")
        # 1. Stop any running program (Ctrl+C)
        self.ser.write(b'\x03')
        time.sleep(0.1)
        
        # 2. Enter Raw REPL Mode (Ctrl+A)
        self.ser.write(b'\x01')
        time.sleep(0.1)
        self.ser.read_all() # Clear buffer

        # 3. Define the I2C setup code
        # We use SoftI2C for maximum compatibility with any pins
        init_code = f"""
import machine
import time
try:
    i2c = machine.SoftI2C(sda=machine.Pin({PIN_SDA}), scl=machine.Pin({PIN_SCL}), freq={I2C_FREQ})
    status = "OK"
except Exception as e:
    status = str(e)
"""
        self.exec_raw(init_code)
        print("I2C initialized on ESP32.")

    def exec_raw(self, code):
        """Execute code in Raw REPL and return output"""
        # Ctrl+A to ensure we are in raw mode
        self.ser.write(b'\x01')
        time.sleep(0.05)
        self.ser.read_all() # Clear "OK"

        # Send code
        self.ser.write(code.encode('utf-8') + b'\x04') # Ctrl+D to execute
        
        # Wait for execution to finish (look for \x04)
        ret = b""
        while True:
            if self.ser.in_waiting > 0:
                chunk = self.ser.read(self.ser.in_waiting)
                ret += chunk
                if ret.endswith(b'\x04>'): # End of raw repl output
                    break
            time.sleep(0.01)
        
        # Parse response
        # Format is: OK<output>\x04<error>\x04>
        # We want <output>. If <error> exists, raise it.
        
        parts = ret.split(b'\x04')
        if len(parts) >= 2:
            output = parts[0].decode('utf-8', errors='replace').strip()
            if output.startswith('OK'):
                output = output[2:] # Remove OK
            
            error = parts[1].decode('utf-8', errors='replace').strip()
            
            if error:
                raise RuntimeError(f"ESP32 Error: {error}")
            return output
        return ""

    def scan(self):
        """Run i2c.scan() on the ESP32 and return list of addresses"""
        print("Scanning I2C bus...")
        code = "print(i2c.scan())"
        try:
            result = self.exec_raw(code)
            # Result should be a string like "[8, 32, ...]"
            # Evaluate it safely
            if result:
                return eval(result)
            return []
        except Exception as e:
            print(f"Scan failed: {e}")
            return []

    def read_from_mem(self, address, register, num_bytes=1):
        """Read bytes from a specific register on a device"""
        # Using readfrom_mem(addr, memaddr, nbytes)
        code = f"print(i2c.readfrom_mem({address}, {register}, {num_bytes}))"
        try:
            result = self.exec_raw(code)
            # Result is a bytes object string representation like "b'\\x00...'"
            # We can parse this or just return the raw string for now
            return result
        except Exception as e:
            print(f"Read failed: {e}")
            return None
            
    def write_to_mem(self, address, register, data_byte):
        """Write a byte to a register"""
        code = f"i2c.writeto_mem({address}, {register}, bytes([{data_byte}]))"
        try:
            self.exec_raw(code)
            print(f"Wrote {data_byte} to reg {register} at addr {address}")
        except Exception as e:
            print(f"Write failed: {e}")

    def close(self):
        self.ser.close()

if __name__ == "__main__":
    esp = None
    try:
        esp = ESPI2C()
        
        # 1. Scan for devices
        devices = esp.scan()
        print(f"Found devices at addresses: {devices} (Decimal)")
        print(f"Found devices at addresses: {[hex(x) for x in devices]} (Hex)")

        # 2. Example Read (Uncomment to use)
        # if devices:
        #     target = devices[0]
        #     print(f"Reading from first device {hex(target)}...")
        #     # Try reading register 0x00 (often ID or Status)
        #     data = esp.read_from_mem(target, 0x00, 1)
        #     print(f"Data at 0x00: {data}")

    except Exception as e:
        print(f"Error: {e}")
    finally:
        if esp:
            esp.close()

