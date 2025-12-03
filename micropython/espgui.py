import tkinter as tk
from tkinter import messagebox
import serial
import time
import sys

# --- CONFIGURATION ---
SERIAL_PORT = '/dev/tty.usbmodem101'  # <--- CONFIRM THIS IS YOUR PORT!
BAUD_RATE = 115200

# This is the MicroPython code we inject into the ESP32 RAM on startup.
# It defines a helper function (set_pin) for quick control.
# We no longer include print statements here as Raw REPL handles errors differently.
ESP_INIT_CODE = b"""
import machine
gpios = {}
def set_pin(pin_num, state):
    # Ensure pin is in our cache
    if pin_num not in gpios:
        gpios[pin_num] = machine.Pin(pin_num, machine.Pin.OUT)
    
    # Force output mode just in case it got reset
    # gpios[pin_num].init(machine.Pin.OUT) 
    
    # Set the value (1 or 0)
    gpios[pin_num].value(1 if state else 0)
"""

class ESP32Controller:
    def __init__(self, port):
        try:
            self.ser = serial.Serial(port, BAUD_RATE, timeout=0.5) 
            
            # 1. Stop any running program
            self.ser.write(b'\x03') 
            time.sleep(0.05)
            
            # 2. Enter Raw REPL Mode (\x01 is Ctrl+A, which enters raw mode)
            self.ser.write(b'\x01') 
            time.sleep(0.05)
            # Read and discard the "OK" response from entering raw REPL
            self.ser.read_all()
            
            # 3. Send the initialization code as a complete block
            # Raw REPL expects the code with newlines, terminated by Ctrl+D
            self.ser.write(ESP_INIT_CODE.strip() + b'\n')
            time.sleep(0.02)

            # 4. Execute the code block and return to normal mode (\x04 is Ctrl+D)
            self.ser.write(b'\x04') 
            time.sleep(0.1) 
            
            # Check for errors after execution
            response = self.ser.read_all().decode('utf-8', errors='ignore')
            if 'Traceback' in response or 'Error' in response or 'SyntaxError' in response:
                 print(f"!!! CRITICAL ESP32 ERROR DURING INIT: {response.strip()}", file=sys.stderr)
                 # Raise an error to stop the GUI from running on a failed setup
                 raise ConnectionError("ESP32 setup failed. See error log above.")
        except serial.SerialException as e:
            messagebox.showerror("Connection Error", f"Could not open port {port}\n\n{e}")
            raise

    def toggle_pin(self, pin, state):
        val = 1 if state else 0
        
        # Use Raw REPL for more reliable command execution
        # 1. Enter Raw REPL
        self.ser.write(b'\x01')  # Ctrl+A
        time.sleep(0.03)
        self.ser.read_all()  # Discard "OK"
        
        # 2. Send the command
        cmd = f"set_pin({pin}, {val})\n"
        self.ser.write(cmd.encode('utf-8'))
        time.sleep(0.02)
        
        # 3. Execute with Ctrl+D
        self.ser.write(b'\x04')
        time.sleep(0.08)
        
        # 4. Read response and check for errors only
        raw_bytes = self.ser.read_all()
        if raw_bytes:
            try:
                decoded = raw_bytes.decode('utf-8', errors='replace')
                if 'Traceback' in decoded or 'Error' in decoded or 'NameError' in decoded:
                    print(f"ESP32 ERROR: {decoded.strip()}", file=sys.stderr)
            except Exception as e:
                print(f"Decode error: {e}", file=sys.stderr) 

class GPIOApp:
    def __init__(self, root, controller):
        self.root = root
        self.controller = controller
        self.root.title("ESP32-S3 GPIO Control")
        self.root.geometry("400x450")
        
        # Grid Configuration
        self.root.columnconfigure(0, weight=1) # Left Col
        self.root.columnconfigure(1, weight=1) # Right Col

        # --- LEFT COLUMN (LED 48 + Pins 1-7 Ascending) ---
        
        # LED 48 (Upper Left)
        self.create_toggle(48, "LED (48)", row=0, col=0, color="red")
        
        # Pins 1-7
        row_idx = 1
        for pin in range(1, 8): # 1 to 7
            self.create_toggle(pin, f"GPIO {pin}", row=row_idx, col=0)
            row_idx += 1

        # --- RIGHT COLUMN (Pins 13-8 Descending) ---
        
        # Pins 13-8 (Starts at row 1 for vertical alignment)
        row_idx = 1
        for pin in range(13, 7, -1): # 13 down to 8
            self.create_toggle(pin, f"GPIO {pin}", row=row_idx, col=1)
            row_idx += 1

    def create_toggle(self, pin, label_text, row, col, color="green"):
        # Frame to hold label and button
        frame = tk.Frame(self.root, pady=5)
        frame.grid(row=row, column=col, sticky="ew", padx=20)
        
        lbl = tk.Label(frame, text=label_text, width=10, anchor="w", font=("Arial", 12))
        lbl.pack(side="left")
        
        # Toggle Button (Checkbutton styled)
        var = tk.BooleanVar()
        btn = tk.Checkbutton(
            frame, 
            text="OFF", 
            variable=var, 
            indicatoron=0, 
            width=8,
            selectcolor=color, 
            command=lambda p=pin, v=var, b=None: self.on_toggle(p, v)
        )
        btn.configure(command=lambda p=pin, v=var, b=btn: self.on_toggle(p, v, b))
        btn.pack(side="right")

    def on_toggle(self, pin, var, btn):
        state = var.get()
        # Update button text
        if btn:
            btn.configure(text="ON" if state else "OFF")
        
        # Send command to ESP32
        self.controller.toggle_pin(pin, state)

if __name__ == "__main__":
    PORT = SERIAL_PORT 
    
    try:
        esp = ESP32Controller(PORT)
        root = tk.Tk()
        app = GPIOApp(root, esp)
        root.mainloop()
    except Exception as e:
        print(f"\n--- Application Shutdown ---", file=sys.stderr)
        print(f"Error during main execution: {e}", file=sys.stderr)