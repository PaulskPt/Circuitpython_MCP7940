#
# Downloaded from: https://github.com/tinypico/micropython-mcp7940/blob/master/mcp7940.py
# On 2022-02-27
# Following are modifications by @Paulskpt (GitHub)
# Added global debug flag `my_debug`
# In class MCCP7940, the following functions added by @Paulskpt:
# - set_12hr()
# - is_12hr()
# - is_PM()
# - weekday_N()
# - weekday_S()
# - yearday()
# - _clr_SQWEN_bit()
# - _read_SQWEN_bit()
# - _set_ALMPOL_bit()
# - _clr_ALMPOL_bit()
# - _read_ALMPOL_bit()
# - _read_ALMxIF_bit()
# - _clr_ALMxIF_bit()
# - _read_ALMxMSK_bits()
# - _set_ALMxMSK_bits()
# - pwr_updn_dt()
# - clr_SRAM()
# - write_to_SRAM()
# - read_fm_SRAM()
# - pr_regs()
#
# Added dictionaries: DOW, DOM and bits_dict
# Added self._match_lst 
# In functions start() and stop() added functionality to wait for the osc_run_bit to change (See the MC=7940  datasheet DS20005010H-page 15, Note 2)
# For this in function time() (Setter) I added calls to stop() and start() before and after writing a new time to the MC7940 RTC.
# Be aware when setting an alarm time one loses the state ALMPOL bit, the ALMxIF bit and the three ALMxMSK bits. 
# Thus when setting an alarm make sure to set ALMPOL, ALMx1F and ALMxMSK for alarm1 and/or alarm2 in your code.py script. 
# See the example in function set_alarm() in my code.py example.
# For the sake of readability: replaced index values like [0] ...[6] with [RTCSEC] ... [RTCYEAR]
#
# About clearing the alarm Interrupt Flag bit (ALMxIF). 
# See MCP7940 datasheet  DS20005010H-page 23, note 2
# See also paragraph 5.4.1 on page 21
# Writing to the ALMxWKDAY register will always clear the ALMxIF bit.
# This is what we do in function _clr_ALMxIF_bit().
#
from micropython import const

# Added by @PaulskPt from CPY > Frozen > adafruit_register > example register_rwbit.py
from board import SCL, SDA
from busio import I2C
import time
my_debug = False

class MCP7940:
    """
        Example usage:

            # Read time
            mcp = MCP7940(i2c)
            time = mcp.time # Read time from MCP7940
            is_leap_year = mcp.is_leap_year() # Is the year in the MCP7940 a leap year?

            # Set time
            ntptime.settime() # Set system time from NTP
            mcp.time = utime.localtime() # Set the MCP7940 with the system time
    """

    ADDRESS = const(0x6F)       # '11001111'
    CONTROL_BYTE = 0xde # '1101 1110'
    
    
    CONTROL_REGISTER = 0x00  # control register on the MCP7940
    RTCC_CONTROL_REGISTER = 0X07
    REGISTER_ALARM0  = 0x0A 
    REGISTER_ALARM1  = 0x11
    REGISTER_PWR_FAIL = 0x18

    SRAM_START_ADDRESS = 0x20  # a SRAM space on the MCP7940
    
    # MCP7940 registers
    RTCSEC = 0x00 # RTC seconds register
    RTCMIN = 0x01
    RTCHOUR = 0x02
    RTCWKDAY = 0x03  # RTC Weekday register
    RTCDATE = 0x04
    RTCMTH = 0x05
    RTCYEAR = 0x06
    PWRDN_ADDRESS = 0X18
    PWRUP_ADDRESS = 0x1C
    PWRMIN = 0x00 # reg 0x1C
    PWRHOUR = 0x01 # reg 0x1D
    PWRDATE = 0x02 # reg 0x1E
    PWRMTH = 0x03 # reg 0x1F
    FAIL_BIT = 4
    OSCRUN_BIT = 5
    ALARM0EN_BIT = 4 
    ALARM1EN_BIT = 5
    SQWEN_BIT = 6
    ALMPOL_BIT = 7
    ALMxIF_BIT = 3
    ST = 7  # Status bit
    VBATEN = 3  # External battery backup supply enable bit
    
    bits_dict = {3: "VBATEN",
                 4: "FAIL",
                 7: "STATUS"}
    
    # Definitions added by @PaulskPt
    TIME_AND_DATE_START = 0X00
    PWR_FAIL_REG = 0X03
    TIME_AND_DATE_END = 0X06
    CONFIG_START = 0X07
    CONFIG_END = 0X09
    ALARM1_START = 0X0A
    ALARM1_END = 0X10
    ALARM2_START = 0X11
    ALARM2_END = 0X18
    POWER_FAIL_TIMESTAMP_START = 0X18
    POWER_FAIL_TIMESTAMP_END = 0X1F
    SRAM_START = 0X20  # 64 Bytes
    SRAM_END = 0X5F
    
    # From MCP7940 Datasheet DS20005010H-page 15
    """
    The day of week value counts from 1 to 7, increments
    at midnight, and the representation is user-defined (i.e.,
    the MCP7940N does not require 1 to equal Sunday,
    etc.)
    """

    """ Dictionary added by @Paulskpt. See weekday_S() """
    DOW = { 1: "Monday",
            2: "Tuesday",
            3: "Wednesday",
            4: "Thursday",
            5: "Friday",
            6: "Saturday",
            7: "Sunday" }
    
    DOM = { 1:31,
            2:28,
            3:31,
            4:30,
            5:31,
            6:30,
            7:31,
            8:31,
            9:30,
            10:31,
            11:30,
            12:31}
    
    def __init__(self, i2c, status=True, battery_enabled=True):
        self._i2c = i2c
        # lines added by @PaulskPt
        self._status = status
        self.battery_enabled = battery_enabled
        self._numregs = 16
        self.dt_sram = bytearray()
        self.year_day = 0
        self.is_dst = 0
        self._match_lst = ["ss", "mm", "hh", "dow", "dd", "res", "res", "all"]
        
    def has_power_failed(self):
        return True if self._read_bit(MCP7940.PWR_FAIL_REG, MCP7940.FAIL_BIT) else False
    
    def clr_pwr_fail_bit(self):
        self._set_bit(MCP7940.PWR_FAIL_REG, MCP7940.FAIL_BIT, 0)
    
    def start(self):
        ads = 0x3
        self._set_bit(MCP7940.RTCSEC, MCP7940.ST, 1)
        while True:
            osc_run_bit = self._read_bit(ads, MCP7940.OSCRUN_BIT)
            if my_debug:
                print(f"MCP7940.start(): osc_run_bit: {osc_run_bit}")
            if osc_run_bit:
                break

    def stop(self):
        ads = 0x3
        self._set_bit(MCP7940.RTCSEC, MCP7940.ST, 0)
        while True:
            osc_run_bit = self._read_bit(ads, MCP7940.OSCRUN_BIT)
            if my_debug:
                print(f"MCP7940.stop(): osc_run_bit: {osc_run_bit}")
            if not osc_run_bit:
                break

    def is_started(self):
        return self._read_bit(MCP7940.RTCSEC, MCP7940.ST)

    def battery_backup_enable(self, enable):
        self._set_bit(MCP7940.RTCWKDAY, MCP7940.VBATEN, enable)

    def is_battery_backup_enabled(self):
        return self._read_bit(MCP7940.RTCWKDAY, MCP7940.VBATEN)

    def _set_bit(self, register, bit, value):
        """ Set only a single bit in a register. To do so, need to read
            the current state of the register and modify just the one bit.
        """
        TAG = "MCP7940._set_bit():     "
        mask = 1 << bit
        #current = self._i2c.readfrom_mem(MCP7940.ADDRESS, register, 1)
        current = bytearray(1)
        current2 = bytearray(1)
        reg_buf = bytearray()
        reg_buf.append(register)
        out_buf = bytearray()
        out_buf.append(register)
        if my_debug:
            print(TAG+f"params: register: {register}, bit: {bit}, value: {value}")
        try:
            while not self._i2c.try_lock():
                pass
            
            self._i2c.writeto_then_readfrom(MCP7940.ADDRESS, reg_buf, current) 
                            
        except OSError as e:
            print(TAG+f"Error: {e}")
        finally:
            self._i2c.unlock()
            #pass
        
        if my_debug:
            print(TAG+f"Current register nr {hex(register)} value from RTC: {hex(current[0])}")      
        updated = (current[0] & ~mask) | ((value << bit) & mask)

        out_buf.append(updated)
        if my_debug:
            print(TAG+f"writing to RTC register nr {hex(register)} updated value: {out_buf}")
        lst = list(out_buf)
        le = len(lst)
        if my_debug:
            print(TAG+f"lst: {lst}, le: {le}")
            print(TAG+f"writing to RTC register nr {hex(register)} updated value: ", end='')
            for _ in range(le):
                print("0x{:02x} ".format(lst[_]), end='')
            print()
        
            print(TAG+f"first call to self._i2c.writeto(). Address to write to: {hex(MCP7940.ADDRESS)}")
        
        try:
            while not self._i2c.try_lock():
                pass
        
            self._i2c.writeto(MCP7940.ADDRESS, out_buf)  # send data
        except OSError as e:
            print(TAG+f"Error: {e}")
        finally:
            self._i2c.unlock()
            #pass       

        # Check the result:
        if my_debug:
            print(TAG+"second call to self._i2c.writeto()")
        try:
            while not self._i2c.try_lock():
                pass
            self._i2c.writeto_then_readfrom(MCP7940.ADDRESS, reg_buf, current2)
        except OSError as e:
            print(TAG+f"Error: {e}")
        finally:
            self._i2c.unlock()
            #pass       
    
        if my_debug:
            print(TAG+f"received (updated bits) from RTC: {hex(current2[0])}")      
        

    def _read_bit(self, register, bit):
        TAG="MCP7940._read_bit():    "
        register_val = bytearray(1)
        reg_buf = bytearray()
        reg_buf.append(register)
        if bit in MCP7940.bits_dict.keys():
            sb = MCP7940.bits_dict[bit]
        else:
            sb = bit
        if my_debug:
            print(TAG+f"params: register: {register}, bit: {sb}")
        try:
            while not self._i2c.try_lock():
                pass
            self._i2c.writeto(MCP7940.ADDRESS, reg_buf)  # send request for register ...
            self._i2c.readfrom_into(MCP7940.ADDRESS, register_val)

        except OSError as e:
            print(TAG+f"Error: {e}")
        finally:
            self._i2c.unlock()
            #pass
        
        ret = (register_val[0] & (1 << bit)) >> bit
        if my_debug:
            print(TAG+f"received from RTC register: {hex(register)}, bit nr: {bit}, (register_val): {register_val}. func return value: {ret}")
        return ret

    @property
    def time(self):
        return self._get_time()

    @time.setter
    def time(self, t):
        """
            >>> import time
            >>> time.localtime()
            (2019, 6, 3, 13, 12, 44, 0)
            # 1:12:44pm on Monday (0) the 3 Jun 2019
        """
        TAG = "MCP7940.time():         "
        if my_debug:
            print(TAG+f"setter: param t: {t}")
        year, month, date, hours, minutes, seconds, weekday = t
        # Reorder
        time_reg = [seconds, minutes, hours, weekday, date, month, year % 100]
        print(TAG+f"time_reg:{time_reg}")

        # Add ST (status) bit

        # Add VBATEN (battery enable) bit
        if my_debug:
            print(TAG+
                "{}/{}/{} {}:{}:{} (weekday {} = {})".format(
                    time_reg[MCP7940.RTCYEAR],
                    time_reg[MCP7940.RTCMTH],
                    time_reg[MCP7940.RTCDATE],
                    time_reg[MCP7940.RTCHOUR],
                    time_reg[MCP7940.RTCMIN],
                    time_reg[MCP7940.RTCSEC],
                    time_reg[MCP7940.RTCWKDAY],
                    MCP7940.DOW[time_reg[MCP7940.RTCWKDAY]],
                )
            )
        
        #print(time_reg)
        reg_filter = (0x7F, 0x7F, 0x3F, 0x07, 0x3F, 0x3F, 0xFF)
        """ Note @Paulskpt zip() is a built-in function of micropython (and in circuitpython!). Works as follows:
            >>> x = [1, 2, 3]
            >>> y = [4, 5, 6]
            >>> zipped = zip(x,y)
            >>> list(zipped)
            [(1, 4), (2, 5), (3, 6)]"""
            
        out_buf = bytearray()
        out_buf.append(MCP7940.CONTROL_REGISTER)
        t = [(self.int_to_bcd(reg) & filt) for reg, filt in zip(time_reg, reg_filter)]

        for _ in range(len(t)):
            out_buf.append(t[_])

        # Note that some fields will be overwritten that are important!
        # fixme!  From @PaulskPt 2023-10-07: fixed|
  
        if my_debug:
            ck_dt = ()
            for _ in range(len(out_buf)):
                ck_dt += (self.bcd_to_int(out_buf[_]),)
            print(TAG+f"writing out_buf: {out_buf}, list(ck_dt): {ck_dt}") # in ck_dt skip the first byte which is the registry address
        
        self.stop()  # See:  MCP7940 DATASHEET: DS20005010H-page 15

        try:
            while not self._i2c.try_lock():
                pass
            self._i2c.writeto(MCP7940.ADDRESS, out_buf)
    
        except OSError as e:
            print(TAG+f"Error: {e}")
        finally:
            self._i2c.unlock()
            
        self.start()
    
    # See MCP7940 Datasheet DS20005010H-page 17    
    def set_12hr(self, _12hr=None):
        if _12hr is None:
            return
        if not isinstance(_12hr, bool):
            return
        bit = 6
        reg = MCP7940.RTCHOUR
            
        self._set_bit(reg, bit, _12hr)
    
    # See MCP7940 Datasheet DS20005010H-page 17
    def is_12hr(self):
        bit = 6
        reg = MCP7940.RTCHOUR
        return self._read_bit(reg, bit)
    
    # See MCP7940 Datasheet DS20005010H-page 17
    def is_PM(self):
        ret = ""
        if self.is_12hr():
            bit = 5
            reg = MCP7940.RTCHOUR
            ret = "PM" if self._read_bit(reg, bit) else "AM"
        return ret 
    
    # See datasheet  DS20005010H-page 26
    def alarm_enable(self, alarm_nr= None, onoff = False):
        if alarm_nr is None:
            return
        if not alarm_nr in [1, 2]:
            return
        if not isinstance(onoff, bool):
            return
        
        reg = MCP7940.RTCC_CONTROL_REGISTER
        
        if alarm_nr == 1:
            bit = MCP7940.ALARM0EN_BIT
        elif alarm_nr == 2:
            bit = MCP7940.ALARM1EN_BIT
        
        value = 1 if onoff else 0
        
        self._set_bit(reg, bit, value)

    def alarm_is_enabled(self, alarm_nr=None):
        if alarm_nr is None:
            return
        if not alarm_nr in [1, 2]:
            return
        
        reg = MCP7940.RTCC_CONTROL_REGISTER
        
        if alarm_nr == 1:
            bit = MCP7940.ALARM0EN_BIT
        elif alarm_nr == 2:
            bit = MCP7940.ALARM1EN_BIT
        
        return self._read_bit(reg, bit)
    
    @property
    def alarm1(self):
        return self._get_time(start_reg=MCP7940.ALARM1_START)

    @alarm1.setter
    def alarm1(self, t):
        TAG = "alarm1(): "
        if my_debug:
            print(TAG+f"setting alarm1 to: {t}")
        le = len(t)
        if le == 8:
            _, month, date, hours, minutes, seconds, weekday, _ = t  # Don't need year or yearday
        elif le == 6:
            month, date, hours, minutes, seconds, weekday = t
        # Reorder
        time_reg = [seconds, minutes, hours, weekday, date, month]
        reg_filter = (0x7F, 0x7F, 0x3F, 0x07, 0x3F, 0x3F)  # No year field for alarms
        out_buf = bytearray()
        out_buf.append(MCP7940.ALARM1_START)
        t = [(self.int_to_bcd(reg) & filt) for reg, filt in zip(time_reg, reg_filter)]
        for _ in range(len(t)):
            out_buf.append(t[_])
        
        while not self._i2c.try_lock():
            pass
        if my_debug:
            print(TAG+f"writing to alarm1: {list(out_buf)}")
        self._i2c.writeto(MCP7940.ADDRESS, out_buf) 

        self._i2c.unlock()
        
    @property
    def alarm2(self):
        return self._get_time(start_reg=MCP7940.ALARM2_START)

    @alarm2.setter
    def alarm2(self, t):
        TAG = "alarm2(): "
        if my_debug:
            print(TAG+f"setting alarm2 to: {t}")
        le = len(t)
        if le == 8:
            _, month, date, hours, minutes, seconds, weekday, _ = t  # Don't need year or yearday
        elif le == 6:
            month, date, hours, minutes, seconds, weekday = t
        # Reorder
        time_reg = [seconds, minutes, hours, weekday, date, month]
        reg_filter = (0x7F, 0x7F, 0x3F, 0x07, 0x3F, 0x3F)  # No year field for alarms
        out_buf = bytearray()
        out_buf.append(MCP7940.ALARM2_START)
        t = [(self.int_to_bcd(reg) & filt) for reg, filt in zip(time_reg, reg_filter)]
        for _ in range(len(t)):
            out_buf.append(t[_])
            
        while not self._i2c.try_lock():
            pass
        if my_debug:
            print(TAG+f"writing to alarm2: {list(out_buf)}")
        self._i2c.writeto(MCP7940.ADDRESS, out_buf) 
        
        self._i2c.unlock()

    def bcd_to_int(self, bcd):
        """ Expects a byte encoded with 2x 4bit BCD values. """
        # Alternative using conversions: int(str(hex(bcd))[2:])
        return (bcd & 0xF) + (bcd >> 4) * 10 

    def int_to_bcd(self, i):
        return (i // 10 << 4) + (i % 10)

    def is_leap_year(self, year):
        """ https://stackoverflow.com/questions/725098/leap-year-calculation """
        if (year % 4 == 0 and year % 100 != 0) or year % 400 == 0:
            return True
        return False
    
    def weekday_N(self):
        """ Function added by @Paulskpt """
        dt = self._get_time()
        le = len(dt)
        return dt[le-1:][0] # dt[le-1:] results in tuple: (0,) so we have to extract the first element.
    
    def weekday_S(self):
        """ Function added by @Paulskpt """       
        return MCP7940.DOW[self.weekday_N()]
    
    def yearday(self, dt0=None):
        """ Function added by @Paulskpt """
        if my_debug:
            print(f"yearday(): param dt0: {dt0}")
        if self.year_day != 0:
            return self.year_day
        
        if dt0 is not None: 
            # Prevent 'hang' when called fm self._get_time(),
            # by having self._get_time() furnish dt stamp
            # Slicing [:3]. We need only year, month and mday
            dt = dt0[:3]
        else:
            dt = self._get_time()[:3]
        ndays = 0
        curr_yr = dt[0]
        curr_mo = dt[1]
        curr_date = dt[2]
        for _ in range(1, curr_mo):
            try:
                ndays += MCP7940.DOM[_]
                if _ == 2 and self.is_leap_year(curr_yr):
                    ndays += 1
            except KeyError:
                pass
        ndays += curr_date
        yearday = ndays
        return ndays
    
    def _is_pwr_failure(self):
        time_reg = bytearray()  # added by @PaulskPt
        time.reg.append(MCP7940.REGISTER_PWR_FAIL)
        if my_debug:
            print(f"_is_pwr_failure(): state power failure register: {time_reg}")
        
    def _clr_pwr_failure_bit(self):
        pwr_bit = bytearray(1)
        pass
    
    def _clr_SQWEN_bit(self):
        self._set_bit(0x07, MCP7940.SQWEN_BIT, 0)
        
    def _read_SQWEN_bit(self):
        return self._read_bit(0x07, MCP7940.SQWEN_BIT)
        
    def _set_ALMPOL_bit(self, alarm_nr=None):
        if alarm_nr is None:
            return
        if not alarm_nr in [1, 2]:
            return
        if alarm_nr == 1:
            ads = 0x0D
        elif alarm_nr == 2:
            ads = 0x14
        self._set_bit(ads, MCP7940.ALMPOL_BIT, 1)
        if my_debug:
            ck_bit = self._read_ALMPOL_bit(alarm_nr)
            print("MCP7940._set_ALMPOL_bit() for alarm{:d}: check: b\'{:b}\'".format(alarm_nr, ck_bit))
        
    def _clr_ALMPOL_bit(self, alarm_nr=None):
        if alarm_nr is None:
            return
        if not alarm_nr in [1, 2]:
            return
        if alarm_nr == 1:
            ads = 0x0D
        elif alarm_nr == 2:
            ads = 0x14
        if my_debug:
            print("MCP7940._clr_ALMPOL_bit() for alarm{:d}: we passed here. Line 504".format(alarm_nr))
        self._set_bit(ads, MCP7940.ALMPOL_BIT, 0)
        
    def _read_ALMPOL_bit(self, alarm_nr=None):
        if alarm_nr is None:
            return
        if not alarm_nr in [1, 2]:
            return
        if alarm_nr == 1:
            ads = 0x0D
        elif alarm_nr == 2:
            ads = 0x14
        ret =  self._read_bit(ads, MCP7940.ALMPOL_BIT)
        if my_debug:
            print("MCP7940._read_AMPOL_bit for alarm{:d}, value: b\'{:b}\'".format(alarm_nr, ret))
        return ret
    
    def _read_ALMxIF_bit(self, alarm_nr=None):
        if alarm_nr is None:
            return
        if not alarm_nr in [1, 2]:
            return
        if alarm_nr == 1:
            ads = 0x0D
        elif alarm_nr == 2:
            ads = 0x14
        return self._read_bit(ads, MCP7940.ALMxIF_BIT)
    
    # See MCP7940 datasheet  DS20005010H-page 23, note 2
    # Writing to the ALMxWKDAY register will always clear the ALMxIF bit.
    # This is what we do in _clr_ALMxIF_bit() below:
    def _clr_ALMxIF_bit(self, alarm_nr=None):
        TAG = "MCP7940._clr_ALMxIF_bit():  "
        if alarm_nr is None:
            return
        if not alarm_nr in [1, 2]:
            return
        
        if alarm_nr == 1:
            ads = 0x0D
        elif alarm_nr == 2:
            ads = 0x14

        current = bytearray(1)
        reg_buf = bytearray()
        reg_buf.append(ads)
        out_buf = bytearray()
        out_buf.append(ads)

        try:
            while not self._i2c.try_lock():
                pass
            self._i2c.writeto_then_readfrom(MCP7940.ADDRESS, reg_buf, current)
        except OSError as e:
            print(TAG+f"Error: {e}")
            return 0
        finally:
            self._i2c.unlock()
            #pass
            
        if my_debug:
            print(TAG+"received ALM{:d} weekday value register: lst(current): {}, value: 0x{:0x}, in binary: b\'{:08b}\'". \
                format(alarm_nr, list(current), current[0], current[0]))
        updated = current[0]
        updated = updated & 0xF7 # clear the ALMxIF bit
        out_buf.append(updated)
        
        if my_debug:
            print(TAG+"writing value, hex: 0x{:02x}, binary: b\'{:08b}\'".format(updated, updated) )
            
        try:
            while not self._i2c.try_lock():
                pass 
            self._i2c.writeto(MCP7940.ADDRESS, out_buf)  # send data
        except OSError as e:
            print(TAG+f"Error: {e}")
            return 0
        finally:
            self._i2c.unlock()
            #pass
        reg_buf = bytearray()
        reg_buf.append(ads)
        ck_buf = bytearray(1)
        try:
            while not self._i2c.try_lock():
                pass
            self._i2c.writeto_then_readfrom(MCP7940.ADDRESS, reg_buf, ck_buf)
            ck_if_bit = ck_buf[0]
            ck_if_bit2 = ck_if_bit & 0x7F # isolate b3
            ck_if_bit2 = ck_if_bit2 >> 3  # shift b3 to b0
            if my_debug:
                print(TAG+"check weekday value register rcvd 2nd time: 0x{:02x}, IF bit: hex: 0x{:x}, binary: b\'{:b}\'". \
                    format(ck_if_bit, ck_if_bit2, ck_if_bit2))
                print()
        except OSError as e:
            print(TAG+f"Error: {e}")
            return 0
        finally:
            self._i2c.unlock()
            #pass
    
    def _read_ALMxMSK_bits(self, alarm_nr= None):
        TAG= "MCP7940._read_ALMxMSK_bits(): "
        if alarm_nr is None:
            return
        if not alarm_nr in [1, 2]:
            return
        if alarm_nr == 1:
            ads = 0x0D
        elif alarm_nr == 2:
            ads = 0x14
        ret = 0
        reg_buf = bytearray()
        reg_buf.append(ads)
        current = bytearray(1)
        
        try:
            while not self._i2c.try_lock():
                pass
            self._i2c.writeto_then_readfrom(MCP7940.ADDRESS, reg_buf, current)
        except OSError as e:
            print(TAG+f"Error: {e}")
            return 0
        finally:
            self._i2c.unlock()
            #pass
        
        ret = current[0] & 0x70 # isolate bits 6-4
        ret = ret >> 4
        
        if my_debug and ret >= 0 and ret <= 7:
            print(TAG+f"ret: {hex(ret)}, type of match: {self._match_lst[ret]}")
        return ret
    
    def _set_ALMxMSK_bits(self, alarm_nr= None, match_type=None):
        TAG = "MCP7940._set_ALMxMSK_bits(): "
        if alarm_nr is None:
            return
        if not alarm_nr in [1, 2]:
            return
        if match_type is None:
            return
        #
        # match type
        # b7 b6 b5 b4 b3 b2 b1 b0
        #  x  0  0  1  x  x  x  x = minute
        # 
        # b'001'  match type
        # b'001'
        # ----- &
        # b'001'  result
        #
        # 
        # b'001'  match type
        # b'010'
        # ----- &
        # b'000'  result
        #
        # current2
        # b'001'  match type
        # b'100'
        # ----- &
        # b'000'  result
        #
        if alarm_nr == 1:
            ads = 0x0D
        elif alarm_nr == 2:
            ads = 0x14
        if match_type >= 0 and match_type <= 7:
            mask = match_type << 4 # minutes
        else:
            mask = 0x00 << 4 # seconds
        
        current = bytearray(1)
        reg_buf = bytearray()
        reg_buf.append(ads)
        out_buf = bytearray()
        out_buf.append(ads)
        
        try:
            while not self._i2c.try_lock():
                pass
            self._i2c.writeto_then_readfrom(MCP7940.ADDRESS, reg_buf, current)
        except OSError as e:
            print(TAG+f"Error: {e}")
            return 0
        finally:
            self._i2c.unlock()
            #pass
            
        if my_debug:
            print(TAG+"received ALM{:d}MSK_bits: lst(current): {}, value: 0x{:x}, binary: b\'{:b}\'". \
                format(alarm_nr, list(current), current[0], current[0]))
        updated = current[0]
        updated &= 0x8F  # mask bits b6-b4
        updated |= mask  # set for minutes
        out_buf.append(updated)
        if my_debug:
            print(TAG+"writing value: {:02x}, binary: b\'{:b}\'".format(updated, updated))
            new_match_value = updated & 0x70 # isolate bits 6-4
            new_match_value = new_match_value >> 4
            print(TAG+f"= new_match_value: {new_match_value} = {self._match_lst[new_match_value]}")
            
        try:
            while not self._i2c.try_lock():
                pass
            self._i2c.writeto(MCP7940.ADDRESS, out_buf)  # send data
        except OSError as e:
            print(TAG+f"Error: {e}")
            return 0
        finally:
            self._i2c.unlock()
            #pass
        reg_buf = bytearray()
        reg_buf.append(ads)
        ck_buf = bytearray(1)
        try:
            while not self._i2c.try_lock():
                pass
            self._i2c.writeto_then_readfrom(MCP7940.ADDRESS, reg_buf, ck_buf)
            if my_debug:
                print(TAG+"check: list(ck_buf) {}, ck_buf[0] value: 0x{:02x}, binary: b\'{:08b}\'". \
                    format(list(ck_buf), ck_buf[0], ck_buf[0]))
        except OSError as e:
            print(TAG+f"Error: {e}")
            return 0
        finally:
            self._i2c.unlock()
            #pass
        if my_debug and match_type >= 0 and match_type <= 7:
            print(TAG+"match type value set: 0x{:02x}, type of match: {:s}". \
                format(match_type, self._match_lst[match_type]))
            print()
    
    def _get_time(self, start_reg = 0x00):
        TAG = "MCP7940._get_time():   "
        num_registers = 7 if start_reg == 0x00 else 6
        time_reg = bytearray(num_registers)  # added by @PaulskPt
        reg_buf = bytearray()
    
        if start_reg == MCP7940.CONTROL_REGISTER:
            r = "control"
            reg_buf.append(MCP7940.CONTROL_REGISTER)
        
        elif start_reg == MCP7940.SRAM_START_ADDRESS:
            r = "sram"
            time_reg[0] = MCP7940.SRAM_START_ADDRESS
        
        elif start_reg == MCP7940.ALARM1_START:
            r = "alarm0"
            reg_buf.append(MCP7940.ALARM1_START)
        
        elif start_reg == MCP7940.ALARM2_START:
            r = "alarm1"
            reg_buf.append(MCP7940.ALARM2_START)
        
        elif start_reg == MCP7940.REGISTER_PWR_FAIL:
            r = "prw_fail"
            reg_buf.append(MCP7940.REGISTER_PWR_FAIL) 
        
        else:
            r = "default"
            reg_buf.append(MCP7940.CONTROL_REGISTER)  # default
        
        if my_debug:
            print(TAG+f"using the MCP7940 {r} register")
            print(TAG+f"reg_buf: {reg_buf}, list(reg_buf): ", end='')
            lst = list(reg_buf)
            le = len(lst)
            print("[", end='')
            for _ in range(le):
                print(f"{hex(lst[_])}", end='')
                if _ < le-1:
                    print(", ", end='')
            print("]", end='\n')
            print(TAG+f"time_reg: {time_reg}, list(time_reg): {list(time_reg)}")
            
        try:
            while not self._i2c.try_lock():
                pass
            self._i2c.writeto_then_readfrom(MCP7940.ADDRESS, reg_buf, time_reg)
            if my_debug:
                print(TAG+"received following datetime data from MCP7940:")
                print(f"{time_reg}")
                print()
        except OSError as e:
            print(TAG+f"Error: {e}")
            return 0
        finally:
            self._i2c.unlock()
            #pass
        
        reg_filter = (0x7F, 0x7F, 0x3F, 0x07, 0x3F, 0x3F, 0xFF)[:num_registers]
        if my_debug:
            print(TAG+f"time_reg: {time_reg}")
            print(TAG+f"reg_filter: {reg_filter}")
        t = [self.bcd_to_int(reg & filt) for reg, filt in zip(time_reg, reg_filter)]

        # Reorder
        t2 = (t[MCP7940.RTCMTH], t[MCP7940.RTCDATE], t[MCP7940.RTCHOUR], \
              t[MCP7940.RTCMIN], t[MCP7940.RTCSEC],  t[MCP7940.RTCWKDAY])
        t3 = (t[MCP7940.RTCYEAR] + 2000,) + t2 if num_registers == 7 else t2
        if my_debug:
            print(TAG+f"t: {t}")
        
        # now = (2019, 7, 16, 15, 29, 14, 6, 167)  # Sunday 2019/7/16 3:29:14pm
        # year, month, date, hours, minutes, seconds, weekday = t
        # time_reg = [seconds, minutes, hours, weekday, date, month, year % 100]

        if self.year_day == 0:
            yrday = self.yearday(t3)
            if my_debug:
                print(f"yearday rcvd from within _get_time(): {yrday}")
            self.year_day = yrday # Set yearday
        else:
            yrday = self.year_day
            
        if self.is_dst == 0:
            isdst = -1
            self.is_dst = isdst
        else:
            isdst = self.is_dst
        
        t3 += (yrday, isdst)  # add yearday and isdst to datetime stamp
        
        if my_debug:
            print(TAG+f"result: {t3}")
        return t3
    
    def pwr_updn_dt(self, pwr_updn=True): # power up is default
        TAG="get_pwr_up_dt():         "
        reg_buf = bytearray()
        if pwr_updn:
            reg_buf.append(MCP7940.PWRUP_ADDRESS)
        else:
            reg_buf.append(MCP7940.PWRDN_ADDRESS)
        num_registers = 4
        time_reg = bytearray(num_registers)
        
        try:
            while not self._i2c.try_lock():
                pass
            
            self._i2c.writeto_then_readfrom(MCP7940.ADDRESS, reg_buf, time_reg)
            if my_debug:
                s = "up" if pwr_updn else "down"
                print(TAG+f"received MCP7940 power {s} timestamp: {list(time_reg)}")
            
        except OSError as e:
            print(TAG+f"Error: {e}")
            return 0
        finally:
            self._i2c.unlock()
            #pass
        #             min   hr    date  wd/month
        reg_filter = (0x7F, 0x3F, 0x3F, 0xFF)[:num_registers]
        if my_debug:
            print(TAG+f"time_reg: {time_reg}")
            print(TAG+f"reg_filter: {reg_filter}")
        t = [self.bcd_to_int(reg & filt) for reg, filt in zip(time_reg, reg_filter)]

        # extract 12/24  flag (True = 12, False = 24)
        _12hr = t[MCP7940.PWRMIN] & 0x40 # (0x40 = 0100 0000)
        _12hr = _12hr >> 6 # move b01000000 to b00000001
        # print(TAG+"{:s} hour format".format("12" if _12hr else "24")))
        # AM/PM flag (True = PM, False = AM)
        _AMPM = t[MCP7940.PWRMIN] & 0x20 # (0x20 = 0010 0000)
        _AMPM = _AMPM >> 5 # move b00100000 to b00000001
        #if _12hr:
        #    print("time: {:s}".format("PM" if _AMPM else "AM"))
        
        # extract weekday:
        wd  = t[MCP7940.PWRMTH] & 0xE0  # (0xE0 = b1110 0000)
        wd = wd >> 5  # move b11100000 to b00000111
        # extract month
        mth = t[MCP7940.PWRMTH] & 0x1F  # (0x1F = b0001 1111)
        if my_debug:
            print(TAG+f"t: {t}")
        # Reorder
        t2 = (mth, t[MCP7940.PWRDATE], t[MCP7940.PWRHOUR], t[MCP7940.PWRMIN], wd)
       
        if _12hr:
            t3 = "PM" if _AMPM else "AM"
            t2 += (t3,) 
        else:
            t3 = ""
            
        if my_debug:
            print(TAG+f"result: {t2} {t3}")

        return t2
    
    def clr_SRAM(self):
        TAG = "clr_SRAM(): "
        reg_buf = bytearray()
        reg_buf.append(MCP7940.SRAM_START_ADDRESS)
        out_buf = bytearray()
        out_buf.append(MCP7940.SRAM_START_ADDRESS)
        for _ in range(0x40):
            out_buf.append(0x0)
        if my_debug:
            print(TAG+f"length data to write to clear SRAM data: {hex(len(out_buf-1))}")
        try:
            while not self._i2c.try_lock():
                pass
        
            self._i2c.writeto(MCP7940.ADDRESS, out_buf) 
        except OSError as e:
            print(TAG+f"Error: {e}")
        finally:
            self._i2c.unlock()
    
    def show_SRAM(self):
        TAG = "show_SRAM(): "
        reg_buf = bytearray()
        reg_buf.append(MCP7940.SRAM_START_ADDRESS)
        in_buf = bytearray(0x3F) # 0x5F-0x20+1)
        if my_debug:
            print(TAG+"Contents of SRAM:")
        try:
            while not self._i2c.try_lock():
                pass      
            self._i2c.writeto_then_readfrom(MCP7940.ADDRESS, reg_buf, in_buf)
        except OSError as e:
            print(TAG+f"Error: {e}")
        finally:
            self._i2c.unlock()
        le = len(in_buf)
        for _ in range(le):
            if _ % 10 == 0:
                if _ > 0:
                    print()
            if _ == le-1:
                s = ""
            else:
                s = ", "
            if my_debug:
                print("0x{:02x}{:s}".format(in_buf[_], s), end='')

        print()
        
    def write_to_SRAM(self, dt):
        """ Function added by @Paulskpt """
        TAG="MCP7940.write_to_SRAM():    "
        le = len(dt)
        if my_debug:
            print("\n"+TAG+f"param dt: {dt}")
            print(TAG+f"length received param dt, le: {le}")
        reg_buf = bytearray()
        reg_buf.append(MCP7940.SRAM_START_ADDRESS)
        if my_debug:
            print(TAG+f"reg_buf: {reg_buf}, hex(list(reg_buf)[0]): {hex(list(reg_buf)[0])}")
        if le >= 8:
            dt2 = dt[:7]  # only the bytes 0-6. Cut 7 and 8 because 7 is too large and 8 could be negative]
        else:
            dt2 = dt
        le2 = len(dt2)
        if my_debug:
            print(TAG+f"le2: {le2}")
        for _ in range(le2):
            if _ == 0:
                dt3 = (dt[_] - 2000,)
            else:
                dt3 += (dt[_],)
        dt3 += (self.is_12hr(),)
        if dt.tm_hour > 12:
            is_PM = 1
        else:
            is_PM = 0
        dt3 += (is_PM,)
        if my_debug:
            print("\n"+TAG+f"dt2: {dt2}")
            print(TAG+f"MCP7940.write_to_SRAM(): Writing this datetime tuple (dt3): \'{dt3}\' to user memory (SRAM)")
            
        year, month, date, hours, minutes, seconds, weekday, is_12hr, is_PM = dt3
        
        ampm = ""
        
        if is_12hr:
            if hours > 12:
                is_pm = 1
            else:
                is_pm = 0
                
                
        if my_debug:
            print(TAG+f"yy: {year}, mon: {month}, dt: {date}, \
                hr: {hours}, min: {minutes}, sec: {seconds}, {ampm}, wkday: {weekday}, is_12hr: {is_12hr}, is_PM: {is_PM}")
        # Reorder
        # Write in reversed order (as in the registers 0x00-0x06 of the MP7940)
        
        dt4 = [seconds, minutes, hours, weekday, date, month, year, is_12hr, is_PM]

        le4 = len(dt4)
        nr_bytes = le4
        if my_debug:
            print(TAG+f"dt4: {dt4}")
        out_buf = bytearray() # 
        out_buf.append(MCP7940.SRAM_START_ADDRESS)
        
        for _ in range(le4):  # don't save tm_yday (can be > 255) and don't save tm_isdst (can be negative)
            out_buf.append(dt4[_])

        le = len(out_buf)
        if my_debug:
            print(TAG+f"out_buf: {out_buf}, type: {type(out_buf)}, number of bytes to be written: {nr_bytes}")
            print(TAG+f"writing to SRAM: list(out_buf): {list(out_buf)}")
        try:
            while not self._i2c.try_lock():
                pass
            self._i2c.writeto(MCP7940.ADDRESS, out_buf)   # Write the data to SRAM
        except OSError as e:
            print(TAG+f"Error: {e}")
        finally:
            self._i2c.unlock()
            #pass
    
    def read_fm_SRAM(self):
        """ Function added by @Paulskpt """
        TAG = "MCP7940.read_fm_SRAM():     "
        if self.is_12hr():
            num_regs = 9
        else:
            num_regs = 7 # 1 address byte + 7 data bytes
        dt = bytearray(num_regs)
        reg_buf = bytearray()
        reg_buf.append(MCP7940.SRAM_START_ADDRESS)
        if my_debug:
            print(TAG+f"\nbefore reading, dt: {dt} = list(dt): {list(dt)}")
        try:
            while not self._i2c.try_lock():
                pass
            self._i2c.writeto_then_readfrom(MCP7940.ADDRESS, reg_buf, dt) 
        except OSError as e:
            print(TAG+f"Error: {e}")
            return dt
        finally:
            self._i2c.unlock()
            #pass
        dt2 = list(dt)
        if my_debug:
            print(TAG+f"received from RTC SRAM: len(dt2): {len(dt2)}, dt: ", end='\n')
        t = () # create an empty tuple
        for _ in range(len(dt2)):
            if _ == len(dt2)-3:
                t += (dt2[_]+2000,)
            else:
                t += (dt2[_],)
            if my_debug:
                print("hex: 0x{:02x}, dec: {:3d},".format(dt2[_], dt[_]), end='\n')
        if my_debug:
            print()
        
        seconds, minutes, hours, weekday, date, month, year, is_12hr, is_PM = t
        yearday = self.yearday((year,month,date))  # don't call self.yearday() from here. It seems to lock up the script
        isdst = -1
        dt2 = (year, month, date, hours, minutes, seconds, weekday, yearday, isdst, is_12hr, is_PM)
        # Reorder
        #dt2 = [year, month, date, hours, minutes, seconds, weekday]
        
        if is_12hr:
            if hours > 12:
                hours -= 12
        if is_PM:
            s_pm = "PM"
        else:
            s_pm = "AM"
        
        if my_debug:
            print(TAG+f"yy: {year}, mon: {month}, dt: {date}, hr: {hours}, min: {minutes}, \
                sec: {seconds}, {s_pm}, wkday: {weekday}, yrday: {yearday}, dst: {isdst}")

        le = len(dt)
        if my_debug:
            print(TAG+"data read: {}, type: {}, bytes read: {}".format(dt, type(dt), le))
        """
        dt2 = ()
        for _ in range(len(dt)):
            if _ == 0:
                dt2 += (dt[_]+2000,)
            else:
                  dt2 += (dt[_],)
        """
        if my_debug:
            print(TAG+"dt2: {}, type(dt2): {} ".format(dt2, type(dt2)))
            print()
        return dt2
    
    def pr_regs(self):
        # display the device values for the bits
        print(f"pr_regs(): {list(self.dt_sram)}")


    class Data:
        def __init__(self, i2c, address):
            self._i2c = i2c
            self._address = address
            self._memory_start = MCP7940.SRAM_START_ADDRESS

        def __getitem__(self, key):
            
            reg_buf = bytearray()
            reg_buf.append(self._memory_start)
            
            get_byte = bytearray(1)
            
            try:
            
                while not self._i2c.try_lock():
                    pass
            
                get_byte = lambda x: (self._i2c.writeto_then_readfrom(self.memory_start + x, get_byte), get_byte)(x)
                print(f"Data._getitem_(): get_byte: {get_byte}")
            except OSError as e:
                print(f"Data.__getitem__(): Error {e}")
            finally:
                self._i2c.unlock()
                #pass
            
            if type(key) is int:
                if my_debug:
                    print('key: {}'.format(key))
                return get_byte(key)
            elif type(key) is slice:
                if my_debug:
                    print('start: {} stop: {} step: {}'.format(key.start, key.stop, key.step))
                # fixme: Could be more efficient if we check for a contiguous block
                # Loop over range(64)[slice]
                return [get_byte(i) for i in range(64)[key]]

        def __setitem__(self, key, value):
            if type(key) is int:
                if my_debug:
                    print('key: {}'.format(key))
            elif type(key) is slice:
                if my_debug:
                    print('start: {} stop: {} step: {}'.format(key.start, key.stop, key.step))
            if my_debug:
                print(value)
