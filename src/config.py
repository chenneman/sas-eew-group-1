"""Global configuration settings for the simulation"""


L_WH       = 28             # Warehouse grid length in x (meters)
W_WH       = 24             # Warehouse grid width in y (meters)
N_AGV      = 4              # Number of AGVs
N_SERVERS  = 2              # Number of servers
N_CHARGERS = N_AGV          # Number of chargers
N_ITEMS    = 100            # Number of items

# Order Generation Parameters
ORDERS_PER_HOUR = [
    13.0,  7.5,  5.0,  4.5,  4.0,  4.0,   # 00-05
     5.0,  8.0, 16.0, 24.0, 30.0, 32.0,   # 06-11
    29.5, 32.0, 32.0, 32.0, 32.5, 30.0,   # 12-17
    28.0, 30.0, 30.5, 30.5, 28.0, 21.0,   # 18-23
]

# Simulation Run Parameters
SIM_START_HOUR = 0
WARMUP_MIN     = 30
HORIZON_MIN    = 24 * 60
TOTAL_MIN      = WARMUP_MIN + HORIZON_MIN
N_REPS         = 10
MAX_WAIT_TIME = 5 # min
BATCH_SIZE = 3 # orders

# AGV parameters
MAX_BATTERY    = 621.6 # Wh
SOC_THRESHOLD   = 10 # %
BATTERY_THRESHOLD  = 0.01 * SOC_THRESHOLD * MAX_BATTERY
DRIVE_SPEED   = 3.5 # m/s
E_BASE        = 0.0489 # Wh/m
ALPHA       = 0.0001 # Wh/(kg·m)
MAX_VOLUME = 600 * 400 * 400 # mm^3
MAX_PAYLOAD = 40.0 # kg
CHARGE_RATE = 43.17 # Wh/min

