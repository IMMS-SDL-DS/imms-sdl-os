"""
config.py
=========
Shared configuration for balance and robot workflows.
"""

# ============================================================
# Balance Connection
# ============================================================
BALANCE_HOST = "192.168.1.10"
BALANCE_PORT = 81
BALANCE_PASSWORD = "00000000"
USE_HTTPS = False

# ============================================================
# Dosing Tolerances
# ============================================================
LOWER_TOLERANCE = 1.0
UPPER_TOLERANCE = 1.0

# ============================================================
# UR Robot Connection
# ============================================================
UR_HOST = "192.168.1.20"
UR_PORT = 30002

# ============================================================
# Robotiq Gripper Speed Configuration
# ============================================================
# 0 = minimum speed (~22 mm/s) for fragile glass vial safety
# 255 = maximum speed (~110 mm/s)
GRIPPER_SPEED = 0