
# SPDX-FileCopyrightText: 2023 Paulus Schulinck
#
# SPDX-License-Identifier: MIT
##############################

"""
    This CircuitPython script is created to show how I managed to:
    a) read the values of the registers (e.g.: timekeeping data) from an Unexpected Maker MCP7940 RTC board;
    b) write and read timekeeping data to and from the MCP7940's user SRAM space.

    I created and tested this script on an Unexpected Maker ESP32S3 FeatherS3 flashed with circuitpython,
    initially versions 8.2.6 and finally 9.0.0-Alpha.1-50.
    This script is also able to send texts to an attached I2C display,
    in my case an Adafruit 1.12 inch mono OLED 128x128 display (SH1107).

    Note: since CircuitPython (CPY) V8.x the CPY status_bar is set ON/off in file: boot.py

    This script is tested successfully on an Unexpected Maker FeatherS3, version P4.

    Update October 2023:

    The script tries to establish WiFi and when successfull it will fetch a datetime stamp from the Adafruit NTP server.
    Depending of the global boolean variables: 'state.set_SYS_RTC' and 'state.set_EXT_RTC', the internal and/or the external RTC(s)
    is/are set.

    The external MCP7940 RTC timekeeping set values will be read frequently.
    For test this script and the library script mcp7940.py contain function to write and read datetime stamps
    to and from the MCP7940 user space in its SRAM.
    The MCP7940 RTC needs only to be set when the RTC has been without power or not has been set before.
    When you need more (debug) output to the REPL, set the global variable 'my_debug' to True.

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
import neopixel
import feathers3
import rtc
import mcp7940
# Global flags
# --- DISPLAY DRTIVER selection flag ----+
use_sh1107 = True    #                   |
# ---------------------------------------+
use_wifi = True
use_TAG = True
my_debug = False  # Set to True if you need debug output to REPL
use_ping = True


mRTC = rtc.RTC()  # create internal RTC object
if my_debug:
    print(f"global mRTC: {mRTC}")

import adafruit_ntp
pool = socketpool.SocketPool(wifi.radio)
ntp = adafruit_ntp.NTP(pool, tz_offset=1)  

pool = None

state = None

class State:
    def __init__(self, saved_state_json=None):
        self.board_id = None
        self.lStart = True
        self.tag_le_max = 24  # see tag_adj()
        self.use_clr_SRAM = False
        self.set_SYS_RTC = True
        self.NTP_dt_is_set = False
        self.SYS_RTC_is_set = False
        self.set_EXT_RTC = True # Set to True to update the MCP7940 RTC datetime values (and set the values of dt_dict below)
        self.EXT_RTC_is_set = False
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


state = State()

state.board_id = board.board_id

def pr_msg(state, msg_lst=None):
    pass

if my_debug:
    print()  # Cause REPL output be on a line under the status_bar
    print(f"MCP7940 and SH1107 tests for board: \'{id}\'") # Unexpected Maker FeatherS3")
    print("waiting 5 seconds...")
    time.sleep(5)
    msg = ["MCP7940 and SH1107 tests", "for board:", "\'"+state.board_id+"\'"]
    pr_msg(state, msg)

if my_debug:
    if wifi is not None:
        print(f"wifi= {type(wifi)}")

if state.board_id == 'unexpectedmaker_feathers3':
    state.use_neopixel = True
    import feathers3
    import neopixel
    # Create a NeoPixel instance
    # Brightness of 0.3 is ample for the 1515 sized LED
    pixels = neopixel.NeoPixel(board.NEOPIXEL, 1, brightness=0.3, auto_write=True, pixel_order=neopixel.RGB)
    state.neopixel_brightness = 0.005
    state.BLK = 0
    state.RED = 1
    state.GRN = 200
else:
    pixels = None
    state.use_neopixel = False
    state.neopixel_brightness = None
    state.BLK = None
    state.RED = None
    state.GRN = None

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

    if is_INT_RTC():
        mRTC.datetime = ntp.datetime
        state.SYS_dt = mRTC.datetime
        #print(TAG+f"state.SYS_dt: {state.SYS_dt}")
        state.SYS_RTC_is_set = True
        if state.SYS_dt.tm_year >= 2000:
             print(TAG+s1+"NTP service "+s2) # +f"{state.SYS_dt}")
    elif state.EXT_RTC_is_set:
        mRTC = mcp.time
        state.SYS_RTC_is_set = True
        state.SYS_dt = mRTC.datetime
        if state.SYS_dt is not None:
            if state.SYS_dt.tm_year >= 2000:
                print(TAG+s1+"External RTC"+s2) # +f"{state.SYS_dt}")
    dt = state.SYS_dt
    if not my_debug:
        print(TAG+"{:d}/{:02d}/{:02d}".format(dt.tm_mon, dt.tm_mday, dt.tm_year))
        print(TAG+"{:02d}:{:02d}:{:02d} weekday: {:d}".format(dt.tm_hour, dt.tm_min, dt.tm_sec, dt.tm_wday) )


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
    print(TAG+"awaiting seconds = 0 ...")    

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
    state.dt_dict[state.wd] = dt.tm_wday
    state.dt_dict[state.yd] = mcp.yearday(dt)
    state.dt_dict[state.isdst] = -1
    
    if not my_debug:
        print(TAG + s2 + f"datetime stamp:")
        print(TAG+"{:d}/{:02d}/{:02d}".format(
            state.dt_dict[state.mo], state.dt_dict[state.dd], state.dt_dict[state.yy]))
        print(TAG+"{:02d}:{:02d}:{:02d} weekday: {:d}, yearday: {:d}, isdst: {:d}".format(
            state.dt_dict[state.hh], state.dt_dict[state.mm], state.dt_dict[state.ss], 
            state.dt_dict[state.wd], state.dt_dict[state.yd], state.dt_dict[state.isdst]) )

    dt2 = (state.dt_dict[state.yy], state.dt_dict[state.mo], state.dt_dict[state.dd], 
          state.dt_dict[state.hh], state.dt_dict[state.mm], state.dt_dict[state.ss], 
          state.dt_dict[state.wd])
    
    if my_debug:
        print(TAG+f"going to set "+eRTC+" for: {dt2}")
    mcp.time = dt2 # Set the external RTC
    ck_dt = mcp.time # Check it
    if ck_dt and len(ck_dt) >= 7:
        state.EXT_RTC_is_set = True
        state.SRAM_dt = ck_dt
        if not my_debug:
            print(TAG+eRTC+f"updated to: {ck_dt}")
    else:
        state.SRAM_dt = ()

# Convert a list to a tuple
def convert(lst):
    if isinstance(lst, list):
        return tuple(i for i in lst)
    else:
        if my_debug:
            print(f"convert(): return value: {lst}")
        return lst  # return an empty tuple

def upd_SRAM(state):
    global SYS_dt
    TAG = tag_adj(state, "upd_SRAM(): ")
    res = None
    res2 = None
    yrday_old = -1
    yrday_new = -1
    if state.use_clr_SRAM:
        if my_debug:
            print(TAG+"First we go to clear the SRAM data space")
        mcp.clr_SRAM()
    else:
        if my_debug:
            print(TAG+"We\'re not going to clear SRAM. See global var \'state.use_clr_SRAM\'")
    tm = time.localtime()
    mcp.show_SRAM() # Show the values in the cleared SRAM space
    if my_debug:
        print(TAG+f"type(tm = time.localtime()): {type(tm)},\nSYS_dt: {tm}")
    if isinstance(tm, time.struct_time):
        if my_debug:
            print(TAG+"going to write time.localtime() to MCP7940 SRAM")
        mcp.write_to_SRAM(tm)
    if my_debug:
        print(TAG+"Check: result reading from SRAM:")
    res = mcp.read_fm_SRAM() # read the datetime saved in SRAM
    if res is not None:
        if isinstance(tm, tuple):
            yrday_old = res[7]
            yrday_new = mcp.yearday(res)
    else:
        res = ()
    le = len(res)
    if len(res) >= 7:
        res2 = ()
        for _ in range(7):
            res2 += (res[_],)
        res2 += (yrday_new,-1,)  # add yearday and isdst
        if my_debug:
            print(TAG+f"yearday old: {yrday_old}, new: {yrday_new} ")
            print(TAG+f"result reading from SRAM: {res2}")
        le = len(res2)

        year, month, date, hours, minutes, seconds, weekday, yearday, isdst = res2

        dt1 = "{}/{:02d}/{:02d}".format(
            year,
            month,
            date)


        dt2 = "{:02d}:{:02d}:{:02d}".format(
            hours,
            minutes,
            seconds)

        wd = mcp.DOW[weekday]
        dt3 = "wkday: {}".format(wd)

        dt4 = "yrday: {}".format(yearday)

        dt5 = "dst: {}".format(isdst)


        msg = ["Read from SRAM:", dt1, dt2, dt3, dt4, dt5]
        pr_msg(state, msg)


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
    yy = now[state.hh]
    mm = now[state.mo]
    dd = now[state.dd]
    hh = now[state.hh]
    mi = now[state.mm]
    ss = now[state.ss]
    wd = now[state.wd]

    dow = mcp.DOW[wd]

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

        dt1 = "{:d}/{:02d}/{:02d}".format(mm, dd, yy)
        dt2 = "{:02d}:{:02d}:{:02d} {:s}".format(hh, mi, ss, ampm)
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
 * @param None
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


"""
 * @brief this function sets the WiFi.AuthMode. Then the function calls the function do_connect()
 * to establish a WiFi connection.
 *
 * @param None
 *
 * @return None
"""
def setup(state):
    global pixels, my_brightness, mRTC, SRAM_dt, SYS_dt
    TAG = tag_adj(state, "setup(): ")
    # Create a colour wheel index int
    color_index = 0
    
    print(TAG+f"board: \'{state.board_id}\'")

    if state.board_id == 'unexpectedmaker_feathers3':
        try:
            # Turn on the power to the NeoPixel
            feathers3.set_ldo2_power(True)

            if state.use_neopixel:
                pixels = neopixel.NeoPixel(board.NEOPIXEL, 1)
                #for i in range(len(pixels)):
                #    pixels[i] = RED
                neopixel.NeoPixel.brightness = state.neopixel_brightness
                r,g,b = feathers3.rgb_color_wheel( state.BLK )
                pixels[0] = ( r, g, b, state.neopixel_brightness)
                pixels.write()
        except ValueError:
            pass

    wifi.AuthMode.WPA2   # set only once

    if is_NTP(state):
        print(TAG+"We have NTP")
    if is_INT_RTC():
        print(TAG+"We have an internal RTC")
        if state.SYS_RTC_is_set:
            print(TAG+"and the internal RTC is set from an NTP server")
    if is_EXT_RTC:
        print(TAG+"We have an external RTC")
        if state.EXT_RTC_is_set:
            print(TAG+"and the external RTC is set from an NTP server")


    s_mcp = "MCP7940"
    s_pf1 = s_mcp+" Power failed"
    s_en1 = s_mcp+" RTC battery "
    s_en2 = s_en1+"is now enabled? "
    s_rtc = "RTC datetime year "

    pwrud_dt = mcp.pwr_updn_dt(False)
    if my_debug:
        print(TAG+f"power down timestamp: {pwrud_dt}")
    pwrud_dt = mcp.pwr_updn_dt(True)
    if my_debug:
        print(TAG+f"power up timestamp: {pwrud_dt}")
        print(TAG+f"Checking for {s_mcp} power failure.")
    s_pf_yn = "Yes" if mcp.has_power_failed() else "No"
    if my_debug:
        print(TAG+f"{s_pf1}? {s_pf_yn}") # Check if the power failed bit is set
    if s_pf_yn == "Yes":
        mcp.clr_pwr_fail_bit()
        if not mcp.has_power_failed():
            if my_debug:
                print(TAG+"{s_pf1} bit cleared")
    if my_debug:
        print(TAG+f"Checking if {s_mcp} has been started.")
    if not mcp.is_started():
        if my_debug:
            print(TAG+f"{s_mcp} not started yet...")
        mcp.start()
        if mcp.is_started():
            if my_debug:
                print(TAG+f"{s_mcp} now started")
        else:
            print(TAG+f"failed to start {s_mcp}")
    else:
        if my_debug:
            print(TAG+f"{s_mcp}is running")
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

    state.SRAM_dt = convert( mcp.read_fm_SRAM() )
    # print(TAG+f"SRAM_dt: {SRAM_dt}. type(SRAM_dt): {type(SRAM_dt)}. len(SRAM_dt): {len(SRAM_dt)}")
    
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
        ret = "{} {:4d}-{:02d}-{:02d} {:02d}:{:02d}:{:02d}. Day of year: {:>3d}".format(mcp.weekday_S(),dt[state.yy], dt[state.mo], dt[state.dd], dt[state.hh], dt[state.mm], dt[state.ss], yrday)
    
    return ret


"""
 * @brief function performs a ping test with google.com
 *
 * @param None
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
 * @param None
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


"""
 * @brief function print hostname to REPL
 *
 * @param None
 *
 * @return None
"""
def hostname(state):
    TAG = tag_adj(state, "hostname(): ")
    print(TAG+f"wifi.radio.hostname= \'{wifi.radio.hostname}\'")

"""
 * @brief function prints mac address to REPL
 *
 * @param None
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
            print("\nHello from feathers3!")
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
    #feathers3.set_pixel_power(True)
   #feathers3.set_ldo2_power(True)  <<<<=== Is already set in setup()
    # Rainbow colours on the NeoPixel

    while True:
        # Get the R,G,B values of the next colour
        r,g,b = feathers3.rgb_color_wheel( color_index )
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
    # state = State()
    TAG = tag_adj(state, "main(): ")
    if my_debug:
        print("Waiting another 5 seconds for mu-editor etc. getting ready")
    time.sleep(5)
    setup(state)
    if my_debug:
        print("Entering loop")
    discon_msg_shown = False

    ping_done = False
    grn_set = False
    red_set = False
    count_tried = 0
    count_tried_max = 10
    state.lStart = True
    loop_nr = 0
    while True:
        try:
            loop_nr += 1
            if loop_nr >= 100:
                loop_nr = 1
            if my_debug:
                print(TAG+f"loop nr: {loop_nr}")
            if not wifi_is_connected(state):
                if not my_debug:
                    print(TAG+"going to establish a WiFi connection...")
                do_connect(state)
            if wifi_is_connected(state):  # Check again.
                if state.board_id == 'unexpectedmaker_feathers3':
                    if state.use_neopixel and not grn_set:
                        grn_set = True
                        r,g,b = feathers3.rgb_color_wheel( state.GRN )
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
                    if state.board_id  == 'unexpectedmaker_feathers3':
                        if neopixel and not red_set:
                            red_set = True
                            r,g,b = feathers3.rgb_color_wheel( state.RED )
                            pixels[0] = ( r, g, b, state.neopixel_brightness)
                            pixels.write()
            time.sleep(2)
            if state.lStart:
                state.lStart = False
                msg = ['NTP date:', pr_dt(state, True, 0), pr_dt(state, True, 2)]
                pr_msg(state, msg)
                upd_SRAM(state)
                say_hello(True)
                state.lStart = False
                clr_scrn()
            else:
                #sys.exit()
                say_hello(False)  # Was: False
                upd_SRAM(state)
        except KeyboardInterrupt:
            wifi.radio.stop_station()
            r,g,b = feathers3.rgb_color_wheel( state.BLK )
            pixels[0] = ( r, g, b, state.neopixel_brightness)
            pixels.write()
            print("KeyboardInterrupt. Exiting...")
            sys.exit()
        except Exception as e:
            print("Error", e)
            raise

if __name__ == '__main__':
    main()

