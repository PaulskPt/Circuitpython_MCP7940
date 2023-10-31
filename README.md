# MCP7940  RTC Shield
 Circutipython example to use an Unexpected Maker RTC Shield (MCP7940) .
 Until now there were, as far as I know, only examples for Micropython and for Arduino.

The example sets Alarm1 for a datetime which is 2 minutes from the moment the alarm is set. The MCP7940 is programmed to 'signal' a 'match' of the current datetime with the datetime of Alarm1. The match is set for a match on "minutes". At the moment a match occurs, the MCP7940 MFP line will go to logical state '1'. 
In the Example FeatherS3, the MFP line, pin 4 on the UM RTC Shield is connected to pin IO33 of the UM FeatherS3.
In the Example ProS3, the MFP line, pin 4 on the UM RTC Shield is connected to pin IO15 of the UM ProS3.
When a 'match' interrupt occurs, the NEOPIXEL led will flash alternatively red and blue for some cycles. The sketch will issue a KeyboardInterrupt after receiving the RTC Interrupt.

## Update 2023-10-31:
In Example 2 added a file `dst.py` which contains the dst start and end `EPOCH values for the years 2022 - 2031`. In the current example the file `dst.py` contains the dst values for `timezone 'Europe/Portugal'`.
You can change the values for your timezone. See: `https://www.epochconverter.com/`
