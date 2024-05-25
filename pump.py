"""
Water pump Rpi4

This class is used to water a plant with  a pump

Author: Tommaso Bacci
"""
from utils import printlog
import RPi.GPIO as GPIO
import time


class Pump:

    def __init__(self, gpio_pin):

        # Set the GPIO mode
        GPIO.setmode(GPIO.BCM)
        # Define the GPIO pin connected to the relay
        self.relay_pin = gpio_pin
        # Set up the GPIO pin as an output
        GPIO.setup(self.relay_pin, GPIO.OUT)
    

    def water_plant(self, seconds = 8):
        GPIO.output(self.relay_pin, GPIO.HIGH)
        printlog("\nPump ON")
        time.sleep(seconds)
        self.pump_off()


    def pump_off(self):
        GPIO.output(self.relay_pin, GPIO.LOW)
        printlog("Pump OFF - 200ml")
    

    def test(self):
        print(f"\nWater Pump 3s...")
        self.water_plant(3)
        print(f"\nWater Pump OK!")



