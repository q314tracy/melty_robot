import board
import busio as bus
import time
import adafruit_lis331

#imu outputs in 

imu_data = [
    0.0, #x, tangential
    0.0, #y, centripetal
    0.0 #z, gravity
]

i2c = bus.I2C(board.SCL, board.SDA, frequency=400_000)
imu = adafruit_lis331.H3LIS331(i2c)
imu.data_rate = adafruit_lis331.Rate.RATE_1000_HZ
imu.range = adafruit_lis331.H3LIS331Range.RANGE_100G
imu.enable_hpf(enabled=True, cutoff=adafruit_lis331.RateDivisor.ODR_DIV_50, use_reference=True)

def ema(current_value, previous_ema, alpha):
    return alpha * current_value + (1 - alpha) * previous_ema


while True:

    #update data
    i = 0
    for value in imu.acceleration:
        imu_data[i] = abs(round(value / 9.80665, 3))
        i += 1
    
    print(imu_data)
    time.sleep(1)  # 100 Hz update rate (adjust as needed)