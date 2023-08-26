import board
import busio
import time

import microcontroller
import adafruit_requests as requests
import adafruit_esp32spi.adafruit_esp32spi_socket as socket

from digitalio import DigitalInOut, Direction
from adafruit_esp32spi import adafruit_esp32spi
from adafruit_motor import stepper


TIME_URL = "http://worldtimeapi.org/api/ip"
DISCORD_TOKEN = ""
CHANNEL_ID = ""
DEBUG_CHANNEL_ID = ""
PEANUT = "%F0%9F%A5%9C"
CHESTNUT = "%F0%9F%8C%B0"
SSID = ""
PASSWORD = ""
MOTOR_DELAY = 1
MOTOR_STEPS = 200
FEEDING_INTERVAL = 10


try:
    # configure the esp32 wifi chip
    esp32_cs = DigitalInOut(board.ESP_CS)
    esp32_ready = DigitalInOut(board.ESP_BUSY)
    esp32_reset = DigitalInOut(board.ESP_RESET)

    spi = busio.SPI(board.SCK, board.MOSI, board.MISO)
    esp = adafruit_esp32spi.ESP_SPIcontrol(spi, esp32_cs, esp32_ready, esp32_reset)
    requests.set_socket(socket, esp)

    print("Connecting to AP...")
    while not esp.is_connected:
        try:
            esp.connect_AP(SSID, PASSWORD)
        except OSError as e:
            print("could not connect to AP, retrying: ", e)
            continue


    # configure the stepper motor
    coils = (
        DigitalInOut(board.D8),
        DigitalInOut(board.D9),
        DigitalInOut(board.D10),
        DigitalInOut(board.D11),
    )
    for coil in coils:
        coil.direction = Direction.OUTPUT

    motor = stepper.StepperMotor(coils[0], coils[1], coils[2], coils[3], microsteps=None)


    print("Starting main loop")
    headers = {"Authorization": "Bot {DISCORD_TOKEN}".format(DISCORD_TOKEN=DISCORD_TOKEN), "Content-Length": "0"}
    messages_url = "https://discord.com/api/v9/channels/{CHANNEL_ID}/messages?limit=3"
    reactions_url = "https://discord.com/api/v9/channels/{CHANNEL_ID}/messages/{MESSAGE_ID}/reactions/{EMOJI}/@me"

    print('stepping')
    for step in range(MOTOR_STEPS // 3):
        print(step)
        motor.onestep(direction=stepper.BACKWARD)
        time.sleep(MOTOR_DELAY / 2)

    while True:

        t_resp = requests.get(TIME_URL).json()
        now = t_resp["datetime"]
        if now.split("T")[1][:05] == "13:00":
            microcontroller.reset()

        resp = requests.get(messages_url.format(CHANNEL_ID=CHANNEL_ID), headers=headers)
        latest_message = resp.json()[0]
        resp.close()

        if "reactions" not in latest_message:
            print("Received message, dispensing nuts")
            r = requests.put(reactions_url.format(CHANNEL_ID=CHANNEL_ID, MESSAGE_ID=latest_message["id"], EMOJI=PEANUT), headers=headers)
            print(r.status_code)
            r.close()
            r = requests.put(reactions_url.format(CHANNEL_ID=CHANNEL_ID, MESSAGE_ID=latest_message["id"], EMOJI=CHESTNUT), headers=headers)
            print(r.status_code)
            r.close()

            # turn 1/6th of a full turn
            for step in range(MOTOR_STEPS // 3):
                print(step)
                motor.onestep(direction=stepper.BACKWARD)
                time.sleep(MOTOR_DELAY)

            for step in range(MOTOR_STEPS // 3):
                print(step)
                motor.onestep(direction=stepper.FORWARD)
                time.sleep(MOTOR_DELAY)

            print("sleeping {minutes} minutes".format(minutes=FEEDING_INTERVAL))
            time.sleep(FEEDING_INTERVAL * 60)

    time.sleep(30)

except:
    microcontroller.reset()
