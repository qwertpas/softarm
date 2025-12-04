import serial
import time

port = '/dev/tty.usbmodem2101'
serial_port = serial.Serial(port, 921600, timeout=0.1)

serial_port.write('P10:1'.encode())
time.sleep(0.5)
serial_port.write('P10:0'.encode())
time.sleep(0.5)

serial_port.close()
