#
# Downloaded from: https://github.com/tinypico/micropython-mcp7940/blob/master/mcp7940.py
# On 2022-02-27
# Following are modifications by @Paulskpt (GitHub)
# # for Circuitpython project with Unexpected Maker ProS3
# Date 2023-10
#
from micropython import const

# Added by @PaulskPt from CPY > Frozen > adafruit_register > example register_rwbit.py
from board import SCL, SDA
from busio import I2C
import time

my_debug = False

class MCP7940:
    CLS_NAME = "MCP7940"
    ADDRESS = const(0x6F)  # '11001111'
    CONTROL_BYTE = 0xde  # '1101 1110'
    CONTROL_REGISTER = 0x00  # control register on the MCP7940
    RTCC_CONTROL_REGISTER = 0X07
    REGISTER_ALARM0  = 0x0A
    REGISTER_ALM1WKDAY = 0x0D
    REGISTER_ALARM1  = 0x11
    REGISTER_ALM2WKDAY = 0x14
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
    PWRFAIL_BIT = 4
    OSCRUN_BIT = 5
    ALARM0EN_BIT = 4 
    ALARM1EN_BIT = 5
    SQWEN_BIT = 6
    ALMPOL_BIT = 7
    ALMxIF_BIT = 3
    ST = 7  # Start Status bit
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
    
    DOW = { 0: "Monday",
            1: "Tuesday",
            2: "Wednesday",
            3: "Thursday",
            4: "Friday",
            5: "Saturday",
            6: "Sunday" }
    
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
    
    # From MCP7940 Datasheet DS20005010H-page 15
    """
    The day of week value counts from 0 to 6, increments
    at midnight, and the representation is user-defined (i.e.,
    the MCP7940N does not require 1 to equal Sunday,
    etc.)
    """
    DOW = { 0: "Monday",
            1: "Tuesday",
            2: "Wednesday",
            3: "Thursday",
            4: "Friday",
            5: "Saturday",
            6: "Sunday" }
    
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
        self._match_lst = ["ss", "mm", "hh", "dow", "dd", "res", "res", "all"]
        self._match_lst_long = ["second", "minute", "hour", "weekday", "date", "reserved", "reserved", "all"]
        self._is_12hr_fmt = -1 # Set by calling script. Default -1 to indicate it is not yet set
        self.time_is_set = False
        self.last_time_set = ()
        self.sbf = "calling self._set_bit() failed"
        self.rbf = "calling self._read_bit() failed"
        self.gtf = "calling self._mcpget_time() failed"
        self._status = status
        self._battery_enabled = battery_enabled
    
    # See datasheet: DS20005010H-page 18
    def has_power_failed(self):
        ret = True if self._read_bit(MCP7940.PWR_FAIL_REG, MCP7940.PWRFAIL_BIT) else False
        if my_debug:
            print(f"MCP7940.has_pwr_failure(): state power failure register: {ret}")
        return ret
    
    def clr_pwr_fail_bit(self):
        TAG = MCP7940.CLS_NAME+".clr_pwr_fail_bit(): "
        ret = self._set_bit(MCP7940.PWR_FAIL_REG, MCP7940.PWRFAIL_BIT, 0)
        if ret == -1:
            if my_debug:
                print(TAG+self.sbf)
        return ret

    def start(self):
        TAG = MCP7940.CLS_NAME+".start(): "
        ads = 0x3
        osc_run_bit = 0
        self._set_bit(MCP7940.RTCSEC, MCP7940.ST, 1)
        while True:
            osc_run_bit = self._read_bit(ads, MCP7940.OSCRUN_BIT)
            if osc_run_bit == 1:
                break
            elif osc_run_bit == -1:
                if my_debug:
                    print(TAG+self.rbf)
                break
            #if my_debug:
            #    print(f"MCP7940.start(): osc_run_bit: {osc_run_bit}")
        return osc_run_bit
    
    def stop(self):
        TAG = MCP7940.CLS_NAME+".stop(): "
        ads = 0x3
        osc_run_bit = 0
        self._set_bit(MCP7940.RTCSEC, MCP7940.ST, 0)
        while True:
            osc_run_bit = self._read_bit(ads, MCP7940.OSCRUN_BIT)
            # print(TAG+f"osc_run_bit: {osc_run_bit}")
            if osc_run_bit == 0:
                break
            elif osc_run_bit == -1:
                if not my_debug:
                    print(TAG+self.rbf)
                break
            #if my_debug:
            #    print(f"MCP7940.stop(): osc_run_bit: {osc_run_bit}")
    
    def _is_started(self):
        TAG = MCP7940.CLS_NAME+"._is_started(): "
        ret = self._read_bit(MCP7940.RTCSEC, MCP7940.ST)
        if ret == -1:
            if not my_debug:
                print(TAG+self.rbf)
        return ret

    def battery_backup_enable(self, enable):
        TAG = MCP7940.CLS_NAME+".battery_backup_enable(): "
        if enable is None:
            enable = self.battery_enabled  # use the value set at __init__()
        ret = self._set_bit(MCP7940.RTCWKDAY, MCP7940.VBATEN, enable)
        if ret == -1:
            if my_debug:
                print(TAG+self.sbf)
        return ret

    def _is_battery_backup_enabled(self):
        TAG = MCP7940.CLS_NAME+".is_battery_backup_enabled(): "
        ret = self._read_bit(MCP7940.RTCWKDAY, MCP7940.VBATEN)
        if ret == -1:
            if my_debug:
                print(TAG+self.rbf)
        return ret

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
            self._i2c.writeto_then_readfrom(MCP7940.ADDRESS, reg_buf, register_val)

        except OSError as e:
            print(TAG+f"Error: {e}")
        finally:
            self._i2c.unlock()
        
        ret = (register_val[0] & (1 << bit)) >> bit
        if my_debug:
            print(TAG+f"received from RTC register: {hex(register)}, bit nr: {bit}, (register_val[0]): {register_val[0]}. func return value: {ret}")
        return ret

    @property
    def mcptime(self):
        return self._mcpget_time()

    # Added calls to self.stop() and self.start()
    @mcptime.setter
    def mcptime(self, t_in):
        TAG = MCP7940.CLS_NAME+".mcptime() setter: "
        """
            >>> import time
            >>> time.localtime()
            (2019, 6, 3, 13, 12, 44, 0, 154)
            # 1:12:44pm on Monday (0) the 3 Jun 2019 (154th day of the year)
        """
        if not my_debug:
            print(TAG+f"setter: param t_in: {t_in}. len(t_in): {len(t_in)}")
        t_in = t_in[:7]  # Slice off too many bytes
        if not my_debug:
            print(TAG+f"t_in (cut): {t_in}")
        year, month, date, hours, minutes, seconds, weekday = t_in  # skip yearday
        # Reorder
        time_reg = [seconds, minutes, hours, weekday, date, month, year % 100]
        if my_debug:
            print(TAG+f"time_reg:{time_reg}")

        # Add ST (status) bit
        # is not needed. The setting of the timekeeping registers
        # contains calls to self.stop() and self.start()
        
        if not my_debug:
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
        
        out_buf = bytearray()
        out_buf.append(MCP7940.CONTROL_REGISTER)
        t = [(self.int_to_bcd(reg) & filt) for reg, filt in zip(time_reg, reg_filter)]
        for _ in range(len(t)):
            out_buf.append(t[_])
        in_buf = bytearray(len(out_buf)-1)
        if not my_debug:
            print(TAG+f"to send to MCP7940, buffer: {out_buf}, len(buffer): {len(out_buf)}")

        # Note that some fields will be overwritten that are important!
        # fixme!  From @PaulskPt 2023-10-07: fixed.
        # --------------------------------------------------------------------------------------
        # SET THE TIMEKEEPING DATA to THE MCP7940 RTC SHIELD
        # --------------------------------------------------------------------------------------
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

        # correct the fact that setting a new time clears the 12/24hr bit
        if self._is_12hr:
            self.set_12hr(self._is_12hr)
        
        
        # correct the fact that setting a new time clears the 12/24hr bit
        #if self._is_12hr:
        #    self.set_12hr(self._is_12hr)
        # --------------------------------------------------------------------------------------
        
    # Return state of the self.time_is_set flag
    # Function added to be useful for calling scripts
    # to know if the MCP7940 timekeeping registers already have been set
    def time_has_set(self):
        return self.time_is_set
    
    # Set self._is_12hr_fmt
    # This will be set from the calling program
    # Setting will not be changed from within this class
    # "s11" means "self"  (In Dutch language "eleven" = "elf")
    def set_s11_12hr(self, _12hr=None):
        TAG = MCP7940.CLS_NAME+".set_s11_12hr(): "
        if _12hr is None:
            return -1
        if my_debug:
            print(TAG+f"param _12hr: {_12hr}, type(_12hr): {type(_12hr)}")
        if not isinstance(_12hr, bool):
            return -1
        self._is_12hr_fmt =  1 if _12hr else 0
        ret = self._is_12hr_fmt
        if my_debug:
            print(TAG+f"self._is_12hr_fmt: {self._is_12hr_fmt}")
        return ret       
    
    # Set the 12hr bit and set self._is_12hr_fmt flag if not yet set    
    # See MCP7940 Datasheet DS20005010H-page 17
    # Return 0 if able to set self._is_12hr_fmt
    # We're not going to set the 12hr fmt bit in the MCP7940 hour register
    # because it appeared this did not work. Better set a flag within this class   
    def set_12hr(self, _12hr=None):
        TAG = MCP7940.CLS_NAME+".set_12hr(): "
        ret = 0
        if _12hr is None:
            return ret
        if my_debug:
            print(TAG+f"param _12hr: {_12hr}, type(_12hr): {type(_12hr)}")
        if not isinstance(_12hr, bool):
            return ret
        bit = 6
        reg = MCP7940.RTCHOUR
        value = 1 if _12hr else 0
        if self._is_12hr_fmt == -1:  # If not set yet, set it to remember
             self._is_12hr_fmt = value # Remember the settingset_PM
             ret = 1
        #if my_debug:
        #    print(f"MCOP7940.set_12hr(): setting reg: {hex(reg)}, bit {bit}, _12hr {value}")
        #ret = self._set_bit(reg, bit, value)
        #if ret == -1:
        #    print(TAG+self.sbf)
        return ret
    
    # See MCP7940 Datasheet DS20005010H-page 17
    @property
    def _is_12hr(self):
        return self._is_12hr_fmt
    
    # Return the AMPM bit is the 12hr bit is set
    # See MCP7940 Datasheet DS20005010H-page 17
    def _is_PM(self, hour):
        TAG = MCP7940.CLS_NAME+"._is_PM(): "
        ret = 0
        if hour is None:
            return ret
        if hour >= 0 and hour < 24:
            is_12hr = self._is_12hr
            if my_debug:
                print(TAG+f"self._is_12hr: {is_12hr}")
            if is_12hr:
                return 1 if hour >= 12 else 0
        return ret
    
    # Enable alarm x
    # See datasheet  DS20005010H-page 26
    def alarm_enable(self, alarm_nr= None, onoff = False):
        TAG = MCP7940.CLS_NAME+".alarm_enable(): "
        if alarm_nr is None:
            return -1
        if not alarm_nr in [1, 2]:
            return -1
        if not isinstance(onoff, bool):
            return -1
        
        reg = MCP7940.RTCC_CONTROL_REGISTER
        
        if alarm_nr == 1:
            bit = MCP7940.ALARM0EN_BIT
        elif alarm_nr == 2:
            bit = MCP7940.ALARM1EN_BIT
        
        value = 1 if onoff else 0
        
        ret = self._set_bit(reg, bit, value)
        if ret == -1:
            print(TAG+self.sbf)
        return ret
    
    # Check if alarm x is enabled
    def alarm_is_enabled(self, alarm_nr=None):
        TAG = MCP7940.CLS_NAME+"alarm_is_enabled(): "
        if alarm_nr is None:
            return
        if not alarm_nr in [1, 2]:
            return
        
        reg = MCP7940.RTCC_CONTROL_REGISTER
        
        if alarm_nr == 1:
            bit = MCP7940.ALARM0EN_BIT
        elif alarm_nr == 2:
            bit = MCP7940.ALARM1EN_BIT
        
        ret= self._read_bit(reg, bit)
        if ret == -1:
            print(TAG+self.rbf)
        return ret
    
    @property
    def alarm1(self):
        return self._mcpget_time(start_reg=MCP7940.ALARM1_START)

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
        return self._mcpget_time(start_reg=MCP7940.ALARM2_START)

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
        ret = (bcd & 0xF) + (bcd >> 4) * 10
        if my_debug:
            print(MCP7940.CLS_NAME+"bcd_to_int(): "+"bcd: {:2d}, int: {:02d}".format(bcd, ret))
        return ret

    def int_to_bcd(self, i):
        ret = (i // 10 << 4) + (i % 10)
        if my_debug:
            print(MCP7940.CLS_NAME+"int_to_bcd(): "+"int: {:2d}, bcd: {:02d}".format(i, ret))
        return ret

    """ https://stackoverflow.com/questions/725098/leap-year-calculation """
    def is_leap_year(self, year):
        if (year % 4 == 0 and year % 100 != 0) or year % 400 == 0:
            return True
        return False
    
    # Return the weekday as an integeradded by @Paulskpt """
    def weekday_N(self):
        TAG = MCP7940.CLS_NAME+".weekday_N(): "
        if my_debug:
            print(TAG+f"self.mcptime = {self.mcptime}")
        dt = self._mcpget_time()
        le = len(dt)
        if le < 2:
            if my_debug:
                print(TAG+self.gtf)
            return -1
        if my_debug:
            print(TAG+f"dt: {dt}")
        # Year, month, mday, hour, minute, second, weekday, yearday, is_12hr, isPM
        weekday = dt[6]   # slice off not needed values
        #_, _, _, _, _, _, weekday = dt # we don't need: year, month, date, hour, minute, second
        
        if my_debug:
            print(TAG+f"weekday: {weekday}")

        return weekday
    
    # Return the weekday as a string
    def weekday_S(self):
        TAG = MCP7940.CLS_NAME+".weekday_S(): "
        wd_s = ""
        wd_n = self.weekday_N()
        if wd_n == -1:
            if my_debug:
                print(TAG+"calling self.weekday_N() failed")
                return wd_s
        if wd_n in MCP7940.DOW:
            wd_s = MCP7940.DOW[wd_n]
            if my_debug:
                print(f"weekday_S(): weekday: {wd_s}")
        return wd_s
    
    
    # Calculate the yearday
    def yearday(self, dt0=None):
        TAG = MCP7940.CLS_NAME+".yearday(): "
        if my_debug:
            print(TAG+f"param dt0: {dt0}")

        if dt0 is not None: 
            # Prevent 'hang' when called fm self._mcpget_time(),
            # by having self._mcpget_time() furnish dt stamp
            # Slicing [:3]. We need only year, month and mday
            dt = dt0[:3]
        else:
            dt = self._mcpget_time()[:3]
            le = len(dt)
            if le < 2:
                if my_debug:
                    print(TAG+self.gtf)
                    return -1
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
        return ndays
    
    # See datasheet: DS20005010H-page 18
    def _is_pwr_failure(self):
        TAG = MCP7940.CLS_NAME+"._is_pwr_failure(): "
        reg = MCP7940.RTCWKDAY
        bit = MCP7940.PWRFAIL_BIT
        ret = self._read_bit(reg, bit)
        if ret == -1:
            if my_debug:
                print(TAG+self.rbf)
        else:
            if my_debug:
                print(TAG+f"power failure bit: {ret}")
        return ret
    
    # See datasheet DS20005010H-page 18, Note 2
    def _clr_pwr_failure_bit(self):
        pwr_bit = bytearray(1)
        pass

    # Clear square wave output bit
    def _clr_SQWEN_bit(self):
        TAG = MCP7940.CLS_NAME+"._clr_SQWEN_bit(): "
        ret = self._set_bit(MCP7940.RTCC_CONTROL_REGISTER, MCP7940.SQWEN_BIT, 0)
        if ret == -1:
            print(TAG+self.sbf)
        return ret
    
    # Read state of the square wave output bit
    def _read_SQWEN_bit(self):
        TAG = MCP7940.CLS_NAME+"._read_SWEN_bit(): "
        ret = self._read_bit(MCP7940.RTCC_CONTROL_REGISTER, MCP7940.SQWEN_BIT)
        if ret == -1:
            print(TAG+self.rbf)
        return ret
    
    # Read ALMxPOL, ALMxIF or ALMxMSK bit(s)   
    def _read_ALM_POL_IF_MSK_bits(self, alarm_nr=None, itm=None):
        TAG = MCP7940.CLS_NAME+"._set_ALMPOL_bit(): "
        if alarm_nr is None:
            return -1
        if itm is None:
            return -1
        if not alarm_nr in [1, 2]:
            return -1
        if not itm in [0, 1, 2]:
            return -1
        
        itm_dict = {0: "POL",
                    1: "IF",
                    2: "MSK"}
        
        if alarm_nr == 1:
            ads = MCP7940.REGISTER_ALM1WKDAY
        elif alarm_nr == 2:
            ads = MCP7940.REGISTER_ALM2WKDAY
        
        num_registers = 1
        reg_buf = bytearray()
        reg_buf.append(ads)
        current = bytearray(num_registers)
        try:
            while not self._i2c.try_lock():
                pass
            #current = self._i2c.readfrom_mem(MCP7940.ADDRESS, ads, num_registers)
            self._i2c.writeto(MCP7940.ADDRESS, reg_buf)  # send request for register ...
            self._i2c.readfrom_into(MCP7940.ADDRESS, current)
        except OSError as e:
            print(TAG+f"Error: {e}")
            return -1
        finally:
            self._i2c.unlock()
        if my_debug:
            print(TAG+f"ALM{alarm_nr}{itm_dict[itm]}_bit current: {current}")
        if itm == 0:
            ret = (current[0] & 0x80) >> 7
        elif itm == 1:
            ret = (current[0] & 0x08) >> 3
        elif itm == 2:
            ret = (current[0] & 0x70) >> 4
        
        if my_debug:
            print(TAG+"return value: {:d}, b\'{:08b}\'".format(ret, ret))
        return ret
    
    # Set the alarm pol bit for alarm x 
    def _set_ALMPOL_bit(self, alarm_nr=None):
        TAG = MCP7940.CLS_NAME+"._set_ALMPOL_bit(): "
        if alarm_nr is None:
            return -1
        if not alarm_nr in [1, 2]:
            return -1
        if alarm_nr == 1:
            ads = MCP7940.REGISTER_ALM1WKDAY
        elif alarm_nr == 2:
            ads = MCP7940.REGISTER_ALM1WKDAY
        ret = self._set_bit(ads, MCP7940.ALMPOL_BIT, 1)
        if ret == -1:
            print(TAG+self.sbf)
        if my_debug:
            ck_bit = self._read_ALMPOL_bit(alarm_nr)
            print(TAG+"for alarm{:d}: check: b\'{:b}\'".format(alarm_nr, ck_bit))
        return ret
    
    # Clear the alarm pol bit for alarm x     
    def _clr_ALMPOL_bit(self, alarm_nr=None):
        TAG = MCP7940.CLS_NAME+"._clr_ALMPOL_bit(): "
        if alarm_nr is None:
            return -1
        if not alarm_nr in [1, 2]:
            return -1
        if alarm_nr == 1:
            ads = MCP7940.REGISTER_ALM1WKDAY
        elif alarm_nr == 2:
            ads = MCP7940.REGISTER_ALM1WKDAY
        ret = self._set_bit(ads, MCP7940.ALMPOL_BIT, 0)
        if ret == -1:
            if my_debug:
                print(TAG+self.sbf)
            return ret
        return ret
    
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
    
    
    # Set the alarm mask (= alarm match) bits for alarm x
    def _set_ALMxMSK_bits(self, alarm_nr= None, match_type=None):
        TAG = "MCP7940._set_ALMxMSK_bits(): "
        if alarm_nr is None:
            return
        if not alarm_nr in [1, 2]:
            return
        if match_type is None:
            return
        if alarm_nr == 1:
            ads = MCP7940.REGISTER_ALM1WKDAY
        elif alarm_nr == 2:
            ads = MCP7940.REGISTER_ALM2WKDAY
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

    # Get time for:
    # a) timekeeping registers
    # b) SRAM registers
    # c) alarm1
    # d) alarm2
    # e) power fail
    def _mcpget_time(self, start_reg = 0x00):
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
            
        # --------------------------------------------------------------------------------------
        # GET THE TIMEKEEPING DATA FROM THE MCP7940 RTC SHIELD
        # --------------------------------------------------------------------------------------
        try:
            while not self._i2c.try_lock():
                pass
            self._i2c.writeto_then_readfrom(MCP7940.ADDRESS, reg_buf, time_reg)
        except OSError as e:
            print(TAG+f"Error: {e}")
            return (0,)
        finally:
            self._i2c.unlock()
            #pass
        # --------------------------------------------------------------------------------------
        if my_debug:
            print(TAG+"received following datetime data from MCP7940:")
            print(f"{time_reg}, list(time_reg): {list(time_reg)}")  # note this contains bcd coded values
            print()
        
        reg_filter = (0x7F, 0x7F, 0x3F, 0x07, 0x3F, 0x3F, 0xFF)[:num_registers]

        if my_debug:
            print(TAG+f"time_reg: {time_reg}")
            print(TAG+f"reg_filter: {reg_filter}")
        t = [self.bcd_to_int(reg & filt) for reg, filt in zip(time_reg, reg_filter)]
        
        if my_debug:
            print(TAG+f"t: {t}")
            
        hh = t[MCP7940.RTCHOUR]
        if my_debug:
            print(TAG+f"self._is_12hr: {self._is_12hr}")
            print(TAG+"hh: {:2d}, b\'{:08b}\'".format(hh, hh))
        if self._is_12hr:
            hh &= 0x1F  # mask 12/24 bit and mask AM/PM bit
            #if hh >= 12:
            #    hh -= 12
        
        if my_debug:
            print(TAG+"hh (bits 7-5 masked): {:2d}, b\'{:08b}\'".format(hh, hh))
            print(TAG+f"length t: {t}")
        t2 = (t[MCP7940.RTCMTH], t[MCP7940.RTCDATE], hh, t[MCP7940.RTCMIN], t[MCP7940.RTCSEC], t[MCP7940.RTCWKDAY])
        t3 = (t[MCP7940.RTCYEAR] + 2000,) + t2 if num_registers == 7 else t2
        # now = (2019, 7, 16, 15, 29, 14, 6, 167)  # Sunday 2019/7/16 3:29:14pm (yearday=167)
        # year, month, date, hours, minutes, seconds, weekday, yearday = t
        # time_reg = [seconds, minutes, hours, weekday, date, month, year % 100]

        if my_debug:
            print(TAG+f"returning result t3: {t3}")
        return t3
    
    # Read the datetime stamps of the pwr down / pwr up events
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
        
    # Clear the 64 bytes of SRAM space
    def clr_SRAM(self):
        TAG = "clr_SRAM(): "
        out_buf = bytearray()
        out_buf.append(MCP7940.SRAM_START_ADDRESS)
        for _ in range(0x40):
            out_buf.append(0x0)
        if my_debug:
            print(TAG+f"length data to write to clear SRAM data: {hex(len(out_buf)-1)}")
        try:
            while not self._i2c.try_lock():
                pass
        
            self._i2c.writeto(MCP7940.ADDRESS, out_buf) 
        except OSError as e:
            print(TAG+f"Error: {e}")
        finally:
            self._i2c.unlock()
            
    # Print contents of the 64 bytes of SRAM space
    def show_SRAM(self):
        TAG = "show_SRAM(): "
        reg_buf = bytearray()
        reg_buf.append(MCP7940.SRAM_START_ADDRESS)
        in_buf = bytearray(0x40) # 0x5F-0x20+1)
        try:
            while not self._i2c.try_lock():
                pass      
            self._i2c.writeto_then_readfrom(MCP7940.ADDRESS, reg_buf, in_buf)
        except OSError as e:
            print(TAG+f"Error: {e}")
        finally:
            self._i2c.unlock()
        
        print(TAG+"Contents of SRAM:")
        le = len(in_buf)
        for _ in range(le):
            if _ % 10 == 0:
                if _ > 0:
                    print()
            if _ == le-1:
                s = ""
            else:
                s = ", "
            print("{:3d}{:s}".format(in_buf[_], s), end='')
        print()
    
    # Write datetime stamp to SRAM 
    def write_to_SRAM(self, dt):
        TAG="MCP7940.write_to_SRAM():    "
        le = len(dt)
        if my_debug:
            print("\n"+TAG+f"param dt: {dt}")
            print(TAG+f"length received param dt, le: {le}")
        reg_buf = bytearray()
        reg_buf.append(MCP7940.SRAM_START_ADDRESS)
        if my_debug:
            print(TAG+f"reg_buf: {reg_buf}, hex(list(reg_buf)[0]): {hex(list(reg_buf)[0])}")
        if le >= 64:
            dt2 = dt[:64]  # only the bytes 0-6. Cut 7 and 8 because 7 is too large and 8 could be negative]
        else:
            dt2 = dt
        le2 = len(dt2)
        if my_debug:
            print(TAG+f"le2: {le2}")
  
        if my_debug:
            print("\n"+TAG+f"dt2: {dt2}")
            print(TAG+f"MCP7940.write_to_SRAM(): Writing this datetime tuple (dt2): \'{dt2}\' to user memory (SRAM)")
        
        if le2 == 7:
            year, month, date, hours, minutes, seconds, weekday  = dt2
            if year >= 2000:
                year -= 2000
            dt4 = [seconds, minutes, hours, weekday, date, month, year]
        elif le2 == 9:
            year, month, date, hours, minutes, seconds, weekday, is_12hr, is_PM = dt2
            if year >= 2000:
                year -= 2000
            dt4 = [seconds, minutes, hours, weekday, date, month, year, is_12hr, is_PM]
        
        ampm = "" 
                
        le4 = len(dt4)
        nr_bytes = le4
        
        if my_debug:
            if le4 == 7:
                print(TAG+f"nr_bytes: {nr_bytes+1}, sec: {seconds}, min: {minutes}, hr: {hours}, wkday: {weekday}, dt: {date}, mon: {month}, yy: {year}")
            elif le4 == 9:
                print(TAG+f"nr_bytes: {nr_bytes+1}, sec: {seconds}, min: {minutes}, hr: {hours}, wkday: {weekday}, dt: {date}, mon: {month}, yy: {year},  is_12hr: {is_12hr}, is_PM: {is_PM}")
                print()
        # Reorder
        # Write in reversed order (as in the registers 0x00-0x06 of the MP7940)

        if my_debug:
            print(TAG+f"dt4: {dt4}, nr_bytes: {nr_bytes}")
        out_buf = bytearray() # 
        out_buf.append(MCP7940.SRAM_START_ADDRESS)
        out_buf.append(nr_bytes+1) # add the number of bytes + the nr_bytes byte itself
        
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
            self._i2c.unlock()
            return -1
        finally:
            self._i2c.unlock()
            #pass
        return nr_bytes  # return nr_bytes to show command was successful
    
    # Read datetime stamp from SRAM
    def read_fm_SRAM(self):
        TAG = "MCP7940.read_fm_SRAM():     "
        dt = bytearray(0x40) #  read all the SRAM memory. was: (num_regs)
        reg_buf = bytearray()
        reg_buf.append(MCP7940.SRAM_START_ADDRESS)
        if my_debug:
            print(TAG+f"\nbefore reading from SRAM, dt: {dt} = list(dt): {list(dt)}")
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
    
        if not dt:
            return (0,)  # Indicate received 0 bytes
        if len(dt) == 0:
            return (0,) # Indicate received 0 bytes

        nr_bytes = dt[0] # extract the number of bytes saved
        dt = list(dt[:nr_bytes])
        if my_debug:
            print(TAG+f"received from RTC SRAM: nr_bytes: {nr_bytes}, dt: ", end='\n')
            print(TAG+f"dt2: {dt}")
        
        if nr_bytes == 8:
            nr_bytes2, seconds, minutes, hours, weekday, date, month, year = dt
            # reorder:
            dt2 = (nr_bytes2, year, month, date, weekday, hours, minutes, seconds)
        elif nr_bytes == 10:
            nr_bytes2, seconds, minutes, hours, weekday, date, month, year, is_12hr, is_PM = dt
            # reorder:
            dt2 = (nr_bytes2, year, month, date, weekday, hours, minutes, seconds, is_12hr, is_PM)
        else:
            dt2 = dt
        if my_debug:
            print(TAG+"return value dt2: {}, type(dt2): {} ".format(dt2, type(dt2)))
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
