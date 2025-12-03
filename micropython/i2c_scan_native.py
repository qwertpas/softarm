# This is a standard MicroPython script.
# It runs on the ESP32, but you save it on your laptop.
import machine
import time

# Config
SDA_PIN = 1
SCL_PIN = 2
FREQ = 100000

def scan_i2c():
    print(f"Initializing I2C on SDA={SDA_PIN}, SCL={SCL_PIN}...")
    
    try:
        # Initialize I2C
        i2c = machine.SoftI2C(
            sda=machine.Pin(SDA_PIN), 
            scl=machine.Pin(SCL_PIN), 
            freq=FREQ
        )
        
        # Scan
        print("Scanning...")
        devices = i2c.scan()
        
        if devices:
            print(f"Found {len(devices)} devices:")
            for device in devices:
                print(f"  Decimal: {device} | Hex: {hex(device)}")
        else:
            print("No I2C devices found.")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    scan_i2c()

