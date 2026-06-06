"""Global configuration settings for the simulation"""

# Warehouse
L_WH = 28  # Warehouse grid length in x (meters)
W_WH = 24  # Warehouse grid width in y (meters)
N_AGV = 4  # Number of AGVs
N_SERVERS = 2  # Number of servers
N_CHARGERS = N_AGV  # Number of chargers
N_ITEMS = 100  # Number of items

# AGV
MAX_BATTERY = 621.6  # Wh
SOC_THRESHOLD = 10  # %
BATTERY_THRESHOLD = 0.01 * SOC_THRESHOLD * MAX_BATTERY
DRIVE_SPEED = 3.5 # originally 3.5 # m/s
E_BASE = 0.0489  # originally 0.0489 # Wh/m
E_IDLE = 0.05  # Wh/min (Base electronics/sensor drain)
ALPHA = 0.0001  # Wh/(kg·m)
MAX_VOLUME = 60 * 40 * 40  # cm^3
MAX_PAYLOAD = 40.0  # kg
CHARGE_RATE = 43.17  # Wh/min
PICK_TIME_PER_ITEM = 60  # Seconds per item picked
INITIAL_BATTERY_FACTOR = 0.8  # Fraction of MAX_BATTERY to start with (e.g. 0.05 for testing)

# Control / global
INNOVATION_ENABLED = False  # True = Multi-stop picking, False = 1 order per AGV
MAX_WAIT_TIME = 5  # maximum time (in sim minutes) to wait for a full batch before triggering.
BATCH_SIZE = 4  # the number of orders to pool before triggering a routing run. #NEED TO BE 1 WHEN INNOVATION IS OFF
RANDOM_SEED = 1234  # Seed for reproducible simulation runs

# Scaling
ORDER_RATE_MULTIPLIER = 1.0  # Multiplies orders/hr rate (e.g., 2.0 doubles demand)
SERVICE_TIME_MULTIPLIER = 2.0  # Multiplies unloading/packing time (e.g., 2.0 makes it 2x slower)

# Time
SIM_START_HOUR = 0  # Start time of the simulation (0-23)
WARMUP_MIN = 30 # Time before KPIs are measured
HORIZON_MIN = 24 * 60 # Simulation time horizon in minutes
TOTAL_MIN = WARMUP_MIN + HORIZON_MIN

# UI
ANIMATE = False  # If False the simulation runs much faster
ENABLE_UI_LOGGING = True  # Set to False for high-speed runs to avoid list-appending overhead
INITIAL_ANIM_SPEED = 1  # Initial animation speed (e.g., 1 for synced)

# Logging
LOG_LEVEL = "INFO"  # DEBUG, INFO, WARNING, ERROR, CRITICAL
SAVE_LOG_TO_FILE = True  # If True, saves custom logs to logs/simulation.log
SAVE_TRACE_TO_FILE = False  # If True, saves Salabim trace to logs/trace.log
SAVE_SUMMARY_TO_FILE = True  # If True, saves the final KPI summary to logs/summary.txt
