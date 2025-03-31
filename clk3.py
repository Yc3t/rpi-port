import board
import busio
import adafruit_ds3231
import time
from time import struct_time

# Create the I2C interface
i2c = busio.I2C(board.SCL, board.SDA)

# Create the DS3231 instance
rtc = adafruit_ds3231.DS3231(i2c)

# Obtener la hora actual del sistema
tiempo_actual = time.localtime()

# Establecer el RTC con la hora actual del sistema
rtc.datetime = tiempo_actual

print("RTC configurado con la hora actual del sistema:")
print(f"Fecha: {tiempo_actual.tm_year}/{tiempo_actual.tm_mon:02d}/{tiempo_actual.tm_mday:02d}")
print(f"Hora: {tiempo_actual.tm_hour:02d}:{tiempo_actual.tm_min:02d}:{tiempo_actual.tm_sec:02d}")

try:
    while True:
        # Get the current time from RTC
        t = rtc.datetime
        
        # Format the time nicely
        print(f"Date: {t.tm_year}/{t.tm_mon:02d}/{t.tm_mday:02d}")
        print(f"Time: {t.tm_hour:02d}:{t.tm_min:02d}:{t.tm_sec:02d}")
        print("------------------------")
        
        # Wait for a second before next reading
        time.sleep(1)

except KeyboardInterrupt:
    print("\nExiting program")import board
import busio
import adafruit_ds3231
import time
from time import struct_time

# Create the I2C interface
i2c = busio.I2C(board.SCL, board.SDA)

# Create the DS3231 instance
rtc = adafruit_ds3231.DS3231(i2c)

# Obtener la hora actual del sistema
tiempo_actual = time.localtime()

# Establecer el RTC con la hora actual del sistema
rtc.datetime = tiempo_actual

print("RTC configurado con la hora actual del sistema:")
print(f"Fecha: {tiempo_actual.tm_year}/{tiempo_actual.tm_mon:02d}/{tiempo_actual.tm_mday:02d}")
print(f"Hora: {tiempo_actual.tm_hour:02d}:{tiempo_actual.tm_min:02d}:{tiempo_actual.tm_sec:02d}")

try:
    while True:
        # Get the current time from RTC
        t = rtc.datetime
        
        # Format the time nicely
        print(f"Date: {t.tm_year}/{t.tm_mon:02d}/{t.tm_mday:02d}")
        print(f"Time: {t.tm_hour:02d}:{t.tm_min:02d}:{t.tm_sec:02d}")
        print("------------------------")
        
        # Wait for a second before next reading
        time.sleep(1)

except KeyboardInterrupt:
    print("\nExiting program")
