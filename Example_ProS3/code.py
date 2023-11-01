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
    Depending of the State Class boolean variables: 'state.set_SYS_RTC' and 'state.set_EXT_RTC', the internal and/or the external RTC(s)
    is/are set.

    The external MCP7940 RTC timekeeping set values will be read frequently.
    For test this script and the library script mcp7940.py contain function to write and read datetime stamps
    to and from the MCP7940 user space in its SRAM.
    The MCP7940 RTC needs only to be set when the RTC has been without power or not has been set before.
    When you need more (debug) output to the REPL, set the global variable 'my_debug' to True.

    If one wants to use dst then set the value of key 'Use_dst' in file config.json to 1.
    A dst.py file has been added. Its contents will be read at startup.
    Currently dst dictionary in the dst.py file contains dst values for timezone 'Europe/Portugal'. You can change these value for your timezone.
    The State Class attribute state.dst will be set also according to the value of config.json UTC_OFFSET.
    A file 'USA_NY_dst.py' has been added containing a dst dictionary containing EST/EDT EPOCH values for the period 2022-2031.
    If one wants to use the 'USA_NY_dst.py' file I suggest: 1) rename file 'dst.py' to 'dst_original.py'; 2) make a copy of file 
    'USA_NY_dst.py' and rename it to 'dst.py'.
    In the folder /docs/ProS3 is an Excel file named: 'USA_NY_2022-2031_DST_EPOCH_values.xlsx'.
    This Excel file I filled with dates, times and EPOCH values for USA, state NY.
    The EPOCH values from this Excel file I then copied to create the file 'USA_NY_dst.py'.
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
import json
from dst import dst
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
ntp = None  # See setup

state = None

"""function to save the config dict to the JSON file"""
def save_config(state):
    TAG = "save_config():"+" "*12
    ret = 0
    try:
        with open("config.json", "w") as f:
            json.dump(config, f)
        ret = 1
    except OSError as e:
        print(TAG+f"Error: {e}")
        return ret
    return ret

config = None

# load the config file from flash
with open("config.json") as f:
    config = json.load(f)
if my_debug:
    print(f"global(): config: {config}")

class State:
    def __init__(self, saved_state_json=None):
        self.board_id = None
        self.wlan = None
        self.lStart = True
        self.loop_nr = -1
        self.max_loop_nr = 30
        self.tag_le_max = 26  # see tag_adj()
        self.use_clr_SRAM = True
        self.set_SYS_RTC = True
        self.NTP_dt_is_set = False
        self.SYS_RTC_is_set = False
        self.set_EXT_RTC = True # Set to True to update the MCP7940 RTC datetime values (and set the values of dt_dict below)
        self.EXT_RTC_is_set = False
        self.save_dt_fm_int_rtc = False  # when save_to_SRAM, save datetime from INTernal RTC (True) or EXTernal RTC (False)
        self.ntp_last_sync_dt = 0
        self.dt_str_usa = True
        self.use_dst = False
        self.dst = 0
        self.MCP_dt = None
        self.ntp_server_idx = 0 # see ntp_servers_dict
        self.NTP_dt = None
        self.SYS_dt = None # time.localtime()
        self.SRAM_dt = None  #see setup()
        self.ip = None
        self.s__ip = None
        self.mac = None
        self.use_neopixel = True
        self.neopixel_brightness = None
        self.neopixel_dict = {
            "BLK": (0, 0, 0),
            "RED": (200, 0, 0),
            "GRN": (0, 200, 0),
            "BLU": (0, 0, 200)}
        self.neopixel_rev_dict = {
            (0, 0, 0)   : "BLK",
            (200, 0, 0) : "RED",
            (0, 200, 0) : "GRN",
            (0, 0, 200) : "BLU"}
        self.curr_color_set = None
        # See: https://docs.python.org/3/library/time.html#time.struct_time
        self.tm_year = 0
        self.tm_mon = 1 # range [1, 12]
        self.tm_mday = 2 # range [1, 31]
        self.tm_hour = 3 # range [0, 23]
        self.tm_min = 4 # range [0, 59]
        self.tm_sec = 5 # range [0, 61] in strftime() description
        self.tm_wday = 6 # range 8[0, 6] Monday = 0
        self.tm_yday = 7 # range [0, 366]
        self.tm_isdst = 8 # 0, 1 or -1
        self.COUNTRY = None
        self.STATE = None
        self.tm_tmzone = None # was: 'Europe/Lisbon' # abbreviation of timezone name
        #tm_tmzone_dst = "WET0WEST,M3.5.0/1,M10.5.0"
        self.UTC_OFFSET = None
        self.dt_dict = {
            self.tm_year: 2023,
            self.tm_mon: 10,
            self.tm_mday: 4,
            self.tm_hour: 16,
            self.tm_min: 10,
            self.tm_sec: 0,
            self.tm_wday: 2,
            self.tm_yday: 277,
            self.tm_isdst: -1}
        self.alarm1 = ()
        self.alarm2 = ()
        self.alarm1_int = False
        self.alarm2_int = False
        self.alarm1_set = False
        self.alarm2_set = False
        self.mfp = False
        self.POL = 0
        self.IF = 1
        self.MSK = 2
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
rtc_mfp_int.pull = digitalio.Pull.DOWN


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
    #i2c = I2C(board.SCL, board.SDA)
    if not my_debug:
        print(f"global: i2c (STEMMA_I2C()): {i2c}")
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
    ret = False
    if state.mfp:  # We have an interrupt!
        print(TAG+"RING RING RING we have an interrupt from the RTC shield!")
        alarm_blink(state)
        clr_alarm(state, 1)
        mcp._clr_ALMxIF_bit(1) # Clear the interrupt
        state.mfp = False
        ret = True
    return ret

# rtc_mfp_int.irq(handler=interrupt_handler, trigger=Pin.IRQ_RISING)

def read_fm_config(state):
    TAG = tag_adj(state, "read_fm_config(): ")
    key_lst = list(config.keys())
    if my_debug:
        print(TAG+f"global, key_lst: {key_lst}")
        print(TAG+"setting state class variables:")
    for k,v in config.items():
        if isinstance(v, int):
            s_v = str(v)
        elif isinstance(v, str):
            s_v = v
        elif isinstance(v, bool):
            if v:
                s_v = "True"
            else:
                s_v = "False"
        if my_debug:
            print("\tk: \'{:10s}\', v: \'{:s}\'".format(k, s_v))
        if k in key_lst:
            if k == "COUNTRY":
                if v == "PRT":
                    config["STATE"] == ""
                    config["UTC_OFFSET"] == 1
                elif v == "USA":
                    config["STATE"] = "NY"
                    config["UTC_OFFSET"] = -4
                state.COUNTRY = v
                state.STATE = config["STATE"]
            if k == "dt_str_usa":
                state.dt_str_usa = v
            if k == "is_12hr":
                state.is_12hr = v
            if k == "Use_dst":
                state.use_dst = v
            if k == "UTC_OFFSET":
                state.UTC_OFFSET = v
            if k == "tmzone":
                state.tm_tmzone = v
    if my_debug:
        print(TAG+f"for check:\n\tstate.COUNTRY: \'{state.COUNTRY}\', state.STATE: \'{state.STATE}\', state.UTC_OFFSET: {state.UTC_OFFSET}, state.tm_tmzone: \'{state.tm_tmzone}\'")

save_config(state)

def is_NTP(state):
    TAG = tag_adj(state, "is_NTP(): ")
    ret = False
    dt = None
    try:
        if ntp is not None:
            if not state.NTP_dt_is_set:
                dt = ntp.datetime
                if dt == (0,):
                    return ret
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
            if dt == (0,):
                print(TAG+f"call to ntp.datetime failed. Result: {dt}")
                return
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
        mRTC = mcp.mcptime
        state.SYS_RTC_is_set = True
        state.SYS_dt = mRTC.datetime
        if state.SYS_dt is not None:
            if state.SYS_dt.tm_year >= 2000:
                print(TAG+s1+"External RTC"+s2)
    dt = state.SYS_dt
    if not my_debug:
        print(TAG+"{:d}/{:02d}/{:02d}".format(dt.tm_mon, dt.tm_mday, dt.tm_year))
        print(TAG+"{:02d}:{:02d}:{:02d} weekday: {:s}".format(dt.tm_hour, dt.tm_min, dt.tm_sec, mcp.DOW[dt.tm_wday]) )
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

    if is_NTP(state):
        dt = state.NTP_dt
    else:
        dt = time.localtime() # state.SYS_dt

    state.dt_dict[state.tm_year] = dt.tm_year
    state.dt_dict[state.tm_mon] = dt.tm_mon
    state.dt_dict[state.tm_mday] = dt.tm_mday
    state.dt_dict[state.tm_hour] = dt.tm_hour
    state.dt_dict[state.tm_min] = dt.tm_min
    state.dt_dict[state.tm_sec] = dt.tm_sec
    state.dt_dict[state.tm_wday] = dt.tm_wday + 1  # NTP weekday 0-6 while NTP7940 weekday 1-7
    state.dt_dict[state.tm_yday] = mcp.yearday(dt)
    state.dt_dict[state.tm_isdst] = -1

    if not my_debug:
        print(TAG + s2 + f"datetime stamp:")
        print(TAG+"{:d}/{:02d}/{:02d}".format(
            state.dt_dict[state.tm_mon], state.dt_dict[state.tm_mday], state.dt_dict[state.tm_year]))
        print(TAG+"{:02d}:{:02d}:{:02d} weekday: {:s}, yearday: {:d}, isdst: {:d}".format(
            state.dt_dict[state.tm_hour], state.dt_dict[state.tm_min], state.dt_dict[state.tm_sec],
            mcp.DOW[ state.dt_dict[state.tm_wday]], state.dt_dict[state.tm_yday], state.dt_dict[state.tm_isdst]) )

    dt2 = (state.dt_dict[state.tm_year], state.dt_dict[state.tm_mon], state.dt_dict[state.tm_mday],
          state.dt_dict[state.tm_hour], state.dt_dict[state.tm_min], state.dt_dict[state.tm_sec],
          state.dt_dict[state.tm_wday])

    if not my_debug:
        print(TAG+f"going to set {eRTC} for: {dt2}")
    # ---------------------------------------------------------------------
    #  SET THE MCP7940 RTC SHIELD TIME
    # ---------------------------------------------------------------------
    mcp.mcptime = dt2 # Set the external RTC

    # ---------------------------------------------------------------------
    #  GET THE MCP7940 RTC SHIELD TIME
    # ---------------------------------------------------------------------
    ck_dt = mcp.mcptime # Check it

    if ck_dt and len(ck_dt) >= 7:
        state.EXT_RTC_is_set = True
        state.SRAM_dt = ck_dt
        if not my_debug:
            s_ampm = get_ampm(ck_dt[state.tm_hour]) # was: s_ampm = "PM" if mcp._is_PM() else "AM"
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

def can_update_fm_NTP(state):
    TAG = tag_adj(state, "can_update_fm_NTP(): ")
    ret = False
    if my_debug:
        print(TAG+f"last NTP sync: {state.ntp_last_sync_dt}")
    if state.ntp_last_sync_dt == 0:  # we did not NTP sync yet
        return True   # yes go to do NTP sync
    else:
        t1 = state.ntp_last_sync_dt
        while True:
            t2 = time.time() - state.UTC_OFFSET
            if t2 >= t1:
                t_diff = t2 - t1
                if not my_debug:
                    print(TAG+f"last time of sync: {t1}, current time {t1}, difference in seconds: {t_diff}")
                if t_diff >= 15:
                    ret = True
                    break
            time.sleep(2)  # we have to wait 15 seconds
    return ret

def is_dst(state, tm=None):
    global  ntp
    TAG= tag_adj(state, "is_dst(): ")
    
    if not state.use_dst:
        state.dst = 0
    else:
        if tm is None:
            tm = time.localtime()
        if not my_debug:
            print(TAG+f"time.localtime(): {tm}")
        dst_org = state.dst # get original value
        
        if not tm[state.tm_year] in dst.keys():
            print("year: {} not in dst dictionary ({}).\nUpdate the dictionary! Exiting...".format(tm[state.tm_year], dst.keys()))
        else:
            dst_start_end = dst[tm[state.tm_year]]
        if my_debug:
            print(TAG+f"dst_start_end: {dst_start_end}")
        
        dst_start1 =  dst_start_end[0]
        dst_end1 = dst_start_end[1]
        dst_start2 = time.localtime(dst_start1)
        dst_end2 = time.localtime(dst_end1)
        s_lst = ["dst_start1:   ", "current date: ", "dst_end1:     "]
        if not my_debug:
            for _ in range(len(s_lst)):
                s2 = s_lst[_]
                if _ == 0:
                    dst_dt = dst_start2
                elif _  == 1:
                    dst_dt = time.localtime()
                elif _ == 2:
                    dst_dt = dst_end2
                print(TAG+s2+"{:4d}-{:02d}-{:02d} {:02d}:{:02d}:{:02d}".format( \
                    dst_dt[state.tm_year], \
                    dst_dt[state.tm_mon], \
                    dst_dt[state.tm_mday], \
                    dst_dt[state.tm_hour], \
                    dst_dt[state.tm_min], \
                    dst_dt[state.tm_sec]))

        if my_debug:
            print(TAG+f"year: {tm[state.tm_year]}, dst start: {dst_start2}, dst end: {dst_end2}")
        current_time = time.time()
        if current_time > dst_start1 and current_time < dst_end1:
            dst_new = 1
        else:
            dst_new = 0
            
        if dst_new != dst_org:
            state.dst = dst_new
            ntp = None
            ntp = adafruit_ntp.NTP(pool, tz_offset = state.UTC_OFFSET if state.dst else 0)
        
        if not my_debug:
            # print(TAG+f"state.dst: {state.dst}")
            s = 'Yes' if state.dst == 1 else 'No'
            print(TAG+f"Are we in daylight saving time for country: \'{state.COUNTRY}\', state: \'{state.STATE}\' ? {s}")
    return state.dst

def set_time(state):
    global config
    TAG = tag_adj(state, "set_time(): ")
    try_cnt = 0
    good_NTP = False
    tm = None
    if can_update_fm_NTP(state):
        tm_mcp = mcp.mcptime
        mcp_dt = list(tm_mcp)  # create a list (which is mutable)
        mcp_dt_hh = mcp_dt[state.tm_hour]
        if my_debug:
            print(TAG+f"time.localtime(): {time.localtime(time.time())}, state.UTC_OFFSET: {state.UTC_OFFSET}")
        lcl_dt = time.localtime(time.time() + state.UTC_OFFSET)
        lcl_dt_hh = lcl_dt[state.tm_hour]
        # During a long sleep time it happened that the MCP7940 clock was not updated(updating)
        # In that case the MCP7940 timekeeping registers have to be updated
        # So, if the flag state.NTP_dt_is_set already had been set, it has to be reset.
        if lcl_dt_hh != mcp_dt_hh:
            state.NTP_dt_is_set = False
        if my_debug:
            print(TAG+"synchronizing builtin RTC from NTP server, waiting...")
        try_cnt = 0
        while True:
            try:
                if not state.NTP_dt_is_set:
                    # next line queries the time from an NTP server ant sets the builtin RTC
                    dt = ntp.datetime
                    if not my_debug:
                        print(TAG+f"dt: {dt}, len(dt): {len(dt)}")
                    if len(dt) < 2:
                        continue
                    mRTC.datetime = dt
                    t = time.time()
                    if my_debug:
                        print(TAG+f"time(): {t}")
                    if t >= 0:
                        good_NTP = True
                        break
                    print(TAG+"trying again. Wait...")
                    time.sleep(2)
                    try_cnt += 1
                    if try_cnt >= 3:
                        break
            except OSError as e:
                print(TAG+f"Error: {e}")
                try_cnt += 1
                if try_cnt >= 5:
                    raise
        if good_NTP:
            state.NTP_dt_is_set = True
            print(TAG+"Succeeded to update the builtin RTC from an NTP server")
            state.ntp_last_sync_dt = time.time() # get the time serial
            if not my_debug:
                print(TAG+f"Updating ntp_last_sync_dt to: {state.ntp_last_sync_dt}")
            tm = time.localtime(time.time())  # was (time.time() + state.UTC_OFFSET)
            ths = mcp.time_has_set()
            print(TAG+f"mcp.time_has_set(): {ths}")
            if not ths:
                print(TAG+f"setting MCP7940 timekeeping regs to:")
                s = " "*len(TAG)
                print(s+f"{tm}")
                #if MCP7940_RTC_update:
                #gc.collect()
                #-----------------------------------------------------------
                # Set MCP7940 RTC shield timekeeping registers
                #-----------------------------------------------------------
                mcp.mcptime = tm  # Set the External RTC Shiels's clock
                state.MCP_dt = tm
                #-----------------------------------------------------------
                # The following 2 lines added because I saw that calls to
                # mcp.mcpget_time() always returns the same datetime stamp
                if not mcp._is_started():
                    print(TAG+"mcp was not started. Starting now")
                    mcp.start()
                    if mcp._is_started():
                        print(TAG+"mcp now is running")
                else:
                    print(TAG+"mcp is running")
                    
            is_dst(state, tm)
            
            if state.set_SYS_RTC:
                if not state.SYS_RTC_is_set:
                    tm2 = (tm[state.tm_year], tm[state.tm_mon], tm[state.tm_mday], tm[state.tm_wday] + 1,
                        tm[state.tm_hour], tm[state.tm_min], tm[state.tm_sec], 0, 0)
                    mRTC.datetime = tm2  # was: mRTC().datetime(tm2)
                    state.SYS_dt = tm2
                    state.SYS_RTC_is_set = True
                    if not my_debug:
                        print(TAG+f"builtin RTC set to: {state.SYS_dt}")
            if my_debug and tm is not None:
                print(TAG+"date/time updated from: \"{}\"".format(ntp.get_host()))
        else:
            print(TAG+"failed to update builtin RTC from an NTP server")
    else:
        if my_debug:
            print(TAG+"not updating builtin RTC from NTP in this moment")


def neopixel_color(state, color):
    global pixels
    if color is None:
        color = state.curr_color_set
    elif not isinstance(color, str):
        color = state.curr_color_set

    if color in state.neopixel_dict:
        if neopixel  and not state.curr_color_set == color:
            state.curr_color_set = color
            r,g,b = state.neopixel_dict[color]  # feathers3.rgb_color_wheel( clr )
            pixels[0] = ( r, g, b, state.neopixel_brightness)
            pixels.write()

def neopixel_blink(state, color):
    TAG = tag_adj(state, "neopixel_blink(): ")
    global pixels
    if color is None:
        color = state.curr_color_set
    elif not isinstance(color, str):
        color = state.curr_color_set
    else:
        state.curr_color_set = color

    if color in state.neopixel_dict:
        if neopixel:
            if not my_debug:
                print(TAG+f"going to blink color: \'{color}\'")
            for _ in range(6):
                if _ % 2 == 0:
                    r, g, b = state.neopixel_dict[color]
                else:
                    r, g, b = state.neopixel_dict["BLK"]
                pixels[0] = ( r, g, b, state.neopixel_brightness)
                pixels.write()
                time.sleep(0.5)
            # reset to color at start of this function
            r, g, b = state.neopixel_dict["BLK"]  # was: [state.curr_color_set]
            pixels[0] = ( r, g, b, state.neopixel_brightness)
            pixels.write()

def alarm_blink(state):
    #if state.loop_nr < 3:
    #    return
    TAG = tag_adj(state, "alarm_blink(): ")
    my_RED = (200,   0,   0)
    my_GRN = (0,   200,   0)
    my_BLU = (0,     0, 200)
    my_BLK = (0,     0,   0)

    current_color = state.curr_color_set
    if state.use_neopixel:
        for _ in range(5):
            if not my_debug:
                print(TAG+f"blinking: RED")
            r,g,b = state.neopixel_dict["RED"] # feathers3.rgb_color_wheel( state.RED )
            pixels[0] = ( r, g, b, state.neopixel_brightness)
            pixels.write()
            time.sleep(1)
            if not my_debug:
                print(TAG+f"blinking: BLUE")
            r,g,b = state.neopixel_dict["BLU"] #feathers3.rgb_color_wheel( state.BLK )
            pixels[0] = ( r, g, b, state.neopixel_brightness)
            pixels.write()
            time.sleep(1)
        # restore last color:
        if my_debug:
            print(TAG+f"resetting color to: {current_color}")
        # r,g,b = feathers3.rgb_color_wheel( current_color )
        r,g,b = state.neopixel_dict["BLK"]
        pixels[0] = ( r, g, b, state.neopixel_brightness)
        pixels.write()

"""
 * @brief In this version of CircuitPython one can only check if there is a WiFi connection
 * by checking if an IP address exists.
 * In the function do_connect() the global variable s_ip is set.
 *
 * @param None
 *
 * @return boolean. True if exists an ip address. False if not.
"""
def wifi_is_connected(state):
    return True if state.s__ip is not None and len(state.s__ip) > 0 and state.s__ip != '0.0.0.0' else False

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

    try:
        wifi.radio.connect(ssid=ssid, password=pw)
    except ConnectionError as e:
        print(TAG+f"WiFi connection Error: \'{e}\'")
    except Exception as e:
        print(TAG+f"Error: {dir(e)}")

    state.ip = wifi.radio.ipv4_address

    if state.ip:
        state.s__ip = str(state.ip)
        if not my_debug:
            print(TAG+f"connected to \'{ssid}\'. IP: {state.s__ip}")


# When a call to mcp.is_12hr() is positive,
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

    is_12hr = mcp._is_12hr
    is_PM = mcp._is_PM(hours) # don't use get_ampm because that returns a string type

    if my_debug:
        print(TAG+f"param t: {t}")
        print(TAG+f"is_12hr: {is_12hr}, is_PM: {is_PM}")

    t2 = (month, date, hours, minutes, seconds,  weekday)
    t3 = (year,) + t2 if num_registers == 7 else t2

    if my_debug:
        print(TAG+f"t2: {t2}")

    t3 += (is_12hr, is_PM)  # add yearday and isdst to datetime stamp

    if my_debug:
        print(TAG+f"return value: {t3}")

    return t3

def get_hours12(hh):
    ret = hh
    if hh > 12:
        ret = hh - 12
    return ret

def upd_SRAM(state):
    global SYS_dt
    TAG = tag_adj(state, "upd_SRAM(): ")
    num_registers = 0
    res = None
    tm = None
    tm2 = None
    tm3 = None
    s_tm = ""
    s_tm2 = ""
    dt1 = ""
    dt2 = ""
    dt3 = ""
    dt6 = ""
    dt7 = ""

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
        tm = mcp.mcptime  # Using EXTernal RTC
        s_tm = "mcp.mcptime"
        s_tm2 = "EXT"
    if my_debug:
        print(TAG+f"tm: {tm}")

    tm2 = add_12hr(tm)  # Add is_12hr, is_PM and adjust hours for 12 hour time format
    le = len(tm2)
    if le < 2:
        if my_debug:
            print(TAG+f"tm2 length {le} insufficient")
        return -1
    if my_debug:
        print(TAG+f"tm2: {tm2}")

    is_12hr = 0
    is_PM = 0
    hours12 = 0

    if le == 7:
        year, month, date, hours, minutes, seconds, weekday = tm2
        tm3 = (year-2000, month, date, hours, minutes, seconds, weekday)
    elif le == 9:
        year, month, date, hours, minutes, seconds, weekday, is_12hr, is_PM = tm2
        if is_12hr:
            hours12 = get_hours12(hours)
        else:
            hours12 = hours
        tm3 = (year-2000, month, date, hours, minutes, seconds, weekday, is_12hr, is_PM)

    # print(TAG+f"month: {month}")
    if month >= 1 and month <= 12:  # prevent key error
        dt1 = "{:s} {:02d} {:d}".format(
            state.month_dict[month],
            date,
            year)
    else:
        dt1 = ""

    #dt1 = "{}/{:02d}/{:02d}".format(
    #        year,
    #        month,
    #        date)

    ampm = get_ampm(hours)
    
    if state.dt_str_usa:
        if is_12hr:
            hours12 = get_hours12(hours)
            if my_debug:
                print(TAG+f"hours: {hours}, minutes: {minutes}, seconds: {seconds}, is_12hr: {is_12hr}")
            if hours >= 0 and hours < 24 and minutes >= 1 and minutes < 60 and seconds >= 1 and seconds < 60:
                dt2 = "{:d}:{:02d}:{:02d} {}".format(
                hours12,
                minutes,
                seconds,
                ampm)
            else:
                dt2 = "?:??:?? ?"
        else:
            if my_debug:
                print(TAG+f"hours: {hours}, minutes: {minutes}, seconds: {seconds}, is_12hr: {is_12hr}")
            if hours >= 0 and hours < 13 and minutes >= 1 and minutes < 60 and seconds >= 1 and seconds < 60:
                dt2 = "{:02d}:{:02d}:{:02d}".format(
                hours,
                minutes,
                seconds)
            else:
                dt2 = "??:??.??"

    if weekday >= 0 and weekday <= 6:
        wd = mcp.DOW[weekday]
    else:
        wd = "?"

    dt3 = "wkday: {}".format(wd)

    dt6 = "is_12hr: {}".format(is_12hr)

    if is_PM:
        dt7 = "is_PM: {}".format(is_PM)
    else:
        dt7 = "is_PM: {}".format(mcp._is_PM(hours))

    msg = ["Write to SRAM:", dt1, dt2, dt3, dt6, dt7]
    pr_msg(state, msg)

    mcp.clr_SRAM()  # Empty the total SRAM

    if my_debug:
        mcp.show_SRAM() # Show the values in the cleared SRAM space

    if my_debug:
        print(TAG+f"type({s_tm}): {type(tm)},")
        print(TAG+f"{s_tm2}ernal_dt: {tm}")
    if isinstance(tm3, tuple):
        if not my_debug:
            print(TAG+f"we\'re going to write {tm3} to the RTC shield\'s SRAM")
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
        if state.use_dst:
            isdst = state.dst
        else:
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
        
        ampm = get_ampm(hours)
        if not my_debug:
            print(TAG+f"hours: {hours}, ampm: {ampm}")
            
        hours12 = get_hours12(hours)

        # weekday += 1  # Correct for mcp weekday is 1 less than NTP or time.localtime weekday
        if month >= 1 and month <= 12:  # prevent key error
            mon_s = state.month_dict[month]
        else:
            mon_s = " ? "

        if state.dt_str_usa:
            dt1 = "{:s} {:02d} {:d}".format(
                mon_s,
                date,
                year)
        else:
            dt2 = "{:d}{:02d}/{:02d}".format(
                date,
                month,
                year)

        if is_12hr:
            if hours >= 0 and hours < 24 and minutes >= 1 and minutes < 60 and seconds >= 1 and seconds < 60:
                dt2 = "{:d}:{:02d}:{:02d} {}".format(
                hours12,
                minutes,
                seconds,
                ampm)
            else:
                dt2="?:??:???? ?"
        else:
            if hours >= 0 and hours < 24 and minutes >= 1 and minutes < 60 and seconds >= 1 and seconds < 60:
                dt2 = "{:02d}:{:02d}:{:02d}".format(
                hours,
                minutes,
                seconds)
            else:
                dt2="??:??:??"

        if weekday >= 0 and weekday <= 6:
            wd = mcp.DOW[weekday]
        else:
            wd = "?"
        # print(TAG+f"weekday: {weekday}, mcp.DOW[weekday]: {wd}")

        dt3 = "wkday: {}".format(wd)

        dt4 = "yrday: {}".format(yearday)

        dt5 = "dst: {}".format(isdst)

        dt6 = "is_12hr: {}".format(is_12hr)

        if is_PM:
            dt7 = "is_PM: {}".format(is_PM)
        else:
            dt7 = "is_PM: {}".format(mcp._is_PM(hours))

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
    yy = now[state.tm_year]
    mm = now[state.tm_mon]
    dd = now[state.tm_mday]
    hh = now[state.tm_hour]
    mi = now[state.tm_min]
    ss = now[state.tm_sec]
    wd = now[state.tm_wday]

    dow = mcp.DOW[wd]  # was: [wd+1]

    swd = dow[:3] if short else dow

    dt0 = "{:s}".format(swd)
    if my_debug:
        print(TAG+f"state.dt_str_usa: {state.dt_str_usa}")
    if mcp._is_12hr:
        ampm = get_ampm(hh)
        if hh > 12:
            hh -= 12

        #if hh == 0:
        #    hh = 12

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

    month   = dt[state.tm_mon]
    date    = dt[state.tm_mday]
    hours   = dt[state.tm_hour]
    minutes = dt[state.tm_min]
    seconds = dt[state.tm_sec]
    weekday = dt[state.tm_wday]# +1
    dow = mcp.DOW[weekday]  # was: mcp.DOW[weekday]
    # print(TAG+f"weekday: {weekday}")

    t = month, date, hours, minutes, seconds, weekday

    if alarm1en and alarm_nr == 1:
        if my_debug:
            print(TAG+f"setting alarm1 for: {t[:5]}, {dow}")
                    # ---------------------------------------------------------------
        # SET ALARM1
        # ---------------------------------------------------------------
        mcp.alarm1 = t  # Set alarm1
        # ---------------------------------------------------------------
        t_ck = mcp.alarm1[:6]  # check result
        if my_debug:
            print(TAG+f"check: alarm{alarm_nr} is set for: {t_ck}")
        state.alarm1 = t_ck
        state.alarm1_set = True
        mcp._clr_ALMxIF_bit(alarm_nr)     # Clear the interrupt of alarm1
        mcp._set_ALMxMSK_bits(alarm_nr,1) # Set the alarm1 mask bits for a minutes match
        # IMPORTANT NOTE:
        # ===============
        # I experienced that if mcp.alarm1 (or mcp.alarm2) is called earlier, the setting of the ALMPOL bit is reset,
        # that is why we set the ALMPOL bit again (below)
        # ===============
        if not mcp._read_ALM_POL_IF_MSK_bits(1, state.POL):
            mcp._set_ALMPOL_bit(alarm_nr) # Set ALMPOL bit of Alarm1 (so the MFP follows the ALM1IF)

    if alarm2en and alarm_nr == 2:
        if my_debug:
            print(TAG+f"setting alarm2 for: {t[:5]}, {dow}")
        mcp.alarm2 = t  # Set alarm2
        t_ck = mcp.alarm2[:6]  # check result
        if my_debug:
            print(TAG+f"check: alarm2 is set for: {t_ck}")
        state.alarm2 = t_ck
        state.alarm2_set = True
        mcp._clr_ALMxIF_bit(alarm_nr)     # Clear the interrupt of alarm1
        mcp._set_ALMxMSK_bits(alarm_nr,1) # Set the alarm1 mask bits for a minutes match
        if not mcp._read_ALM_POL_IF_MSK_bits(alarm_nr, state.POL):
            mcp._set_ALMPOL_bit(alarm_nr) # Set ALMPOL bit of alarm1 (so the MFP follows the ALM1IF)

def clr_alarm(state, alarm_nr=None):
    TAG = tag_adj(state, "clr_alarm(): ")
    if alarm_nr is None:
        return

    num_regs = 8

    eal = (0,)*num_regs

    if alarm_nr in [1, 2]:
        if alarm_nr == 1:
            mcp.alarm1 = eal  # clear alarm1 datetime stamp
            mcp._clr_ALMxIF_bit(alarm_nr) # clear alarm1 Interrupt Flag bit
            state.alarm1_set = False
            state.alarm1 = eal
            mcp.alarm_enable(alarm_nr, False)  # Disable alarm2
            if my_debug:
                print(TAG+f"state.alarm1: {state.alarm1[:num_regs]}")
            ck = mcp.alarm1[:6]
        elif alarm_nr == 2:
            mcp.alarm2 = eal    # clear alarm2 datetime stamp
            mcp._clr_ALMxIF_bit(2) # clear alarm2 Interrupt Flag bit
            state.alarm2_set = False
            state.alarm2 = eal
            mcp.alarm_enable(alarm_nr, False)  # Disable alarm2
            if my_debug:
                print(TAG+f"state.alarm2: {state.alarm2[:num_regs]}")
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
        state.alarm1_int = True if mcp._read_ALM_POL_IF_MSK_bits(1,state.IF) else False
        if state.alarm1_int:
            alm1if_bit = mcp._read_ALM_POL_IF_MSK_bits(1,state.IF)
            if my_debug:
                print(TAG+"we have an interrupt from alarm1")
                print(TAG+"alarm1 IF bit: {:b}".format(alm1if_bit))
                alm1msk_bits = mcp._read_ALM_POL_IF_MSK_bits(1,state.MSK)
                show_alm_match_type(alm1msk_bits)
            ck_rtc_mfp_int(state)

    if alarm2en:
        if my_debug:
            print(TAG+"alarm2 is enabled")
        #t_ck = mcp.alarm2[:6]  # check result
        t_ck = state.alarm2[:6]
        if my_debug:
            print(TAG+f"alarm2 is set for: {t_ck}")
        state.alarm2_int = True if mcp._read_ALM_POL_IF_MSK_bits(2,state.IF) else False
        if state.alarm2_int:
            alm2if_bit = mcp._read_ALM_POL_IF_MSK_bits(2,state.IF)
            if my_debug:
                print(TAG+"we have an interrupt from alarm2")
                print(TAG+"alarm2 IF bit: {:b}".format(alm2if_bit))
                alm2msk_bits = mcp._read_ALM_POL_IF_MSK_bits(2,state.MSK)
                show_alm_match_type(alm2msk_bits)
            ck_rtc_mfp_int(state)

# check the RTC interrupt line (RTC io4 to ProS3 io33)
def ck_rtc_mfp_int(state):
    TAG = tag_adj(state, "ck_rtc_mfp_int(): ")
    v = rtc_mfp_int.value
    if my_debug:
        print(TAG+f"rtc_mfp_int.value: {v}")
    s = "High" if v else "Low "
    if my_debug:
        print(TAG+f"rtc interrupt line value: {s}")
    if v:
        state.mfp = True if v == 1 else False

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
    TAG = tag_adj(state, "show_alarm_output_truth_table(): ")
    if alarm_nr is None:
        return
    if not alarm_nr in [1, 2]:
        return

    s_ALMxIF = "ALM"+str(alarm_nr)+"IF"

    print()
    print(f"Single alarm output truth table for alarm{alarm_nr}:")
    s1 = "+--------+---------+-------+----------------------------------+"
    s2 = "| ALMPOL |  {:6s} |  MFP  |            Match type            |".format(s_ALMxIF)

    alarm_POL = 0
    alarm_IF = 0
    alarm_MSK = 0
    for _ in range(3):
        itm = mcp._read_ALM_POL_IF_MSK_bits(alarm_nr, _)
        if _ == 0:
            alarm_POL = itm # Read alarm1 or alarm2 ALMPOL bit
        elif _ == 1:
            alarm_IF = itm # Read alarm1 or alarm2 interrupt flag
        elif _ == 2:
            alarm_MSK = itm # Read ALMxMSK bits of alarm1 or alarm2
    if my_debug:
        print(TAG+"ALM{:d}MSK_bits: b\'{:03b}\'".format(alarm_nr, alarm_MSK))
    msk_match = mcp._match_lst_long[alarm_MSK] # get the match long text equivalent
    mfp = rtc_mfp_int.value # get the RTC shield MFP interrupt line state

    if my_debug:
        print(TAG+f"alarm{alarm_nr}_POL: {alarm_POL}, alarm{alarm_nr}_IF: {alarm_IF}, mfp: {mfp}")

    notes1 = "mask bits: \'b{:03b}\' type: {:8s}".format(alarm_MSK, msk_match)
    s3= "|   {:d}    |    {:d}    |   {:d}   | {:24s} |".format(alarm_POL, alarm_IF, mfp, notes1)
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

    if my_debug:
        print(TAG+f"alarm1 enabled:{ae1}, alarm2 enabled: {ae2}")

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

        match1 = mcp._match_lst[mcp._read_ALM_POL_IF_MSK_bits(1, state.MSK)]
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

        match2 = mcp._match_lst[mcp._read_ALM_POL_IF_MSK_bits(2, state.MSK)]
        if match2 == "mm" and not state.dt_str_usa:
            ss2 = None

    tm_current = mcp.mcptime # Get current datetime stamp from the External UM MCP7940 RTC shield
    if not my_debug:
        print(TAG+f"mcp.mcptime: {tm_current}")

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


def get_dt(state):
    dt = None
    ret = ""
    if is_EXT_RTC():
        if state.lStart:
            while True:
                dt = mcp.mcptime
                if dt[state.ss] == 0: # align for 0 seconds (only at startup)
                    break
        else:
            dt = mcp.mcptime
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
 * Then it sets the internal RTC from a NTP server datetime stamp. (The chick and the egg story. Who was first?)
 * This actual datetime we need to determine is we are in a daylight saving time (dst) period of the year or not.
 * Next the ntp object will be re-created, this 2nd time with the timezone UTC_OFFSET if we're in an dst period.
 * Setup() checks and sets various settings of the connected external Unexpected Makrer TinyPico RTC Shield (MCP7940).
 * This function is called by main().
 *
 * @param: state class object
 *
 * @return None
"""
def setup(state):
    global pixels, config, ntp, pool, mRTC
    TAG = tag_adj(state, "setup(): ")
    s_mcp = "MCP7940"
    s_pf1 = s_mcp+" Power failed"
    s_en1 = s_mcp+" RTC battery "
    s_en2 = s_en1+"is now enabled? "
    s_rtc = "RTC datetime year "
    MCP7940_is_started = False
    
    # Create a colour wheel index int
    color_index = 0

    print(TAG+f"board: \'{state.board_id}\'")
    
    read_fm_config(state)

    wifi.AuthMode.WPA2   # set only once
    do_connect(state)

    if not my_debug:
        print(TAG+f"Checking if {s_mcp} has been started.")
    if not mcp._is_started():
        if not my_debug:
            print(TAG+f"{s_mcp} not started yet...")
        mcp.start()
        if mcp._is_started():
            MCP7940_is_started = True
            if not my_debug:
                print(TAG+f"{s_mcp} now started")
        else:
            print(TAG+f"failed to start {s_mcp}")
    else:
        MCP7940_is_started = True
        if not my_debug:
            print(TAG+f"{s_mcp}is running")
    
    # IMPORTANT: before setting the EXTernal RTC, set the 12/24 hour format !
    # Set 12/24 hour time format
    if not my_debug:
        print(TAG+f"setting MCP7940.is_12hr to: {state.dt_str_usa}")
    mcp.set_12hr(state.dt_str_usa)
    # Check:
    if not my_debug:
        ck = "12hr" if mcp._is_12hr else "24hr"
        print(TAG+f"MCP7950 datetime format: {ck}")
    
    # We need an NTP datetime stamp first
    # to set the internal RTC
    ntp = adafruit_ntp.NTP(pool, tz_offset = 0)  # tz_offset e.g.: -4, 0, 1, 12
    mRTC.datetime = ntp.datetime 
    
    if ntp and my_debug:
        print(TAG+f"ntp object {type(ntp)} created")
    if wifi_is_connected(state):
        if not my_debug:
            s = "Yes" if state.use_dst else "No"
            print(TAG+f"Using dst? {s}")
        # Now adjust the ntp object for local timezone offset
        if state.use_dst:
            my_country_dst = state.UTC_OFFSET if is_dst(state) else 0
            ntp = None
            ntp = adafruit_ntp.NTP(pool, tz_offset = my_country_dst)  # tz_offset e.g.: -4, 0, 1, 12
            pool = None
        else:
            my_country_dst = 0
        if not my_debug:
            print(TAG+f"my_country_dst: {my_country_dst}")
        
        set_time(state)  # call at start
        gc.collect()

    if state.dt_str_usa == True:
        print(TAG+"setting MCP7940 for 12hr time format")
    ret = mcp.set_s11_12hr(state.dt_str_usa) # Set for time format USA (12 hours & AM/PM
    if ret > -1:
        # Check the value set
        is12hr = mcp._is_12hr
        config["is_12hr"] = is12hr  # save to json
        save_config(state)
    else:
        print(TAG+"setting mcp._is_12hr failed")

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

    MCP7940_is_started = False

    if my_debug:
        print(TAG+f"Checking if {s_mcp} has been started.")
    if not mcp._is_started():
        if not my_debug:
            print(TAG+f"{s_mcp} not started yet...")
        mcp.start()
        if mcp._is_started():
            MCP7940_is_started = True
            if not my_debug:
                print(TAG+f"{s_mcp} now started")
        else:
            print(TAG+f"failed to start {s_mcp}")
    else:
        MCP7940_is_started = True
        if not my_debug:
            print(TAG+f"{s_mcp} is running")

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
    s_bbe_yn = "Yes" if mcp._is_battery_backup_enabled() else "No"
    if s_bbe_yn == "No":
        if my_debug:
            print(TAG+f"{s_en1}is not enabled. Going to enable")
        mcp.battery_backup_enable(True)  # Enable backup battery
        # Check backup battery status again:
        s_bbe_yn = "Yes" if mcp._is_battery_backup_enabled() else "No"
        if my_debug:
            print(TAG+f"{s_en2}{s_bbe_yn}")
    else:
        if my_debug:
            print(TAG+f"{s_en2}{s_bbe_yn}")

    if state.set_SYS_RTC :
        if my_debug:
            print(TAG+"Going to set internal (SYS) RTC")
        set_INT_RTC(state)

    #if state.set_EXT_RTC:
    #    set_EXT_RTC(state)
    pool = None



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

    alarm_nr = 1
    mcp._clr_SQWEN_bit()        # Clear the Square Wave Enable bit
    print(TAG+f"check: alarm{alarm_nr} ALMPOL_bit: {mcp._read_ALM_POL_IF_MSK_bits(1, state.POL)}")
    mcp._clr_ALMxIF_bit(alarm_nr)      # Clear the interrupt of alarm1
    mcp._set_ALMxMSK_bits(alarm_nr,1)  # Set the alarm1 mask bits for a minutes match
    mcp._set_ALMPOL_bit(alarm_nr)      # Set ALMPOL bit of Alarm1 (so the MFP follows the ALM1IF)
    state.alarm1_int = False
    mcp.alarm_enable(alarm_nr, True)   # Enable alarm1
    if not my_debug:
        print(TAG+"...")

    alarm_nr = 2
    print(TAG+f"check: alarm{alarm_nr} ALMPOL_bit: {mcp._read_ALM_POL_IF_MSK_bits(2, state.POL)}")
    mcp._clr_ALMxIF_bit(alarm_nr)      # Clear the interrupt of alarm2
    mcp._set_ALMxMSK_bits(alarm_nr,1)  # Set the alarm2 mask bits for a minutes match
    mcp._set_ALMPOL_bit(alarm_nr)      # ALMPOL bit of Alarm2 (so the MFP follows the ALM2IF)
    state.alarm2_int = False
    mcp.alarm_enable(alarm_nr, False)  # Disable alarm2

    state.mfp = True if rtc_mfp_int.value == 1 else False

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
                        mcp.alarm_enable(alarm_nr, True)   # Enable alarm1
                        set_alarm(state, alarm_nr, 2) # Set alarm1 for time now + 2 minutes
                        state.alarm1_set = True
                        alarm_start = False
                    #pol_alarm_int(state)  # Check alarm interrupt
                ck_rtc_mfp_int(state)
                show_mfp_output_mode_status(state)
                if state.loop_nr >= 3:  # Only perform this
                    show_alarm_output_truth_table(state, alarm_nr) # Show alarm output truth table for alarm1
                    show_alm_int_status(state)
                pol_alarm_int(state)  # Check alarm interrupt
                if state.alarm1_int:
                    if interrupt_handler(state):
                        raise KeyboardInterrupt
                # pol_alarm_int(state)  # Check alarm interrupt
                # ------------------------------------------------------------------------------------------------
        except KeyboardInterrupt:

            r,g,b = pros3.rgb_color_wheel( state.BLK )
            state.curr_color_set == state.BLK
            pixels[0] = ( r, g, b, state.neopixel_brightness)
            pixels.write()
            print("KeyboardInterrupt. Exiting...")
            print()
            # wifi.radio.stop_station()
            sys.exit()
        except Exception as e:
            print("Error", e)
            raise

if __name__ == '__main__':
    main()

