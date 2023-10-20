# 2022-09-24 downloaded from: https://github.com/UnexpectedMaker/esp32s3/tree/main/code/micropython/helper%20libraries/pros3
# ProS3 MicroPython Helper Library
# 2022 Seon Rozenblum - Unexpected Maker
#
# Project home:
# http://pros3.io
#
# 2022-09-24 Modified by @PaulskPt for CircuitPython V8.0.0-beta.0

# Import required libraries
#from micropython import const
#from machine import Pin, ADC
import time
import board
import time
import digitalio
import analogio

# ProS3 Hardware Pin Assignments

# Sense Pins
#VBUS_SENSE = const(33)
#VBAT_SENSE = const(10)
VBUS_SENSE = board.VBUS_SENSE  # = board.IO34
VBAT_SENSE = board.VBAT_SENSE  # = bpard-OP2 (VBAT)

# RGB LED & LDO2 Pins
#RGB_DATA = const(18)
RGB_DATA = board.NEOPIXEL  # = board.IO40
RGB_POWER = board.NEOPIXEL_POWER 

#LDO2 = const(17)
LDO2 = board.LDO2  # = board.
# SPI
#SPI_MOSI = const(35)
SPI_MOSI = board.MOSI
#SPI_MISO = const(37)
SPI_MISO = board.MISO
#SPI_CLK = const(36)
SPI_CLK = board.SCK

# I2C
#I2C_SDA = const(8)
I2C_SDA = board.SDA
#I2C_SCL = const(9)
I2C_SCL = board.SCL

# Helper functions
def set_ldo2_power(state):
    """Enable or Disable power to the second LDO"""
    #Pin(LDO2, Pin.OUT).value(state)
    ldo2 = digitalio.DigitalInOut(LDO2)
    ldo2.direction = digitalio.Direction.OUTPUT
    ldo2.value = state


def get_battery_voltage():
    """
    Returns the current battery voltage. If no battery is connected, returns 4.2V which is the charge voltage
    This is an approximation only, but useful to detect if the charge state of the battery is getting low.
    """
    #adc = ADC(Pin(VBAT_SENSE))  # Assign the ADC pin to read
    adc = analogio.AnalogIn(VBAT_SENSE)
    # We are going to read the ADC 10 times and discard the results as we can't guarantee the ADC is calibrated or stable yet after boot. Not sure why we have to do this :(
    for _ in range(10):
        n = adc.value
    measuredvbat = adc.value
    measuredvbat /= 4095  # divide by 4095 as we are using the default ADC voltage range of 0-1.2V
    measuredvbat *= 4.2  # Multiply by 4.2V, our max charge voltage for a 1S LiPo
    return round(measuredvbat, 2)


def get_vbus_present():
    """Detect if VBUS (5V) power source is present"""
    vb = digitalio.DigitalInOut(VBUS_SENSE)
    vb.direction = digitalio.Direction.INPUT  
    return vb.value() == 1


# NeoPixel rainbow colour wheel
def rgb_color_wheel(wheel_pos):
    """Color wheel to allow for cycling through the rainbow of RGB colors."""
    wheel_pos = wheel_pos % 255

    if wheel_pos < 85:
        return 255 - wheel_pos * 3, 0, wheel_pos * 3
    elif wheel_pos < 170:
        wheel_pos -= 85
        return 0, wheel_pos * 3, 255 - wheel_pos * 3
    else:
        wheel_pos -= 170
        return wheel_pos * 3, 255 - wheel_pos * 3, 0