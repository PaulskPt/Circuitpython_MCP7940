
# SPDX-FileCopyrightText: 2023 Paulus Schulinck
#
# SPDX-License-Identifier: MIT
##############################

"""
    This CircuitPython script is created to show how I managed to:
    a) read the values of the registers (e.g.: timekeeping data) from an Unexpected Maker MCP7940 RTC board;
    b) write and read timekeeping data to and from the MCP7940's user SRAM space.

    I created and tested this script on an Unexpected Maker ESP32S ProS3 flashed with circuitpython,
    version: 8.2.6.
    This script is also able to send texts to an attached I2C display,
    in my case an Adafruit 1.12 inch mono OLED 128x128 display (SH1107).

    Note: since CircuitPython (CPY) V8.x the CPY status_bar is set ON/off in file: boot.py

    This script is tested successfully on an Unexpected Maker ProS3.

    Update October 2023:

    The script tries to establish WiFi and when successfull it will fetch a datetime stamp from the Adafruit NTP server.
    Depending of the global boolean variables: 'state.set_SYS_RTC' and 'state.set_EXT_RTC', the internal and/or the external RTC(s)
    is/are set.

    The external MCP7940 RTC timekeeping set values will be read frequently.
    For test this script and the library script mcp7940.py contain function to write and read datetime stamps
    to and from the MCP7940 user space in its SRAM.
    The MCP7940 RTC needs only to be set when the RTC has been without power or not has been set before.
    When you need more (debug) output to the REPL, set the global variable 'my_debug' to True.

    Note that NTP weekday starts with 0. Also time.localtime element tm_wday ranges 0-6 while MCP7940 weekday range is 1-7.
    For this reason we use a mRTC_DOW dictionary in the State Class in this file and
    Then in three places corrections are performed:
    a DOW dictionary in the MCP7940 Class in the file lib/mcp7940.py.
    a) In function set_EXT_RTC() we do the following:
        dt = time.localtime()
        state.dt_dict[state.wd] = dt.tm_wday + 1
    b) In function set_alarm() we do the following:
        t1 = time.time()  # get seconds since epoch
        dt = time.localtime(t1+(mins_fm_now*60)) # convert mins_fm_now to seconds
        weekday = dt.tm_wday + 1
    c) In function upd_SRAM(), after reading the datetime stamp from SRAM we add a correction:
        weekday += 1

    Want to see more of my work: Github @PaulskPt

"""
import time
import sys, os, gc
import board
import wifi
import ipaddress
import socketpool
import rtc
import displayio
import rtc
import mcp7940
import digitalio
# Global flags

my_debug = False  # Set to True if you need debug output to REPL

# --- DISPLAY DRTIVER selection flag ----+
use_sh1107 = True    #                   |
# ---------------------------------------+
use_wifi = True
use_TAG = True
use_ping = True

id = board.board_id 

if id == 'unexpectedmaker_pros3':
    import pros3 
    import neopixel

time.sleep(5) # wait for mu-editor can show REPL from start

mRTC = rtc.RTC()  # create internal RTC object
if my_debug:
    print(f"global mRTC: {mRTC}")

import adafruit_ntp
pool = socketpool.SocketPool(wifi.radio)
ntp = adafruit_ntp.NTP(pool, tz_offset=0)

pool = None

state = None

class State:
    def __init__(self, saved_state_json=None):
        self.board_id = None
        self.lStart = True
        self.loop_nr = -1
        self.ssid = None
        self.tag_le_max = 24  # see tag_adj()
        self.use_clr_SRAM = False
        self.set_SYS_RTC = True
        self.NTP_dt_is_set = False
        self.SYS_RTC_is_set = False
        self.set_EXT_RTC = True # Set to True to update the MCP7940 RTC datetime values (and set the values of dt_dict below)
        self.EXT_RTC_is_set = False
        self.save_dt_fm_int_rtc = False  # when save_to_SRAM, save datetime from INTernal RTC (True) or EXTernal RTC (False)
        self.dt_str_usa = True
        self.SYS_dt = None # time.localtime()
        self.SRAM_dt = None  #see setup()
        self.ip = None
        self.s__ip = None
        self.mac = None
        self.NTP_dt = None
        self.SYS_dt = None
        self.SRAM_dt = None
        self.use_neopixel = None
        self.neopixel_brightness = None
        self.BLK = None
        self.RED = None
        self.GRN = None
        self.curr_color_set = self.BLK
        self.yy = 0
        self.mo = 1
        self.dd = 2
        self.hh = 3
        self.mm = 4
        self.ss = 5
        self.wd = 6
        self.yd = 7
        self.isdst = 8
        self.dt_dict = {
            self.yy: 2023,
            self.mo: 10,
            self.dd: 4,
            self.hh: 16,
            self.mm: 10,
            self.ss: 0,
            self.wd: 2,
            self.yd: 277,
            self.isdst: -1}
        self.alarm1 = ()
        self.alarm2 = ()
        self.alarm1_int = False
        self.alarm2_int = False
        self.alarm1_set = False
        self.alarm2_set = False
        self.mfp = False
        self._match_lst_long = ["second", "minute", "hour", "weekday", "date", "reserved", "reserved", "all"]
        self.mRTC_DOW = DOW =  \
        {
            0: "Monday",
            1: "Tuesday",
            2: "Wednesday",
            3: "Thursday",
            4: "Friday",
            5: "Saturday",
            6: "Sunday"
        }
        self.month_dict = {
            1: "Jan",
            2: "Feb",
            3: "Mar",
            4: "Apr",
            5: "May",
            6: "Jun",
            7: "Jul",
            8: "Aug",
            9: "Sep",
            10: "Oct",
            11: "Nov",
            12: "Dec"
        }


state = State()

state.board_id = board.board_id

# Set the interrupt line coming from the UM RTC Shield, pin 4 (MFP)
# According to the RTC Shield schematic the MFP pin is pulled up
# through a 10kOhm resistor, connected to VCC (3.3V).
rtc_mfp_int = digitalio.DigitalInOut(board.IO15)
rtc_mfp_int.direction = digitalio.Direction.INPUT
# rtc_mfp_int.pull = digitalio.Pull.UP


def pr_msg(state, msg_lst=None):
    pass

if my_debug:
    print()  # Cause REPL output be on a line under the status_bar
    print(f"MCP7940 and SH1107 tests for board: \'{id}\'") # Unexpected Maker ProS3")
    print("waiting 5 seconds...")
    time.sleep(5)
    msg = ["MCP7940 and SH1107 tests", "for board:", "\'"+state.board_id+"\'"]
    pr_msg(state, msg)

if my_debug:
    if wifi is not None:
        print(f"wifi= {type(wifi)}")
    
if id == 'unexpectedmaker_pros3':
    use_neopixel = True
    import pros3
    import neopixel
    state.neopixel_brightness = 0.005
    state.BLK = 0
    state.RED = 1
    state.GRN = 200
else:
    use_neopixel = False
    state.use_neopixel = False
    state.neopixel_brightness = None
    state.BLK = None
    state.RED = None
    state.GRN = None
    
if use_neopixel:
    pixels = neopixel.NeoPixel(board.NEOPIXEL, 1, brightness=state.neopixel_brightness, auto_write=True, pixel_order=neopixel.RGB)
else:
    pixels = None
    
i2c = None

try:
    i2c = board.STEMMA_I2C()
    if my_debug:
        print(f"i2c: {i2c}")
except RuntimeError as e:
    # print(f"Error while creating i2c object: {e}")
    if e:
        e = None
    raise

if my_debug:
    while not i2c.try_lock():
        pass

    devices = i2c.scan()
    for n in devices:
        print(f"i2c device address: {hex(n)}")

    i2c.unlock()
    n = None
    devices = None

if use_sh1107:
    displayio.release_displays()
    # code for Adafruit OLED 128x128 SH1107
    from adafruit_displayio_sh1107 import SH1107, DISPLAY_OFFSET_ADAFRUIT_128x128_OLED_5297
    # Width, height and rotation for Monochrome 1.12" 128x128 OLED
    WIDTH = 128
    HEIGHT = 128
    ROTATION = 0 # Was: 90

    # Border width
    BORDER = 2

    display_bus = displayio.I2CDisplay(i2c, device_address=0x3d)

    display = SH1107(
    display_bus,
    width=WIDTH,
    height=HEIGHT,
    display_offset=DISPLAY_OFFSET_ADAFRUIT_128x128_OLED_5297,
    rotation=ROTATION,
    )

    # Cleanup
    WIDTH = None
    HEIGHT = None
    ROTATION = None
    BORDER = None

mcp = mcp7940.MCP7940(i2c)

# Adjust the values of the state.dt_dict to the actual date and time
# Don't forget to enable the state.set_EXT_RTC flag (above)

# Set the interrupt line coming from the UM RTC Shield, pin 4 (MFP)
# According to the RTC Shield schematic the MFP pin is pulled up
# through a 10kOhm resistor, connected to VCC (3.3V).
def interrupt_handler(state):  # (pin):
    TAG = tag_adj(state, "interrupt_handler(): ")
    if state.mfp:  # We have an interrupt!
        print(TAG+"RING RING RING we have an interrupt from the RTC shield!")
        alarm_blink(state)
        clr_alarm(state, 1)
        mcp._clr_ALMxIF_bit(1) # Clear the interrupt
        state.mfp = False
        raise KeyboardInterrupt

# rtc_mfp_int.irq(handler=interrupt_handler, trigger=Pin.IRQ_RISING)

def is_NTP(state):
    TAG = tag_adj(state, "is_NTP(): ")
    ret = False
    dt = None
    try:
        if ntp is not None:
            if not state.NTP_dt_is_set:
                dt = ntp.datetime
            state.NTP_dt = dt
            if my_debug:
                print(TAG+f"state.NTP_dt: {state.NTP_dt}")
            state.NTP_dt_is_set = True
            ret = True if dt is not None else False
    except OSError as e:
        print(f"is_NTP() error: {e}")
    return ret

def is_EXT_RTC():
    if mcp is not None:
        return True
    return False

def is_INT_RTC():
    if mRTC is not None:
        return True
    return False

def set_INT_RTC(state):
    global mRTC
    if not state.set_SYS_RTC:
        return

    TAG = tag_adj(state, "set_INT_RTC(): ")
    s1 = "Internal (SYS) RTC is set from "
    s2 = "datetime stamp: "
    dt = None
    internal_RTC = True if is_INT_RTC() else False
    if internal_RTC:
        try:
            dt = ntp.datetime
            if not my_debug:
                print(TAG+f"(ntp.datetime, dt: {dt}")
            mRTC.datetime = dt
        except OSError as e:
            print(TAG+f"Error while trying to set internal RTC from NTP datetime: {e}")
            raise
        except Exception as e:
            raise
        state.SYS_dt = mRTC.datetime
        if my_debug:
            print(TAG+f"mRTC.datetime: {mRTC.datetime}")
        #print(TAG+f"state.SYS_dt: {state.SYS_dt}")
        state.SYS_RTC_is_set = True
        if state.SYS_dt.tm_year >= 2000:
             print(TAG+s1+"NTP service "+s2)

    elif state.EXT_RTC_is_set:
        mRTC = mcp.time
        state.SYS_RTC_is_set = True
        state.SYS_dt = mRTC.datetime
        if state.SYS_dt is not None:
            if state.SYS_dt.tm_year >= 2000:
                print(TAG+s1+"External RTC"+s2)
    dt = state.SYS_dt
    if not my_debug:
        print(TAG+"{:d}/{:02d}/{:02d}".format(dt.tm_mon, dt.tm_mday, dt.tm_year))
        print(TAG+"{:02d}:{:02d}:{:02d} weekday: {:s}".format(dt.tm_hour, dt.tm_min, dt.tm_sec, state.mRTC_DOW[dt.tm_wday]) )
        if internal_RTC:
            print(TAG+"Note that NTP weekday starts with 0 while MCP7940 weekday starts with 1")

def set_EXT_RTC(state):
    global mcp, dt_dict
    TAG = tag_adj(state, "set_EXT_RTC(): ")
    eRTC = "External RTC (MCP7940) "
    s1 = "We\'re going to use "
    s2 = "NTP " if is_NTP else "INT RTC "
    s3 = "to set the EXT RTC"

    """ called by setup(). Call only when MCP7940 datetime is not correct """

    if not state.set_EXT_RTC:
        return

    # We're going to set the external RTC from NTP
    print(TAG+s1+s2+s3)

    if is_NTP:
        dt = ntp.datetime
    else:
        dt = time.localtime() # state.SYS_dt

    state.dt_dict[state.yy] = dt.tm_year
    state.dt_dict[state.mo] = dt.tm_mon
    state.dt_dict[state.dd] = dt.tm_mday
    state.dt_dict[state.hh] = dt.tm_hour
    state.dt_dict[state.mm] = dt.tm_min
    state.dt_dict[state.ss] = dt.tm_sec
    state.dt_dict[state.wd] = dt.tm_wday + 1  # NTP weekday 0-6 while NTP7940 weekday 1-7
    state.dt_dict[state.yd] = mcp.yearday(dt)
    state.dt_dict[state.isdst] = -1

    if not my_debug:
        print(TAG + s2 + f"datetime stamp:")
        print(TAG+"{:d}/{:02d}/{:02d}".format(
            state.dt_dict[state.mo], state.dt_dict[state.dd], state.dt_dict[state.yy]))
        print(TAG+"{:02d}:{:02d}:{:02d} weekday: {:s}, yearday: {:d}, isdst: {:d}".format(
            state.dt_dict[state.hh], state.dt_dict[state.mm], state.dt_dict[state.ss],
            mcp.DOW[ state.dt_dict[state.wd]], state.dt_dict[state.yd], state.dt_dict[state.isdst]) )

    dt2 = (state.dt_dict[state.yy], state.dt_dict[state.mo], state.dt_dict[state.dd],
          state.dt_dict[state.hh], state.dt_dict[state.mm], state.dt_dict[state.ss],
          state.dt_dict[state.wd])

    # IMPORTANT: before setting the EXTernal RTC, set the 12/24 hour format !
    # Set 12/24 hour time format
    if not my_debug:
        print(TAG+f"setting MCP7940._is_12hr_fmt to: {state.dt_str_usa}")
    mcp.set_12hr(state.dt_str_usa)
    
    # Check:
    if not my_debug:
        ck = "12hr" if mcp._is_12hr else "24hr"
        print(TAG+f"MCP7950 datetime format: {ck}")

    if not my_debug:
        print(TAG+f"going to set {eRTC} for: {dt2}")
    # ---------------------------------------------------------------------
    #  SET THE MCP7940 RTC SHIELD TIME
    # ---------------------------------------------------------------------
    mcp.time = dt2 # Set the external RTC


    # ---------------------------------------------------------------------
    #  GET THE MCP7940 RTC SHIELD TIME
    # ---------------------------------------------------------------------
    ck_dt = mcp.time # Check it

    if ck_dt and len(ck_dt) >= 7:
        state.EXT_RTC_is_set = True
        state.SRAM_dt = ck_dt
        if not my_debug:
            s_ampm = get_ampm(ck_dt[state.hh]) # was: s_ampm = "PM" if mcp._is_PM() else "AM"
            print(TAG+eRTC+f"updated to: {ck_dt}", end='')
            print(" {:2s}".format(s_ampm),end='\n')  # mcp.is_PM checks if the time format is 12 hr
    else:
        state.SRAM_dt = ()

# Check internal RTC for AM or PM
# if state.dt_str_usa is True
def int_rtc_is_PM(tm):
    ret = False
    if tm is not None and isinstance(tm, time.struct_time):
        if state.dt_str_usa:
            hour = tm.tm_hour
            if hour >= 12:
                ret = True
    return ret

# When a call to mcp._is_12hr is positive,
# the hours will be changed from 24 to 12 hour fomat:
# AM/PM will be added to the datetime stamp
def add_12hr(t):
    TAG = tag_adj(state, "add_12hr()): ")
    if not isinstance(t, tuple):
        return
    num_registers = len(t)
    if my_debug:
        print(TAG+f"num_registers: {num_registers}")
    if num_registers == 6: 
        year, month, date, hours, minutes, seconds = t
    elif num_registers == 7:
        year, month, date, hours, minutes, seconds, weekday = t
    #num_registers = 7 if start_reg == 0x00 else 6
    is_12hr = 1 if state.dt_str_usa else 0
    
    if is_12hr:
        if my_debug:
            print(TAG+f"hours: {hours}")
        if hours >= 12:
            is_PM = 1
        else:
            is_PM = 0
        # If value of hour is more than 24 this is an indication that the 23/24hr bit and/or the AM/PM bit are set
        # so we have to mask these two bits to get a proper hour readout.
        if hours > 0x18:  # 24 hours 
            hours &= 0x1F  # suppress the 12/24hr bit and the AM/PM bit (if present)
        if hours > 12:  # After the previous check: if hours > 0x18
            hours -= 12
    else:
        is_PM = 0
        
    if my_debug:
        print(TAG+f"_is_12hr: {is_12hr}, is_PM: {is_PM}")

    t2 = (month, date, hours, minutes, seconds,  weekday)
    t3 = (year,) + t2 if num_registers == 7 else t2

    if my_debug:
        print(TAG+f"t2: {t2}")

    t3 += (is_12hr, is_PM)  # add yearday and isdst to datetime stamp
    
    if my_debug:
        print(TAG+f"return value: {t3}")

    return t3


def upd_SRAM(state):
    global SYS_dt
    TAG = tag_adj(state, "upd_SRAM(): ")
    num_registers = 0
    res = None

    if state.use_clr_SRAM:
        if my_debug:
            print(TAG+"First we go to clear the SRAM data space")
        mcp.clr_SRAM()
    else:
        if my_debug:
            print(TAG+"We\'re not going to clear SRAM. See global var \'state.use_clr_SRAM\'")
    
    # Decide which datetime stamp to save: from INTernal RTC or from EXTernal RTC. Default: from EXTernal RTC
    if state.save_dt_fm_int_rtc:
        tm = time.localtime() # Using INTernal RTC
        s_tm = "time.localtime()"
        s_tm2 = "INT"
    else:
        tm = mcp.time  # Using EXTernal RTC
        s_tm = "mcp.time"
        s_tm2 = "EXT"
    if my_debug:
        print(TAG+f"tm: {tm}")
        
    tm2 = add_12hr(tm)  # Add is_12hr, is_PM and adjust hours for 12 hour time format
    
    if my_debug:
        print(TAG+f"tm2: {tm2}")
    
    year, month, date, hours, minutes, seconds, weekday, is_12hr, is_PM = tm2
    
    tm3 = (year-2000, month, date, hours, minutes, seconds, weekday, is_12hr, is_PM)
    
    dt1 = "{}/{:02d}/{:02d}".format(
            year,
            month,
            date)

    if state.dt_str_usa:
        if is_12hr:
            ampm = "PM" if is_PM else "AM"
            dt2 = "{:d}:{:02d}:{:02d} {}".format(
            hours,
            minutes,
            seconds, 
            ampm)
        else:
            dt2 = "{:02d}:{:02d}:{:02d}".format(
            hours,
            minutes,
            seconds)

        
    wd = mcp.DOW[weekday]
    # print(TAG+f"weekday: {weekday}, mcp.DOW[weekday]: {wd}")

    dt3 = "wkday: {}".format(wd)
    
    dt6 = "is_12hr: {}".format(is_12hr)
    
    dt7 = "is_PM: {}".format(is_PM)

    msg = ["Write to SRAM:", dt1, dt2, dt3, dt6, dt7]
    pr_msg(state, msg)

    mcp.clr_SRAM()  # Empty the total SRAM
    
    if my_debug:
        mcp.show_SRAM() # Show the values in the cleared SRAM space
    
    if my_debug:
        print(TAG+f"type({s_tm}): {type(tm)},")
        print(TAG+f"{s_tm2}ernal_dt: {tm}")
    if isinstance(tm, tuple):
        if my_debug:
            print(TAG+f"we\'re going to write {s_tm} to the RTC shield\'s SRAM")
        # -----------------------------------------------------
        # WRITE TO SRAM
        # -----------------------------------------------------
        mcp.write_to_SRAM(tm3)
    if my_debug:
        print(TAG+"Check: result reading from SRAM:")
    # ----------------------------------------------------------
    # READ FROM SRAM
    # ----------------------------------------------------------
    res = mcp.read_fm_SRAM() # read the datetime saved in SRAM
    if res is None:
        res = ()
    
    if len(res) > 0:
        num_registers = res[0]
        if num_registers == 0:
            print(TAG+f"no datetime stamp data received")
            return
        
        rdl = "received datetime stamp length: {:d}".format(num_registers-1)
        yearday = mcp.yearday(res[1:])  # slice off byte 0 (= num_registers)
        isdst = -1
        
        if my_debug:
            print(TAG+f"{rdl}")
            print(TAG+f"received from SRAM: {res[1:]}")
            print(TAG+f"yearday {yearday}, isdst: {isdst} ")
        
        if num_registers == 8:
            _, year, month, date, weekday, hours, minutes, seconds  = res  # don't use nr_bytes again
        elif num_registers == 10:
            _, year, month, date, weekday, hours, minutes, seconds, is_12hr, is_PM = res # don't use nr_bytes again

        year += 2000

        # weekday += 1  # Correct for mcp weekday is 1 less than NTP or time.localtime weekday
        if state.dt_str_usa:
            dt1 = "{:s} {:02d} {:d}".format(
                state.month_dict[month],
                date,
                year)
        else:
            dt2 = "{:d}{:02d}/{:02d}".format(
                date,
                month,
                year)

        if is_12hr:
            ampm = "PM" if is_PM==1 else "AM"
            dt2 = "{:d}:{:02d}:{:02d} {}".format(
            hours,
            minutes,
            seconds,
            ampm)
        else:
            dt2 = "{:02d}:{:02d}:{:02d}".format(
            hours,
            minutes,
            seconds)
        
        wd = mcp.DOW[weekday]
        # print(TAG+f"weekday: {weekday}, mcp.DOW[weekday]: {wd}")

        dt3 = "wkday: {}".format(wd)

        dt4 = "yrday: {}".format(yearday)

        dt5 = "dst: {}".format(isdst)
        
        dt6 = "is_12hr: {}".format(is_12hr)
    
        dt7 = "is_PM: {}".format(is_PM)

        msg = ["Read from SRAM:", dt1, dt2, dt3, dt6, dt7, "Added: ", dt4, dt5]
        
        pr_msg(state, msg)
        
        state.SRAM_dt = (year, month, date, weekday, hours, minutes, seconds, is_12hr, is_PM) # skip byte 0 = num_regs
        
        if my_debug:
            sdt = state.SRAM_dt
            sdt_s = "state.SRAM_dt"
            print(TAG+f"{sdt_s}: {sdt}. type({sdt_s}): {type(sdt)}. len({sdt_s}): {len(sdt)}")


def pr_dt(state, short, choice):
    TAG = tag_adj(state, "pr_dt(): ")
    DT_DATE_L = 0
    DT_DATE_S = 1
    DT_TIME = 2
    DT_ALL  = 3

    if short is None:
        short = False

    if choice is None:
        choice2 = DT_ALL

    if choice == 0:
        choice2 = DT_DATE_L  # With weekday
    elif choice == 1:
        choice2 = DT_DATE_S  # Without weekday
    elif choice == 2:
        choice2 = DT_TIME
    elif choice == 3:
        choice2 = DT_ALL

    now = time.localtime()
    yy = now[state.yy]
    mm = now[state.mo]
    dd = now[state.dd]
    hh = now[state.hh]
    mi = now[state.mm]
    ss = now[state.ss]
    wd = now[state.wd]

    dow = mcp.DOW[wd+1]

    swd = dow[:3] if short else dow

    dt0 = "{:s}".format(swd)
    if my_debug:
        print(TAG+f"state.dt_str_usa: {state.dt_str_usa}")
    if state.dt_str_usa:
        if hh >= 12:
            hh -= 12
            ampm = "PM"
        else:
            ampm = "AM"

        if hh == 0:
            hh = 12

        #dt1 = "{:d}/{:02d}/{:02d}".format(mm, dd, yy)
        dt1 = "{:s} {:02d} {:02d}".format(state.month_dict[mm], dd, yy)
        dt2 = "{:d}:{:02d}:{:02d} {:s}".format(hh, mi, ss, ampm)
    else:
        dt1 = "{:d}-{:02d}-{:02d}".format(yy, mm, dd)
        dt2 = "{:02d}:{:02d}:{:02d}".format(hh, mi, ss)

    if choice2 == DT_ALL:
        ret = dt0 + " " + dt1 + ", "+ dt2
    if choice2 == DT_DATE_L:
        ret = dt0 + " " + dt1
    if choice2 == DT_DATE_S:
        ret = dt0 + " " + dt1
    if choice == DT_TIME:
        ret = dt2

    if my_debug:
        print(TAG+f"{ret}")

    return ret

"""
 * @brief In this version of CircuitPython one can only check if there is a WiFi connection
 * by checking if an IP address exists.
 * In the function do_connect() the global variable s_ip is set.
 *
 * @param sate class object
 *
 * @return boolean. True if exists an ip address. False if not.
"""
def wifi_is_connected(state):
    if state.ip is not None:
        my_ip = state.ip
    else:
        my_ip = wifi.radio.ipv4_address

    if my_ip is None:
        return False
    else:
        my_s__ip = str(my_ip)
        return True if my_s__ip is not None and len(my_s__ip) > 0 and my_s__ip != '0.0.0.0' else False

def clr_scrn():
    for i in range(9):
        print()


# Make preparations to enable alarm interrups from RTC shield
# through the MFP (IO4) of the RTC shield.
def prepare_alm_int(state):

    # See the MCP7940N datasheet, paragraph 5.5, DS20005010H-page 25
    # See the Dual Alarm Output Truth Table (Table 5-10) on page 27
    mcp._clr_SQWEN_bit()  # Clear the Square Wave Enable bit
    for _ in range(2):
        if not mcp.alarm_is_enabled(_+1):
            mcp.alarm_enable(_+1, True)  # Enable the alarm (1 or 2)


def set_alarm(state, alarm_nr = 1, mins_fm_now=10):
    TAG = tag_adj(state, "set_alarm(): ")

    if not alarm_nr in [1, 2]:
        return

    if mins_fm_now > 60:  # not more dan 60 minutes from now
        mins_fm_now = 10

    alarm1en = mcp.alarm_is_enabled(1)
    alarm2en = mcp.alarm_is_enabled(2)

    t1 = time.time()  # get seconds since epoch
    dt = time.localtime(t1+(mins_fm_now*60)) # convert mins_fm_now to seconds

    month = dt.tm_mon
    date = dt.tm_mday
    hours = dt.tm_hour
    minutes = dt.tm_min
    seconds = dt.tm_sec
    weekday = dt.tm_wday + 1
    dow = mcp.DOW[weekday]
    # print(TAG+f"weekday: {weekday}")

    t = month, date, hours, minutes, seconds, weekday

    if alarm1en and alarm_nr == 1:
        if my_debug:
            print(TAG+f"setting alarm1 for: {t[:5]}, {dow}")
        mcp.alarm1 = t  # Set alarm1
        t_ck = mcp.alarm1[:6]  # check result
        if my_debug:
            print(TAG+f"check: alarm1 is set for: {t_ck}")
        state.alarm1 = t_ck
        state.alarm1_set = True
        # IMPORTANT NOTE:
        # ===============
        # I experienced that if mcp.alarm1 (or mcp.alarm2) is called earlier, the setting of the ALMPOL bit is reset,
        # that is why we set the ALMPOL bit again (below)
        # ===============
        mcp._set_ALMPOL_bit(1) # Set ALMPOL bit of Alarm1 (so the MFP follows the ALM1IF)
        mcp._clr_ALMxIF_bit(1)     # Clear the interrupt of alarm1
        mcp._set_ALMxMSK_bits(1,1) # Set the alarm1 mask bits for a minutes match

    if alarm2en and alarm_nr == 2:
        if my_debug:
            print(TAG+f"setting alarm2 for: {t[:5]}, {dow}")
        mcp.alarm2 = t  # Set alarm2
        t_ck = mcp.alarm2[:6]  # check result
        if my_debug:
            print(TAG+f"check: alarm2 is set for: {t_ck}")
        state.alarm2 = t_ck
        state.alarm2_set = True
        mcp._set_ALMPOL_bit(2) # Set ALMPOL bit of alarm1 (so the MFP follows the ALM1IF)
        mcp._clr_ALMxIF_bit(2)     # Clear the interrupt of alarm1
        mcp._set_ALMxMSK_bits(2,1) # Set the alarm1 mask bits for a minutes match

def clr_alarm(state, alarm_nr=None):
    TAG = tag_adj(state, "clr_alarm(): ")
    if alarm_nr is None:
        return

    eal = (0,)*6

    if alarm_nr in [1, 2]:
        if alarm_nr == 1:
            mcp.alarm1 = eal  # clear alarm1 datetime stamp
            mcp._clr_ALMxIF_bit(1) # clear alarm1 Interrupt Flag bit
            state.alarm1_set = False
            state.alarm1 = eal
            if my_debug:
                print(TAG+f"state.alarm1: {state.alarm1[:6]}")
            ck = mcp.alarm1[:6]
        elif alarm_nr == 2:
            mcp.alarm2 = eal    # clear alarm2 datetime stamp
            mcp._clr_ALMxIF_bit(2) # clear alarm2 Interrupt Flag bit
            state.alarm2_set = False
            state.alarm2 = eal
            if my_debug:
                print(TAG+f"state.alarm2: {state.alarm2[:6]}")
            ck = mcp.alarm2[:6]
        if my_debug:
            print(TAG+f"alarm{alarm_nr}, check: {ck}")

def pol_alarm_int(state):
    TAG = tag_adj(state, "pol_alarm_int(): ")
    t_ck = None
    alarm1en = False
    alarm2en = False
    alm1msk_bits = None
    alm2msk_bits = None

    for _ in range(2):
        if _ == 0:
            alarm1en = True if mcp.alarm_is_enabled(1) else False
        if _ == 1:
            alarm2en = True if mcp.alarm_is_enabled(2) else False

    if alarm1en:
        if my_debug:
            print(TAG+"alarm1 is enabled")
        #t_ck = mcp.alarm1[:6]  # check result
        t_ck = state.alarm1[:6]
        if my_debug:
            print(TAG+f"alarm1 is set for: {t_ck}")
        state.alarm1_int = True if mcp._read_ALMxIF_bit(1) else False
        if state.alarm1_int:
            alm1if_bit = mcp._read_ALMxIF_bit(1)
            if my_debug:
                print(TAG+"we have an interrupt from alarm1")
                print(TAG+"alarm1 IF bit: {:b}".format(alm1if_bit))
                alm1msk_bits = mcp._read_ALMxMSK_bits(1)
                show_alm_match_type(alm1msk_bits)
            ck_rtc_mfp_int(state)

    if alarm2en:
        if my_debug:
            print(TAG+"alarm2 is enabled")
        #t_ck = mcp.alarm2[:6]  # check result
        t_ck = state.alarm2[:6]
        if my_debug:
            print(TAG+f"alarm2 is set for: {t_ck}")
        state.alarm2_int = True if mcp._read_ALMxIF_bit(2) else False
        if state.alarm2_int:
            alm2if_bit = mcp._read_ALMxIF_bit(2)
            if my_debug:
                print(TAG+"we have an interrupt from alarm2")
                print(TAG+"alarm2 IF bit: {:b}".format(alm2if_bit))
                alm2msk_bits = mcp._read_ALMxMSK_bits(2)
                show_alm_match_type(alm2msk_bits)
            ck_rtc_mfp_int(state)

# check the RTC interrupt line (RTC io4 to ProS3 io33)
def ck_rtc_mfp_int(state):
    TAG = tag_adj(state, "ck_rtc_mfp_int(): ")
    v = rtc_mfp_int.value
    s = "High" if v else "Low "
    if my_debug:
        print(TAG+f"rtc interrupt line value: {s}")
    if v:
        state.mfp = v

# Called from function: pol_alarm_int(state)
def show_alm_match_type(msk=None):
    TAG = tag_adj(state, "show_alm_match_type(): ")
    if msk is None:
        return
    if msk >= 0 and msk <= 7:
        print(TAG+f"match type: {mcp._match_lst[msk]}")


def show_mfp_output_mode_status(stete):
    if state.loop_nr < 3:
        return
    print()
    print("MCP7940 MFP output mode:")
    s1 = "+--------+--------+--------+--------------------------+"
    s2 = "| SQWEN  | ALM0EN | ALM1EN |          Mode            |"
    aio = "Alarm Interruput output "
    sqwen =  mcp._read_SQWEN_bit()
    alm1en = mcp.alarm_is_enabled(1)
    alm2en = mcp.alarm_is_enabled(2)

    if not sqwen:
        if not alm1en:
            if not alm2en:  # 0 0 0
                mode = "Gen purpose output      "
            elif alm2en:    # 0 0 1
                mode = aio
        elif alm1en:
            if not alm2en:  # 0 1 0
                mode = aio
            elif alm2en:    # 0 1 1
                mode = aio
    elif sqwen:             # 1 x x
        mode = "Square Wave Clock Output"
    else:
        mode = "Unknwon                 "

    s3= "|   {:d}    |   {:d}    |   {:d}    | {:s} |".format(sqwen, alm1en, alm2en, mode)
    print(s1)
    print(s2)
    print(s1)
    print(s3)
    print(s1)
    print("See: MCP7940N datasheet DS20005010H-page 25")
    print()


def show_alarm_output_truth_table(state, alarm_nr=None):
    if alarm_nr is None:
        return
    if not alarm_nr in [1, 2]:
        return

    s_ALMxIF = "ALM"+str(alarm_nr)+"IF"

    print()
    print(f"Single alarm output truth table for alarm{alarm_nr}:")
    s1 = "+--------+---------+-------+----------------------------------+"
    s2 = "| ALMPOL |  {:6s} |  MFP  |            Match type            |".format(s_ALMxIF)
    alarm_pol = mcp._read_ALMPOL_bit(alarm_nr) # Read alarm1 or alarm2 ALMPOL bit
    alarm_IF = mcp._read_ALMxIF_bit(alarm_nr) # Read alarm1 or alarm2 interrupt flag
    msk = mcp._read_ALMxMSK_bits(alarm_nr) # Read ALMxMSK bits of alarm1 or alarm2
    msk_match = state._match_lst_long[msk] # get the match long text equivalent
    mfp = rtc_mfp_int.value # get the RTC shield MFP interrupt line state

    if my_debug:
        print(f"show_alarm_output_truth_table(): alarm_pol for alarm{alarm_nr}: {alarm_pol}")

    notes1 = "mask bits: \'b{:03b}\' type: {:8s}".format(msk, msk_match)
    s3= "|   {:d}    |    {:d}    |   {:d}   | {:24s} |".format(alarm_pol, alarm_IF, mfp, notes1)
    print(s1)
    print(s2)
    print(s1)
    print(s3)
    print(s1)
    print("See: MCP7940N datasheet DS20005010H-page 27")
    print()

def get_ampm(hh):
    ret = " ?"
    if isinstance(hh, int):
        if mcp._is_12hr: # was: if state.dt_str_usa:
            ret = "PM" if mcp._is_PM(hh) == 1 else "AM"
        else:
            ret = str(hh)
    return ret

def show_alm_int_status(state):
    TAG = tag_adj(state, "show_alm_int_status(): ")
    match1 = ""
    match2 = ""
    s_sec = "AM/PM" if state.dt_str_usa else "SECOND"
    s1 = "+-------------+----------+-------+-----+------+--------+--------+---------+---------------------+--------------------+"
    s2 = "|  ALARM  Nr  | ENABLED? | MONTH | DAY | HOUR | MINUTE | {:6s} | WEEKDAY | INTERRUPT OCCURRED? | NOTES:             |".format(s_sec)
    
    ae1=mcp.alarm_is_enabled(1)
    ae2=mcp.alarm_is_enabled(2)
    is_12hr = mcp._is_12hr
    
    if ae1:
        alarm1en = "Yes" if ae1 else "No  "
        ts1 = state.alarm1[:6]  # slice off yearday and isdst
        if my_debug:
            print(TAG+f"alarm1 set for: {ts1}")
            
        mo1, dd1, hh1, mi1, ss1, wd1 = ts1
            
        ss1 = get_ampm(hh1)

        if is_12hr:
            if hh1 > 12:
                hh1 -= 12
            
        match1 = mcp._match_lst[mcp._read_ALMxMSK_bits(1)]
        if match1 == "mm" and not state.dt_str_usa:
            ss1 = None
    if ae2:
        alarm2en = "Yes" if ae2 else "No  "
        ts2 = state.alarm2[:6]  # slice off yearday and isdst
        if my_debug:
            print(TAG+f"alarm2 set for: {ts2}")
            
        mo2, dd2, hh2, mi2, ss2, wd2 = ts2
        
        ss2 = get_ampm(hh2)

        if is_12hr:
            if hh2 > 12:
                hh2 -= 12
        
        match2 = mcp._match_lst[mcp._read_ALMxMSK_bits(2)]
        if match2 == "mm" and not state.dt_str_usa:
            ss2 = None

    tm_current = mcp.time # Get current datetime stamp from the External UM MCP7940 RTC shield
    if my_debug:
        print(TAG+f"mcp.time: {tm_current}")

    num_registers = len(tm_current)
    if my_debug:
        print(TAG+f"num_registers: {num_registers}")
    
    if num_registers == 7:
        _, c_mo, c_dd, c_hh, c_mi, c_ss, c_wd = tm_current # Discard year
    elif num_registers == 9:
        _, c_mo, c_dd, c_hh, c_mi, c_ss, c_wd, _, _ = tm_current  # Discard year, yearday and isdst
    elif num_registers == 11:
        _, c_mo, c_dd, c_hh, c_mi, c_ss, c_wd, _, _, _, _ = tm_current  # Discard year, yearday and isdst, is_12hr, is_PM
    
    c_ss = get_ampm(c_hh)

    if is_12hr:
            if c_hh > 12:
                c_hh -= 12
    
    v = "Yes " if state.mfp else "No  "

    s3 = "|      {:s}      |    {:s}     |  {:2d}   |  {:2d} |  {:2d}  |   {:2d}   |   {:2s}   |   {:s}   | {:s}                   | {:18s} |". \
        format("X","X", c_mo, c_dd, c_hh, c_mi, c_ss, mcp.DOW[c_wd][:3],"X","CURRENT DATETIME")

    if ae1:
        if ss1 is None: # We don't display seconds if we do an alarm match on minutes
            s4 = "|      {:d}      |   {:s}    |  {:2d}   |  {:2d} |  {:2d}  |   {:2d}   |   {:2s}   |   {:s}   | {:3s}                | {:18s} |". \
            format(1, alarm1en, mo1, dd1, hh1, mi1, " X", mcp.DOW[wd1][:3], v, "ALARM1 SET FOR")
        else:
            s4 = "|      {:d}      |   {:s}    |  {:2d}   |  {:2d} |  {:2d}  |   {:2d}   |   {:2s}   |   {:s}   | {:3s}                | {:18s} |". \
            format(1, alarm1en, mo1, dd1, hh1, mi1, ss1, mcp.DOW[wd1][:3], v, "ALARM1 SET FOR")

    if ae2:
        if ss2 is None: # We don't display seconds if we do an alarm match on minutes
            s5 = "|      {:d}      |   {:s}    |  {:2d}   |  {:2d} |  {:2d}  |   {:2d}   |   {:2s}   |   {:s}   | {:3s}                | {:18s} |". \
            format(2, alarm2en, mo2, dd2, hh2, mi2, " X", mcp.DOW[wd2][:3], v, "ALARM2 SET FOR")
        else:
            s5 = "|      {:d}      |   {:s}    |  {:2d}   |  {:2d} |  {:2d}  |   {:2d}   |   {:2s}   |   {:s}   | {:3s}                | {:18s} |". \
            format(2, alarm2en, mo2, dd2, hh2, mi2, ss2, mcp.DOW[wd2][:3], v, "ALARM2 SET FOR")

    nxt_int = mi1 if ae1 else mi2 if ae2 else -1 # Next interrupt expected at minute:
    
    print()
    print("Alarm interrupt status:")
    if match1 == "mm" or match2 == "mm" and nxt_int != -1:
        print(f"Expect next alarm at minute: {nxt_int}")
    print(s1)
    print(s2)
    print(s1)
    print(s3)
    print(s1)
    if ae1:
        print(s4)  # Print only enabled alarm
    print(s1)
    if ae2:
        print(s5) # idem
        print(s1)


def alarm_blink(state):
    if state.loop_nr < 3:
        return
    TAG = tag_adj(state, "alarm_blink(): ")
    my_RED = (0,   200,   0)
    my_GRN = (200,   0,   0)
    my_BLU = (0,     0, 200)
    my_BLK = (0,     0,   0)

    current_color = state.curr_color_set
    if state.use_neopixel:
        for _ in range(5):
            if my_debug:
                print(TAG+f"blinking: RED")
            r,g,b = my_RED # Pros3.rgb_color_wheel( state.RED )
            pixels[0] = ( r, g, b, state.neopixel_brightness)
            pixels.write()
            time.sleep(1)
            if my_debug:
                print(TAG+f"blinking: BLUE")
            r,g,b = my_BLU # Pros3.rgb_color_wheel( state.BLK )
            pixels[0] = ( r, g, b, state.neopixel_brightness)
            pixels.write()
            time.sleep(1)
        # restore last color:
        if my_debug:
            print(TAG+f"resetting color to: {current_color}")
        r,g,b = pros3.rgb_color_wheel( current_color )
        pixels[0] = ( r, g, b, state.neopixel_brightness)
        pixels.write()


def get_dt(state):
    dt = None
    ret = ""
    if is_EXT_RTC():
        if state.lStart:
            while True:
                dt = mcp.time
                if dt[state.ss] == 0: # align for 0 seconds (only at startup)
                    break
        else:
            dt = mcp.time
        yrday = mcp.yearday(dt)
        ret = "{} {:4d}-{:02d}-{:02d} {:02d}:{:02d}:{:02d}. Day of year: {:>3d}". \
            format(mcp.weekday_S(),dt[state.yy], dt[state.mo], dt[state.dd], dt[state.hh], dt[state.mm], dt[state.ss], yrday)

    return ret


"""
 * @brief function performs a ping test with google.com
 *
 * @param state class object
 *
 * @return None
"""
def ping_test(state):
    global pool
    TAG = tag_adj(state, "ping_test(): ")
    #state.ip = wifi.radio.ipv4_address
    if state.ip is not None and state.ip != 0:
        # state.s__ip = str(state.ip)
        ret = False

    if my_debug:
        print(TAG+f"state.s__ip= \'{state.s__ip}\'")

    if use_ping:
        try:
            if not pool:
                pool = socketpool.SocketPool(wifi.radio)
            # print(TAG+f"pool= {pool}, type(pool)= {type(pool)}")
            addr_idx = 1
            addr_dict = {0:'LAN gateway', 1:'google.com'}
            info = pool.getaddrinfo(addr_dict[addr_idx], 80)
            # print(TAG+f"info= {info}")
            addr = info[0][4][0]
            print(TAG+f"Resolved google address: \'{addr}\'")
            ipv4 = ipaddress.ip_address(addr)
            if ipv4 is not None:
                ret = True
                for _ in range(10):
                    result = wifi.radio.ping(ipv4)
                    if result:
                        print(TAG+"Ping google.com [%s]: %.0f ms" % (addr, result*1000))
                        break
                    else:
                        print(TAG+"Ping no response")
        except OSError as e:
            print(TAG+f"Error: {e}")
            raise
    return ret

"""
 * @brief function that establish WiFi connection
 * Function tries to establish a WiFi connection with the given Access Point
 * If a WiFi connection has been established, function will:
 * sets the global variables: 'ip' and 's_ip' ( the latter used by function wifi_is_connected() )
 *
 * @param state class object
 *
 * @return None
"""
def do_connect(state):
    TAG = tag_adj(state, "do_connect(): ")

    # Get env variables from file settings.toml
    ssid = os.getenv("CIRCUITPY_WIFI_SSID")
    pw = os.getenv("CIRCUITPY_WIFI_PASSWORD")
    state.ssid = ssid
    
    try:
        wifi.radio.connect(ssid=ssid, password=pw)
    except ConnectionError as e:
        print(TAG+f"WiFi connection Error: \'{e}\'")
    except Exception as e:
        print(TAG+f"Error: {dir(e)}")

    state.ip = wifi.radio.ipv4_address

    if state.ip:
        state.s__ip = str(state.ip)


"""
 * @brief function print hostname to REPL
 *
 * @param state class object
 *
 * @return None
"""
def hostname(state):
    TAG = tag_adj(state, "hostname(): ")
    print(TAG+f"wifi.radio.hostname= \'{wifi.radio.hostname}\'")

"""
 * @brief function prints mac address to REPL
 *
 * @param state class object
 *
 * @return None
"""
def mac(state):
    TAG = tag_adj(state, "mac(): ")
    mac = wifi.radio.mac_address
    le = len(mac)
    if le > 0:
        print(TAG+"wifi.radio.mac_address= ", end='')
        for _ in range(le):
            if _ < le-1:
                print("{:x}:".format(mac[_]), end='')
            else:

                print("{:x}".format(mac[_]), end='')
        print('', end='\n')

def tag_adj(state,t):
    global tag_le_max

    if use_TAG:
        le = 0
        spc = 0
        ret = t

        if isinstance(t, str):
            le = len(t)
        if le >0:
            spc = state.tag_le_max - le
            #print(f"spc= {spc}")
            ret = ""+t+"{0:>{1:d}s}".format("",spc)
            #print(f"s=\'{s}\'")
        return ret
    return ""

def pr_msg(state, msg_lst=None):
    # TAG = tag_adj(state, "pr_msg(): ")
    if msg_lst is None:
        msg_lst = ["pr_msg", "test message", "param rcvd:", "None"]
    le = len(msg_lst)
    max_lines = 9
    nr_lines = max_lines if le >= max_lines else le
    clr_scrn()
    if le > 0:
        for i in range(nr_lines):
            print(f"{msg_lst[i]}")
        if le < max_lines:
            for j in range((max_lines-le)-1):
                print()
        time.sleep(3)

def say_hello(header):
    # Say hello
    if header:
        if my_debug:
            print("\nHello from Pros3!")
            print("------------------\n")

            # Show available memory
            print("Memory Info - gc.mem_free()")
            print("---------------------------")
            print("{} Bytes\n".format(gc.mem_free()))

        flash = os.statvfs('/')
        flash_size = flash[0] * flash[2]
        flash_free = flash[0] * flash[3]
        # Show flash size
        if my_debug:
            print("Flash - os.statvfs('/')")
            print("---------------------------")
            print("Size: {} Bytes\nFree: {} Bytes\n".format(flash_size, flash_free))

            print("Pixel Time!\n")

    # Create a colour wheel index int
    color_index = 0

    # Turn on the power to the NeoPixel
    # Pros3.set_pixel_power(True)
    # Pros3.set_ldo2_power(True)  <<<<=== Is set in setup()
    # Rainbow colours on the NeoPixel

    while True:
        # Get the R,G,B values of the next colour
        r,g,b = pros3.rgb_color_wheel( color_index )
        # Set the colour on the NeoPixel
        pixels[0] = ( r, g, b, 0.5)
        # Increase the wheel index
        color_index += 1
        if color_index > 255:
            if my_debug:
                print("say_hello(): leaving color loop")
            break

        # Sleep for 15ms so the colour cycle isn't too fast
        time.sleep(0.015)

"""
 * @brief this setup function, among various settings specific to the Unexpected Maker ProS3 board,
 * sets the WiFi.AuthMode. Then the function calls the function do_connect()
 * to establish a WiFi connection.
 * It checks and sets various settings of the connected external Unexpected Makrer TinyPico RTC Shield (MCP7940)
 * This function is called by main(). 
 *
 * @param: state class object
 *
 * @return None
"""
def setup(state):
    global pixels, mRTC, SRAM_dt, SYS_dt
    TAG = tag_adj(state, "setup(): ")
    # Create a colour wheel index int
    color_index = 0

    print(TAG+f"board: \'{state.board_id}\'")

    if id == 'unexpectedmaker_pros3':
        try:
            # Turn on the power to the NeoPixel
            pros3.set_ldo2_power(True)
            
            if state.use_neopixel:
                pixels = neopixel.NeoPixel(board.NEOPIXEL, 1)
                #for i in range(len(pixels)):
                #    pixels[i] = RED
                neopixel.NeoPixel.brightness = state.neopixel_brightness
                r,g,b = pros3.rgb_color_wheel( state.BLK )
                pixels[0] = ( r, g, b, state.neopixel_brightness)
                pixels.write()
        except ValueError:
            pass    
        
    wifi.AuthMode.WPA2   # set only once
    
    do_connect(state)
    
    if wifi_is_connected(state):
        print(TAG+f"WiFi connected to: {state.ssid}. IP: {state.s__ip}")
    
    if is_NTP(state):
        if not my_debug:
            print(TAG+"We have NTP")
    if is_INT_RTC():
        if not my_debug:
            print(TAG+"We have an internal RTC")
        if state.SYS_RTC_is_set:
            if my_debug:
                print(TAG+"and the internal RTC is set from an NTP server")
    if is_EXT_RTC:
        if not my_debug:
            print(TAG+"We have an external RTC")
        if state.EXT_RTC_is_set:
            if my_debug:
                print(TAG+"and the external RTC is set from an NTP server")

    s_mcp = "MCP7940"
    s_pf1 = s_mcp+" Power failed"
    s_en1 = s_mcp+" RTC battery "
    s_en2 = s_en1+"is now enabled? "
    s_rtc = "RTC datetime year "

    MCP7940_is_started = False
    
    if my_debug:
        print(TAG+f"Checking if {s_mcp} has been started.")
    if not mcp.is_started():
        if not my_debug:
            print(TAG+f"{s_mcp} not started yet...")
        mcp.start()
        if mcp.is_started():
            MCP7940_is_started = True
            if not my_debug:
                print(TAG+f"{s_mcp} now started")
        else:
            print(TAG+f"failed to start {s_mcp}")
    else:
        MCP7940_is_started = True
        if my_debug:
            print(TAG+f"{s_mcp}is running")
            
    if MCP7940_is_started:

        if not my_debug:
            print(TAG+f"Checking for {s_mcp} power failure.")
        s_pf_yn = "Yes" if mcp.has_power_failed() else "No"
        if my_debug:
            print(TAG+f"{s_pf1}? {s_pf_yn}") # Check if the power failed bit is set
        if s_pf_yn == "Yes":
            mcp.clr_pwr_fail_bit()
            if not mcp.has_power_failed():
                if my_debug:
                    print(TAG+"{s_pf1} bit cleared")

            pwrud_dt = mcp.pwr_updn_dt(False)
            if not my_debug:
                print(TAG+f"{s_mcp} power down timestamp: {pwrud_dt}")
            pwrud_dt = mcp.pwr_updn_dt(True)
            if not my_debug:
                print(TAG+f"{s_mcp} power up timestamp: {pwrud_dt}")
    
    if my_debug:
        print(TAG+f"Checking if {s_en1} has been enabled.")
    s_bbe_yn = "Yes" if mcp.is_battery_backup_enabled() else "No"
    if s_bbe_yn == "No":
        if my_debug:
            print(TAG+f"{s_en1}is not enabled. Going to enable")
        mcp.battery_backup_enable(True)  # Enable backup battery
        # Check backup battery status again:
        s_bbe_yn = "Yes" if mcp.is_battery_backup_enabled() else "No"
        if my_debug:
            print(TAG+f"{s_en2}{s_bbe_yn}")
    else:
        if my_debug:
            print(TAG+f"{s_en2}{s_bbe_yn}")

    if state.set_SYS_RTC :
        if my_debug:
            print(TAG+"Going to set internal (SYS) RTC")
        set_INT_RTC(state)

    if state.set_EXT_RTC:
        set_EXT_RTC(state)

    gc.collect()

    if not my_debug:
        print()

    if my_debug:
        if isinstance(state.SRAM_dt, tuple):
            le = len(state.SRAM_dt)
            if le > 0:
                if state.SYS_dt is not None:
                    print(TAG+s_mcp+" Internal RTC set to: {}, \ntype: {}".format(state.SYS_dt, type(state.SYS_dt)))
                print(TAG+f"Contents of {s_mcp} External RTC\'s SRAM: {state.SRAM_dt}")
                print(TAG+f"{s_mcp}_{s_rtc}read from SRAM = {state.SRAM_dt[state.yy]}")
            else:
                print(TAG+f"length of tuple state.SRAM_dt = {le}")
        else:
            print(TAG+f"Expected type tuple but got type: {type(state.SRAM_dt)}")

    if not my_debug:
        print(TAG+"start setting up MCP7940")

    mcp._clr_SQWEN_bit()        # Clear the Square Wave Enable bit
    mcp._set_ALMPOL_bit(1)      # Set ALMPOL bit of Alarm1 (so the MFP follows the ALM1IF)
    mcp._clr_ALMxIF_bit(1)      # Clear the interrupt of alarm1
    mcp._set_ALMxMSK_bits(1,1)  # Set the alarm1 mask bits for a minutes match
    state.alarm1_int = False
    mcp.alarm_enable(1, True)   # Enable alarm1
    if not my_debug:
        print(TAG+"...")
    mcp._set_ALMPOL_bit(2)      # ALMPOL bit of Alarm2 (so the MFP follows the ALM2IF)
    mcp._clr_ALMxIF_bit(2)      # Clear the interrupt of alarm2
    mcp._set_ALMxMSK_bits(2,1)  # Set the alarm3 mask bits for a minutes match
    state.alarm2_int = False
    mcp.alarm_enable(2, False)  # Disable alarm2

    state.mfp = rtc_mfp_int.value

    if not my_debug:
        print(TAG+"finished setting up MCP7940")
    # prepare_alm_int(state)  # Prepare for alarm interrupt polling


"""
 * @brief this is the main function that controls the flow of the
 * execution of this CircuitPython script.
 * The user can interrupt the running process
 * by typing the key-combination: CTRL+C
 *
 * @param None
 *
 * @return None
"""
def main():
    TAG = tag_adj(state, "main(): ")
    if my_debug:
        print("Waiting another 5 seconds for mu-editor etc. getting ready")
    time.sleep(5)
    setup(state)
    if my_debug:
        print("Entering loop")
    discon_msg_shown = False

    ping_done = False
    state.grn_set = False
    state.red_set = False
    count_tried = 0
    count_tried_max = 10
    state.lStart = True
    state.loop_nr = 0
    state.alarm1_set = False
    alarm_start = True
    sram_demo_cnt = 1
    sram_demo_max_cnt = 2
    while True:
        try:
            state.loop_nr += 1
            if state.loop_nr >= 100:
                state.loop_nr = 1
            if not my_debug:
                print()
                print(TAG+f"loop nr: {state.loop_nr}")
            if not wifi_is_connected(state):
                if not my_debug:
                    print(TAG+"going to establish a WiFi connection...")
                do_connect(state)
            if wifi_is_connected(state):  # Check again.
                if state.board_id == 'unexpectedmaker_Pros3':
                    if state.use_neopixel and not state.curr_color_set == state.GRN:
                        state.curr_color_set = state.GRN
                        r,g,b = pros3.rgb_color_wheel( state.GRN )
                        pixels[0] = ( r, g, b, state.neopixel_brightness)
                        pixels.write()

                if not my_debug:
                    if not ping_done:
                        ssid = os.getenv("CIRCUITPY_WIFI_SSID")
                        print(TAG+f"connected to \"{ssid}\"!")
                        print(TAG+f"IP address is {str(wifi.radio.ipv4_address)}")
                        hostname(state)
                        mac(state)
                        ping_done = ping_test(state)
                        if not ping_done:
                            count_tried += 1
                            if count_tried >= count_tried_max:
                                print(TAG+f"ping test failed {count_tried} times. Skipping this test.")
                                ping_done = True
            else:
                if not discon_msg_shown:
                    discon_msg_shown = True
                    print(TAG+"WiFi disconnected")
                    if state.board_id  == 'unexpectedmaker_Pros3':
                        if neopixel  and not state.curr_color_set == state.RED:
                            state.curr_color_set = state.RED
                            r,g,b = pros3.rgb_color_wheel( state.RED )
                            pixels[0] = ( r, g, b, state.neopixel_brightness)
                            pixels.write()
            time.sleep(2)
            if state.lStart:
                state.lStart = False
                msg = ['NTP date:', pr_dt(state, True, 0), pr_dt(state, True, 2)]
                pr_msg(state, msg)
                say_hello(True)
                state.lStart = False
                clr_scrn()
            else:
                #sys.exit()
                say_hello(False)  # Was: False
                if sram_demo_cnt <=  sram_demo_max_cnt:
                    print(TAG+f"Demo nr {sram_demo_cnt} of {sram_demo_max_cnt}: save to and then read from the RTC shield\'s SRAM")
                    upd_SRAM(state)
                    if sram_demo_cnt <  sram_demo_max_cnt+1:
                        sram_demo_cnt += 1
                # ------------------------------------------------------------------------------------------------
                if alarm_start:
                    alarm_nr = 1
                    clr_alarm(state, alarm_nr)
                    state.alarm1_set = False
                    mcp._set_ALMxMSK_bits(alarm_nr, 1)  # Set Alarm1 Mask bits to have Alarm Minutes match
                    if not state.alarm1_set:
                        set_alarm(state, alarm_nr, 2) # Set alarm1 for time now + 2 minutes
                        state.alarm1_set = True
                        alarm_start = False
                #pol_alarm_int(state)  # Check alarm interrupt
                ck_rtc_mfp_int(state)
                show_mfp_output_mode_status(state)
                if state.loop_nr >= 3:  # Only perform this
                    show_alarm_output_truth_table(state, 1) # Show alarm output truth table for alarm1
                    show_alm_int_status(state)
                pol_alarm_int(state)  # Check alarm interrupt
                if state.alarm1_int:
                    interrupt_handler(state)
                # pol_alarm_int(state)  # Check alarm interrupt
                # ------------------------------------------------------------------------------------------------
        except KeyboardInterrupt:
            wifi.radio.stop_station()
            r,g,b = pros3.rgb_color_wheel( state.BLK )
            state.curr_color_set == state.BLK
            pixels[0] = ( r, g, b, state.neopixel_brightness)
            pixels.write()
            print("KeyboardInterrupt. Exiting...")
            sys.exit()
        except Exception as e:
            print("Error", e)
            raise

if __name__ == '__main__':
    main()

