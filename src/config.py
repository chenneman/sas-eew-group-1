"""Global configuration settings for the simulation"""

#TODO change to yaml based config?

# Warehouse parameters
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

# Control Parameters
INNOVATION_ENABLED = True  # True = Multi-stop picking, False = 1 order per AGV
N_REPS         = 10
MAX_WAIT_TIME = 5 # min
BATCH_SIZE = 3 # orders

# Time parameters
SIM_START_HOUR = 0
WARMUP_MIN     = 30
HORIZON_MIN    = 24 * 60
TOTAL_MIN      = WARMUP_MIN + HORIZON_MIN

# Simulation parameters
ANIMATE = False # If False much faster
INITIAL_ANIM_SPEED = 3      # Initial animation speed (e.g., 1 for synced)
INITIAL_BATTERY_FACTOR = 0.15 # Fraction of MAX_BATTERY to start with (e.g. 0.05 for testing)
LOG_TRACE_TO_FILE = True  # If True, saves Salabim trace to logs/trace.log
SAVE_SUMMARY_TO_FILE = True # If True, saves the final KPI summary to logs/summary.txt
RANDOM_SEED = 123           # Seed for reproducible simulation runs


# AGV parameters
MAX_BATTERY    = 621.6 # Wh
SOC_THRESHOLD   = 10 # %
BATTERY_THRESHOLD  = 0.01 * SOC_THRESHOLD * MAX_BATTERY
DRIVE_SPEED   = 3.5 # m/s
E_BASE        = 0.1 # originally 0.0489 # Wh/m
ALPHA       = 0.0001 # Wh/(kg·m)
MAX_VOLUME = 60 * 40 * 40 # cm^3
MAX_PAYLOAD = 40.0 # kg
CHARGE_RATE = 43.17 # Wh/min

