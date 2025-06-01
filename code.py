import board
import time
import busio as bus
import digitalio as io
import json
import asyncio
import math
import adafruit_rfm69 as rfm69
import adafruit_lis331

print(f"Starting code at {time.monotonic()} seconds")

#node ids for keying messages
robot_node_ID = 69
transmitter_node_ID = 42

#vars for inputs to robot
trans_x = 0.0
trans_y = 0.0
enable = False
vel_sp = False

#vars for robot operation
angular_vel = 0.0
angular_dir = 0.0
bat_volts = 0.0

#imu data
imu_mounting_offset = 0.05 #currently assumed
imu_raw = [0.0, 0.0, 0.0]
imu_data = [0.0, 0.0, 0.0]
imu_calibration = [0.0, 0.0, 0.0]

#motor angles
motor_angle_offsets = [
    -0.25*math.pi,
    0.25*math.pi,
    -0.75*math.pi,
    0.75*math.pi
]

#motor powers
motor_trans_powers = [0.0, 0.0, 0.0, 0.0]

#status LED for debug
status_led = io.DigitalInOut(board.LED)
status_led.direction = status_led.direction.OUTPUT

#SPI bus stuff
spi = bus.SPI(board.SCK, MOSI=board.MOSI, MISO=board.MISO)
cs = io.DigitalInOut(board.D9)
rst = io.DigitalInOut(board.D10)
print(f"SPI bus booted successfully at {time.monotonic()} seconds")

#start radio
try:
    radio_rfm69 = rfm69.RFM69(spi, cs, rst, 915)
    radio_rfm69.tx_power = 5
    radio_rfm69.timeout = 3
    print(f"SPI device RFM69HCW present at {time.monotonic()} seconds")
except RuntimeError as e:
    while True:
        for n in range(0, 6):
            status_led.value = not status_led.value
            time.sleep(0.5)
        time.sleep(3)

#I2C bus stuff
i2c = bus.I2C(board.SCL, board.SDA, frequency=1_000_000)
print(f"I2C bus booted successfully at {time.monotonic()} seconds")

#I2C devices
imu = adafruit_lis331.H3LIS331(i2c)
imu.data_rate = adafruit_lis331.Rate.RATE_1000_HZ
imu.range = adafruit_lis331.H3LIS331Range.RANGE_400G
#imu.enable_hpf(enabled=True, cutoff=adafruit_lis331.RateDivisor.ODR_DIV_50, use_reference=True)
print(f"I2C device H3LIS331 present at {time.monotonic()} seconds")

#IMU calibration routine
imu_cal_samples = [0.0, 0.0, 0.0]
imu_cal_sample_number = 5000 #take samples of each imu axis
print(f"IMU calibration start at {time.monotonic()} seconds.")
for _ in range(imu_cal_sample_number):
    i = 0
    for value in imu.acceleration:
        imu_cal_samples[i] += value
        i += 1
i = 0
for value in imu_calibration:
    imu_calibration[i] = imu_cal_samples[i] / imu_cal_sample_number
    i += 1
print(f"IMU calibration complete at {time.monotonic()} seconds.")

time.sleep(3)

#iir filter for imu data
def iir_filter(new_reading, prev_filtered, alpha):
    return [
        alpha * new_reading[i] + (1 - alpha) * prev_filtered[i]
        for i in range(3)
    ]

#used to update io
async def run_io():

    global angular_vel, imu_raw

    #update data
    imu_raw = iir_filter(imu.acceleration, imu_raw, 0.03)

    i = 0
    #update offset data
    for value in imu_raw:
        imu_data[i] = imu_raw[i] - imu_calibration[i]
        i += 1
    
    #update angular velocity, chop bottom 100rpm off due to noise
    angular_vel_tmp = math.sqrt(abs(imu_data[0]) / imu_mounting_offset) * (60 / (2*math.pi)) #find angular velocity 
    if angular_vel_tmp > 100:
        angular_vel = angular_vel_tmp
    else:
        angular_vel = 0

#use to receive data
async def receive():

    #globals
    global trans_x, trans_y, enable, vel_sp
    
    #receive packet, check node id, write data if good
    packet = radio_rfm69.receive()
    if packet is not None:
        data = json.loads(packet.decode("utf-8"))
        if data["id"] == transmitter_node_ID:
            trans_x = data["tx"]
            trans_y = data["ty"]
            enable = bool(data["en"])
            vel_sp = bool(data["sp"])
            del data["id"]
            #print(f"received: {data}")
    else:
        #print("no packet")
        pass

    #break
    await asyncio.sleep(0)

#use to transmit data
async def transmit():

    #format data into json, keep lengths down to limit assertion errors
    data = {
        "id": robot_node_ID, #indicates this node sent the packet
        "bv": bat_volts,
        "av": angular_vel,
        "ad": angular_dir
    }

    #dump json data into packet and send in byte array
    #assertion error will occur if payload > 64 bytes
    try:
        radio_rfm69.send(bytes(json.dumps(data), "utf-8"))
        #print(f"transmitted: {data}")
    except AssertionError as e:
        print(f"Message send failure, likely byte overflow. {e}")

    #break
    await asyncio.sleep(0)

#use your imagination
async def blink():

    #blink
    status_led.value = True
    time.sleep(0.025)
    status_led.value = False
    
    #break
    await asyncio.sleep(0)

#do i really need to explain?
async def main():
    
    #check time for loops
    print(f"Main loop started at {time.monotonic()} seconds")
    blink_last_time = time.monotonic()
    radio_last_time = time.monotonic()
    loop_last_time = time.monotonic()
    while True:

        #clear task list, check time
        tasks = []
        time_now = time.monotonic()

        #always add transmit and io checks to schedule
        tasks.append(run_io())

        #sample radio at 10hz
        if time_now - radio_last_time >= 0.10:
            radio_last_time = time.monotonic()
            #tasks.append(receive())
            tasks.append(transmit())
            print(f"speed: {angular_vel} rpm")

        #blink at 1hz
        if time_now - blink_last_time >= 1:
            blink_last_time = time.monotonic()
            tasks.append(blink())

        #print(f"Loop time: {time_now - loop_last_time}")
        loop_last_time = time.monotonic()

        #gather tasks
        await asyncio.gather(*tasks)

#use your brain, dude
asyncio.run(main())