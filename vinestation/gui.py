import tkinter as tk
import serial
import serial.tools.list_ports
import threading
import time
import json
from websockets.sync.client import connect

class MotorControlGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Motor Controller")
        
        self.serial_port = None
        self.connected = False
        self.current_pos = 0.0
        self.target_pos = 0.0
        self.min_bound = -10.0
        self.max_bound = 10.0
        self.repeat_job = None
        self.ignore_slider_event = False
        self.offset = None
        
        self.ws_url = "ws://192.168.1.27/websocket"
        
        # UI Setup
        self.setup_ui()
        
        # Start Serial Thread
        self.running = True
        self.thread = threading.Thread(target=self.serial_loop)
        self.thread.daemon = True
        self.thread.start()

    def setup_ui(self):
        # Connection Status
        self.status_var = tk.StringVar(value="Searching for ESP32...")
        tk.Label(self.root, textvariable=self.status_var).pack(pady=5)

        # Current Position Frame
        curr_frame = tk.LabelFrame(self.root, text="Current Position", padx=10, pady=5)
        curr_frame.pack(fill="x", padx=10, pady=5)
        
        self.curr_pos_var = tk.StringVar(value="0.00")
        tk.Entry(curr_frame, textvariable=self.curr_pos_var, state="readonly", justify='center').pack(fill="x")
        
        # Use tk.Scale (classic) instead of ttk.Scale
        # Note: Don't use state="disabled" as it prevents .set() from working
        self.curr_scale = tk.Scale(curr_frame, from_=self.min_bound, to=self.max_bound, 
                                   orient="horizontal", showvalue=False,
                                   sliderlength=20, length=300, takefocus=0)
        self.curr_scale.pack(fill="x", pady=5)
        # Bind to prevent user interaction but allow programmatic updates
        self.curr_scale.bind("<Button-1>", lambda e: "break")
        self.curr_scale.bind("<B1-Motion>", lambda e: "break")

        # Target Position Frame
        self.target_frame = tk.LabelFrame(self.root, text="Target Position", padx=10, pady=5)
        self.target_frame.pack(fill="x", padx=10, pady=5)
        
        self.target_entry_var = tk.StringVar(value="0.0")
        self.target_entry = tk.Entry(self.target_frame, textvariable=self.target_entry_var, justify='center')
        self.target_entry.pack(fill="x")
        self.target_entry.bind('<Return>', self.on_entry_change)
        
        # Button Frame
        btn_frame = tk.Frame(self.target_frame)
        btn_frame.pack(fill="x", pady=2)
        
        # Minus Button with hold-to-repeat
        btn_minus = tk.Button(btn_frame, text="-", width=5)
        btn_minus.pack(side="left", padx=5)
        btn_minus.bind('<ButtonPress-1>', lambda e: self.start_repeat(-0.1))
        btn_minus.bind('<ButtonRelease-1>', self.stop_repeat)
        
        # Plus Button with hold-to-repeat
        btn_plus = tk.Button(btn_frame, text="+", width=5)
        btn_plus.pack(side="right", padx=5)
        btn_plus.bind('<ButtonPress-1>', lambda e: self.start_repeat(0.1))
        btn_plus.bind('<ButtonRelease-1>', self.stop_repeat)
        
        # Use tk.Scale (classic) - it handles dynamic bounds better
        self.target_scale = tk.Scale(self.target_frame, from_=self.min_bound, to=self.max_bound,
                                     orient="horizontal", showvalue=False, sliderlength=20,
                                     resolution=0.01, command=self.on_slider_change)
        self.target_scale.pack(fill="x", pady=5)
        self.target_scale.set(0.0)

        # GPIO Frame
        gpio_frame = tk.LabelFrame(self.root, text="GPIO Control", padx=10, pady=5)
        gpio_frame.pack(fill="x", padx=10, pady=5)
        
        self.gpio_vars = {}
        for pin in [8, 9, 10]:
            var = tk.IntVar()
            self.gpio_vars[pin] = var
            cb = tk.Checkbutton(gpio_frame, text=f"Pin {pin}", variable=var, 
                                command=lambda p=pin: self.toggle_gpio(p))
            cb.pack(side="left", padx=10)

        # Servo Frame
        servo_frame = tk.LabelFrame(self.root, text="Servo Control", padx=10, pady=5)
        servo_frame.pack(fill="x", padx=10, pady=5)
        
        tk.Button(servo_frame, text="Open Servo", 
                  command=lambda: self.send_servo_cmd(160)).pack(side="left", padx=5, expand=True, fill="x")
        tk.Button(servo_frame, text="Close Servo", 
                  command=lambda: self.send_servo_cmd(0)).pack(side="right", padx=5, expand=True, fill="x")

    def find_port(self):
        ports = list(serial.tools.list_ports.comports())
        for p in ports:
            if "usbmodem" in p.device.lower() or "serial" in p.description.lower():
                if len(p.device) < 20:
                    return p.device
        return None

    def serial_loop(self):
        while self.running:
            if not self.connected:
                port = self.find_port()
                if port:
                    try:
                        self.serial_port = serial.Serial(port, 921600, timeout=0.1)
                        self.connected = True
                        self.status_var.set(f"Connected: {port}")
                        time.sleep(2)
                    except Exception as e:
                        self.status_var.set(f"Error: {e}")
                        time.sleep(1)
                else:
                    time.sleep(1)
                continue

            try:
                if self.serial_port.in_waiting:
                    lines = self.serial_port.read_all().decode('utf-8', errors='ignore').strip().split('\n')
                    if lines:
                        last_line = lines[-1]
                        try:
                            val = float(last_line)
                            if self.offset is None:
                                self.offset = val
                            
                            self.current_pos = val - self.offset
                            self.root.after(0, self.update_gui_from_serial)
                        except ValueError:
                            pass 
            except Exception as e:
                self.connected = False
                self.offset = None
                self.status_var.set("Disconnected")
                if self.serial_port:
                    self.serial_port.close()
            
            time.sleep(0.001)

    def update_gui_from_serial(self):
        self.curr_pos_var.set(f"{self.current_pos:.2f}")
        self.curr_scale.set(self.current_pos)

    def autoscale(self, value):
        """Expand bounds if value is outside current range."""
        margin = 5.0
        changed = False
        
        if value < self.min_bound:
            self.min_bound = value - margin
            changed = True
        if value > self.max_bound:
            self.max_bound = value + margin
            changed = True
        
        if changed:
            # Update both scales with new bounds
            self.curr_scale.configure(from_=self.min_bound, to=self.max_bound)
            self.target_scale.configure(from_=self.min_bound, to=self.max_bound)

    def send_target(self):
        if self.connected and self.serial_port:
            try:
                actual_target = self.target_pos + (self.offset if self.offset else 0.0)
                msg = f"M{actual_target}\n"
                self.serial_port.write(msg.encode('utf-8'))
            except Exception:
                pass

    def toggle_gpio(self, pin):
        if self.connected and self.serial_port:
            try:
                state = self.gpio_vars[pin].get()
                msg = f"P{pin}:{state}\n"
                self.serial_port.write(msg.encode('utf-8'))
            except Exception:
                pass

    def send_servo_cmd(self, angle):
        threading.Thread(target=self._send_servo_ws, args=(angle,), daemon=True).start()

    def _send_servo_ws(self, angle):
        try:
            with connect(self.ws_url) as websocket:
                msg = json.dumps({"angle": angle})
                websocket.send(msg)
                print(f"Sent Servo: {msg}")
        except Exception as e:
            print(f"Servo Error: {e}")

    def on_slider_change(self, val):
        if self.ignore_slider_event:
            return
        
        self.target_pos = float(val)
        self.target_entry_var.set(f"{self.target_pos:.2f}")
        self.send_target()

    def set_target_programmatically(self, val):
        self.ignore_slider_event = True
        self.target_pos = val
        self.target_entry_var.set(f"{val:.2f}")
        self.autoscale(val)
        self.target_scale.set(val)
        self.send_target()
        self.root.after(10, self.enable_slider_events)

    def enable_slider_events(self):
        self.ignore_slider_event = False

    def on_entry_change(self, event):
        try:
            val = float(self.target_entry_var.get())
            self.set_target_programmatically(val)
        except ValueError:
            pass

    def increment_target(self, delta):
        new_val = self.target_pos + delta
        self.set_target_programmatically(new_val)

    def start_repeat(self, delta):
        self.increment_target(delta)
        self.repeat_job = self.root.after(50, lambda: self.start_repeat(delta))

    def stop_repeat(self, event=None):
        if self.repeat_job:
            self.root.after_cancel(self.repeat_job)
            self.repeat_job = None

if __name__ == "__main__":
    root = tk.Tk()
    app = MotorControlGUI(root)
    root.geometry("400x550")
    root.mainloop()
