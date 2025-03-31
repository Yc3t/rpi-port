import board
import busio
import time

# Create the I2C interface
i2c = busio.I2C(board.SCL, board.SDA)

DS3231_ADDR = 0x68
REG_STATUS = 0x0F

def check_power_lost():
    """Verifica si el RTC ha perdido energía"""
    i2c.try_lock()
    try:
        # Leer el registro de estado
        i2c.writeto(DS3231_ADDR, bytes([REG_STATUS]))
        status = i2c.readfrom(DS3231_ADDR, 1)[0]
        
        # Verificar el bit OSF (Oscillator Stop Flag)
        if status & 0x80:
            print("¡ADVERTENCIA: El RTC ha perdido energía!")
            print("Es posible que la batería necesite ser reemplazada.")
            
            # Limpiar la bandera OSF
            status &= ~0x80
            i2c.writeto(DS3231_ADDR, bytes([REG_STATUS, status]))
            return True
        else:
            print("El RTC está funcionando correctamente con batería de respaldo.")
            return False
    finally:
        i2c.unlock()

# Verificar el estado de la energía
check_power_lost()

# Tu código original aquí...
