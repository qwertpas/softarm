from adafruit_httpserver import Server, FileResponse, Request, Response, Websocket, OK_200, Headers, Status
from adafruit_motor import servo
from random import choice

import pwmio
import time
import json
import digitalio
import espcamera
import board
import wifi
import socketpool
import busio
import asyncio
import microcontroller

try:
    from typing import Dict, List, Tuple, Union
except ImportError:
    pass

FRAME_SIZE = espcamera.FrameSize.HVGA # 480x320p
# FRAME_SIZE = espcamera.FrameSize.VGA # 640x480p
# FRAME_SIZE = espcamera.FrameSize.HD # 1280x720p
# FRAME_SIZE = espcamera.FrameSize.FHD # 1920x1080p

# FRAME_SIZE = espcamera.FrameSize.UXGA

i2c = busio.I2C(board.CAM_SCL, board.CAM_SDA)

cam = espcamera.Camera(
    data_pins=board.CAM_DATA,
    external_clock_pin=board.CAM_XCLK,
    pixel_clock_pin=board.CAM_PCLK,
    vsync_pin=board.CAM_VSYNC,
    href_pin=board.CAM_HREF,
    pixel_format=espcamera.PixelFormat.JPEG,
    frame_size=FRAME_SIZE,
    i2c=i2c,
    external_clock_frequency=20_000_000,
    grab_mode=espcamera.GrabMode.WHEN_EMPTY,
    framebuffer_count=2,
    jpeg_quality=20)

cam.vflip = True

class XMixedReplaceResponse(Response):
    def __init__(
        self,
        request: Request,
        frame_content_type: str,
        *,
        status: Union[Status, Tuple[int, str]] = OK_200,
        headers: Union[Headers, Dict[str, str]] = None,
        cookies: Dict[str, str] = None,
    ) -> None:
        super().__init__(
            request=request,
            headers=headers,
            cookies=cookies,
            status=status,
        )
        self._boundary = self._get_random_boundary()
        self._headers.setdefault(
            "Content-Type", f"multipart/x-mixed-replace; boundary={self._boundary}"
        )
        self._frame_content_type = frame_content_type

    @staticmethod
    def _get_random_boundary() -> str:
        symbols = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
        return "--" + "".join([choice(symbols) for _ in range(16)])

    def send_frame(self, frame: Union[str, bytes] = "") -> None:
        encoded_frame = bytes(frame.encode("utf-8") if isinstance(frame, str) else frame)

        self._send_bytes(self._request.connection, bytes(f"{self._boundary}\r\n", "utf-8"))
        self._send_bytes(
            self._request.connection,
            bytes(f"Content-Type: {self._frame_content_type}\r\n\r\n", "utf-8"),
        )
        self._send_bytes(self._request.connection, encoded_frame)
        self._send_bytes(self._request.connection, bytes("\r\n", "utf-8"))

    def _send(self) -> None:
        self._send_headers()

    def close(self) -> None:
        self._close_connection()

wifi.radio.connect('NETGEAR93', 'helpfullotus935')
print(f"Successfully connected to WiFi with IP Address: {wifi.radio.ipv4_address}!")

server = Server(socketpool.SocketPool(wifi.radio), '/website', debug=True)

websockets = []
stream_connections = []

# @server.route('/', 'GET')
# def home(request: Request):
#     print(f"{request.client_address} accessed the root!")
#     return FileResponse(request, 'index.html')

@server.route('/websocket', 'GET')
def websockets_route(request: Request):
    print(f"{request.client_address} made a websocket connection!")
    websocket = Websocket(request)
    websockets.append(websocket)
    return websocket

@server.route("/frame")
def frame_handler(request: Request):
    jpeg = cam.take(0.1)
    if jpeg is not None:
        print(f"Captured JPEG of length {len(jpeg)}")
    return Response(request, body=jpeg, content_type="image/jpeg")

@server.route("/stream")
def stream_handler(request: Request):
    response = XMixedReplaceResponse(request, frame_content_type="image/jpeg")
    stream_connections.append(response)

    return response

server.start(str(wifi.radio.ipv4_address), port=80)

async def send_stream_frames():
    while True:
        frame = cam.take(0.1)
        if frame:
            for connection in iter(stream_connections):
                try:
                    connection.send_frame(frame)
                except BrokenPipeError:
                    connection.close()
                    stream_connections.remove(connection)
        else:
            print('dropped frame')
        # await asyncio.sleep(1/60) # 60 fps
        await asyncio.sleep(0.05) # 20 fps
        # await asyncio.sleep(0.2) # 5 fps


async def handle_http_requests():
    led = digitalio.DigitalInOut(board.LED)
    led.direction = digitalio.Direction.OUTPUT
    led.value = False
    while True:
        server.poll()
        await asyncio.sleep(0)

# create a PWMOut object on Pin .
pwm = pwmio.PWMOut(board.D10, duty_cycle=2 ** 15, frequency=50)
# Create a servo object, my_servo.
my_servo = servo.Servo(pwm)

async def handle_websocket_requests():
    while True:
        removing = []
        for websocket in websockets:
            try:
                packet = json.loads(websocket.receive())
            except (ValueError, TypeError):
                packet = None

            if websocket.closed:
                removing.append(websocket)
            elif packet:
                # 0 is closed, 180 is fully opened
                angle = max(min(150, packet['angle']), 0)
                print(f"Setting motor angle to {angle}")
                my_servo.angle = angle
        for remove in removing:
            websockets.remove(remove)
        await asyncio.sleep(0)

# async def move_servo():
#     print('moving servo')
#     while True:
#         # 0 is closed
#         # 180 is fully opened
#         my_servo.angle = 150
#         await asyncio.sleep(1)
#         my_servo.angle = 0
#         await asyncio.sleep(1)

async def print_temp():
    while True:
        print(f"Temperature: {microcontroller.cpu.temperature:.2f} °C", end='\r')
        await asyncio.sleep(1)

async def main():
    await asyncio.gather(
        asyncio.create_task(handle_http_requests()),
        # asyncio.create_task(move_servo()),
        asyncio.create_task(send_stream_frames()),
        asyncio.create_task(print_temp()),
        asyncio.create_task(handle_websocket_requests()),
        # asyncio.create_task(send_rpm_websocket()),
    )

asyncio.run(main())
