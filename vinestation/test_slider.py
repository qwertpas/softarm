"""Minimal test to debug tk.Scale vs ttk.Scale behavior with negative bounds"""
import tkinter as tk
from tkinter import ttk

class TestApp:
    def __init__(self, root):
        self.root = root
        self.min_bound = -10.0
        self.max_bound = 10.0
        self.value = 0.0
        
        # Info label
        self.info = tk.StringVar(value="Click buttons to test")
        tk.Label(root, textvariable=self.info).pack(pady=10)
        
        # Value display
        self.val_display = tk.StringVar(value="0.00")
        tk.Label(root, textvariable=self.val_display, font=('Courier', 24)).pack()
        
        # Bounds display
        self.bounds_display = tk.StringVar(value=f"Bounds: [{self.min_bound}, {self.max_bound}]")
        tk.Label(root, textvariable=self.bounds_display).pack()
        
        # Classic tk.Scale (should work correctly)
        tk.Label(root, text="tk.Scale (classic):").pack(pady=(10,0))
        self.slider_tk = tk.Scale(root, from_=self.min_bound, to=self.max_bound, 
                                  orient='horizontal', showvalue=True, resolution=0.1,
                                  length=300)
        self.slider_tk.pack(padx=20)
        self.slider_tk.set(0)
        
        # ttk.Scale (buggy with negative bounds)
        tk.Label(root, text="ttk.Scale (themed - buggy):").pack(pady=(10,0))
        self.slider_ttk_frame = tk.Frame(root)
        self.slider_ttk_frame.pack(padx=20, fill='x')
        self.slider_ttk = ttk.Scale(self.slider_ttk_frame, from_=self.min_bound, to=self.max_bound, 
                                    orient='horizontal')
        self.slider_ttk.pack(fill='x')
        self.slider_ttk.set(0)
        
        # Buttons
        btn_frame = tk.Frame(root)
        btn_frame.pack(pady=10)
        
        tk.Button(btn_frame, text="- (decrease)", command=lambda: self.change(-1)).pack(side='left', padx=5)
        tk.Button(btn_frame, text="+ (increase)", command=lambda: self.change(1)).pack(side='left', padx=5)
        
        # Debug info
        tk.Label(root, text="Watch: tk.Scale should work, ttk.Scale will break").pack(pady=10)
        
    def change(self, delta):
        self.value += delta
        self.val_display.set(f"{self.value:.2f}")
        
        # Check if we need to expand bounds
        if self.value < self.min_bound:
            self.min_bound = self.value - 5
        if self.value > self.max_bound:
            self.max_bound = self.value + 5
        
        self.bounds_display.set(f"Bounds: [{self.min_bound}, {self.max_bound}]")
        
        # Update tk.Scale - should work fine
        self.slider_tk.configure(from_=self.min_bound, to=self.max_bound)
        self.slider_tk.set(self.value)
        
        # Update ttk.Scale - will likely break
        self.slider_ttk.configure(from_=self.min_bound, to=self.max_bound)
        self.slider_ttk.set(self.value)
        
        self.info.set(f"tk.Scale.get()={self.slider_tk.get():.2f}, ttk.Scale.get()={self.slider_ttk.get():.2f}")

if __name__ == "__main__":
    root = tk.Tk()
    root.title("Slider Test - tk vs ttk")
    root.geometry("400x450")
    app = TestApp(root)
    root.mainloop()
