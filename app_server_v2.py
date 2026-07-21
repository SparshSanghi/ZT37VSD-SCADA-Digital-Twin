import asyncio
import random
import time
import math

from pymodbus.server import StartAsyncTcpServer
from pymodbus.datastore import (
    ModbusSequentialDataBlock,
    ModbusSlaveContext,
    ModbusServerContext
)

# ==========================================================
# ZT37VSD DIGITAL TWIN V2
# ==========================================================

READY = 0
STARTING = 1
LOADED = 2
UNLOADED = 3
SHUTDOWN = 4
TRIP = 5

FAULT_NONE = 0
FAULT_HIGH_TEMP = 1
FAULT_DRYER = 2
FAULT_OVERPRESSURE = 3
FAULT_MAINTENANCE = 4

# ==========================================================
# REGISTER MAP
# ==========================================================

# 0   Pressure PSI x10
# 1   VSD Speed %
# 2   Stage1 Temp
# 3   Intercooler Temp
# 4   Stage2 Temp
# 5   Condensate %
# 6   Active Dryer Load
# 7   PDP +100
# 8   Ambient RH %
# 9   State

# 10  Start Command
# 11  Reset Command
# 12  Auto Mode
# 13  Pressure Setpoint

# 14  Fault Code
# 15  Runtime Seconds
# 16  Power kW x10
# 17  Airflow CFM
# 18  Maintenance Counter
# 19  Alarm Count

# 20  Tower A Load
# 21  Tower B Load
# 22  Active Tower
# 23  Cycle Timer

# 24  Ambient Temp
# 25  Plant Demand
# 26  Maintenance Due

# ==========================================================
# INITIAL REGISTERS
# ==========================================================

regs = [0] * 100

regs[0] = 1025
regs[1] = 0

regs[2] = 30
regs[3] = 30
regs[4] = 30

regs[5] = 0
regs[6] = 10
regs[7] = 60

regs[8] = 65
regs[9] = READY

regs[10] = 0
regs[11] = 0
regs[12] = 1
regs[13] = 1025

regs[14] = 0
regs[15] = 0
regs[16] = 0
regs[17] = 0
regs[18] = 0
regs[19] = 0

# Dryer

regs[20] = 10
regs[21] = 10
regs[22] = 0
regs[23] = 60

# Environment

regs[24] = 30
regs[25] = 40
regs[26] = 0

# ==========================================================
# MODBUS
# ==========================================================

store = ModbusSlaveContext(
    hr=ModbusSequentialDataBlock(
        0,
        regs
    )
)

context = ModbusServerContext(
    slaves=store,
    single=True
)

fault_history = []

# ==========================================================
# HELPER FUNCTIONS
# ==========================================================

def clamp(value, low, high):
    return max(
        low,
        min(
            high,
            value
        )
    )

def modbus_safe(value):

    try:
        value = int(value)
    except:
        value = 0

    return clamp(
        value,
        0,
        65535
    )

def saturation_pressure(temp_c):

    return (
        0.61078 *
        math.exp(
            (17.27 * temp_c)
            /
            (temp_c + 237.3)
        )
    )

def add_fault(code):

    if len(fault_history) >= 200:
        fault_history.pop(0)

    fault_history.append(
        (
            time.strftime("%H:%M:%S"),
            code
        )
    )

# ==========================================================
# MAIN SIMULATION
# ==========================================================

async def simulator(server_context):

    state_timer = 0

    while True:

        await asyncio.sleep(1)

        slave = server_context[0]

        r = slave.getValues(
            3,
            0,
            count=100
        )

        pressure = r[0]
        vsd = r[1]

        s1 = r[2]
        intercool = r[3]
        s2 = r[4]

        condensate = r[5]
        desiccant = r[6]
        pdp = r[7]

        rh = r[8]
        state = r[9]

        start_cmd = r[10]
        reset_cmd = r[11]
        auto_mode = r[12]
        setpoint = r[13]

        fault = r[14]
        runtime = r[15]
        power = r[16]
        airflow = r[17]

        maint = r[18]
        alarms = r[19]

        tower_a = r[20]
        tower_b = r[21]

        active_tower = r[22]
        cycle_timer = r[23]

        ambient_temp = r[24]
        plant_demand = r[25]

        maintenance_due = r[26]
        # ==================================================
        # COMMAND HANDLING
        # ==================================================

        if reset_cmd == 1:

            fault = FAULT_NONE

            if state == TRIP:
                state = READY

            slave.setValues(
                3,
                11,
                [0]
            )

        # ==================================================
        # STARTUP
        # ==================================================

        if (
            state == READY
            and start_cmd == 1
            and fault == FAULT_NONE
        ):

            state = STARTING
            state_timer = 5

        # ==================================================
        # SHUTDOWN
        # ==================================================

        if (
            state in (
                LOADED,
                UNLOADED
            )
            and start_cmd == 0
        ):

            state = SHUTDOWN
            state_timer = 5

        # ==================================================
        # STARTING STATE
        # ==================================================

        if state == STARTING:

            state_timer -= 1

            vsd = min(
                35,
                vsd + 8
            )

            pressure += 2

            if state_timer <= 0:
                state = LOADED

        # ==================================================
        # SHUTDOWN STATE
        # ==================================================

        elif state == SHUTDOWN:

            state_timer -= 1

            vsd = max(
                0,
                vsd - 10
            )

            pressure = max(
                0,
                pressure - 5
            )

            if state_timer <= 0:
                state = READY

        # ==================================================
        # NORMAL OPERATION
        # ==================================================

        elif state in (LOADED, UNLOADED):

            # ----------------------------------------------
            # PRESSURE CONTROLLER
            # ----------------------------------------------

            error = setpoint - pressure

            vsd += int(error * 0.015)

            vsd = clamp(
                vsd,
                20,
                100
            )

            # ----------------------------------------------
            # AIRFLOW MODEL
            # ----------------------------------------------

            airflow = int(
                250 *
                (vsd / 100)
            )

            net_flow = airflow - plant_demand

            pressure += int(
                net_flow * 0.25
            )

            pressure = clamp(
                pressure,
                0,
                1300
            )

            # ----------------------------------------------
            # LOAD / UNLOAD LOGIC
            # ----------------------------------------------

            if pressure > setpoint + 20:

                state = UNLOADED

            elif pressure < setpoint - 30:

                state = LOADED

            if state == UNLOADED:

                pressure -= random.randint(
                    3,
                    8
                )

            runtime += 1

            maint += 1

        # ==================================================
        # READY STATE
        # ==================================================

        elif state == READY:

            pressure = max(
                0,
                pressure - random.randint(
                    2,
                    6
                )
            )

            vsd = 0

        # ==================================================
        # TRIP STATE
        # ==================================================

        elif state == TRIP:

            vsd = 0

            pressure = max(
                0,
                pressure - 10
            )

        # ==================================================
        # POWER MODEL
        # ==================================================

        power = int(
            37 *
            (vsd / 100)
            * 10
        )

        # ==================================================
        # THERMAL MODEL
        # ==================================================

        if vsd > 0:

            s1 = int(
                ambient_temp
                + 30
                + (vsd * 0.45)
            )

            intercool = int(
                ambient_temp
                + 5
                + (vsd * 0.12)
            )

            s2 = int(
                ambient_temp
                + 75
                + (vsd * 0.75)
            )

        else:

            s1 = max(
                ambient_temp,
                s1 - 3
            )

            intercool = max(
                ambient_temp,
                intercool - 2
            )

            s2 = max(
                ambient_temp,
                s2 - 4
            )

        # ==================================================
        # CONDENSATE GENERATION
        # ==================================================

        moisture_factor = (
            rh / 100
        ) * (
            airflow / 250
        )

        condensate += int(
            moisture_factor * 4
        )

        condensate = clamp(
            condensate,
            0,
            100
        )
        # ==================================================
        # TWIN TOWER DRYER
        # ==================================================

        cycle_timer -= 1

        if cycle_timer <= 0:

            active_tower = 1 - active_tower
            cycle_timer = 60

        if state in (LOADED, UNLOADED):

            moisture_load = max(
                1,
                int(
                    (rh / 20)
                    *
                    (airflow / 100)
                )
            )

            if active_tower == 0:

                tower_a += moisture_load

                tower_b -= 3

            else:

                tower_b += moisture_load

                tower_a -= 3

        else:

            tower_a -= 1
            tower_b -= 1

        tower_a = clamp(
            tower_a,
            0,
            100
        )

        tower_b = clamp(
            tower_b,
            0,
            100
        )

        desiccant = (
            tower_a
            if active_tower == 0
            else tower_b
        )

        # ==================================================
        # PDP MODEL
        # ==================================================

        if desiccant < 30:

            pdp = 60

        elif desiccant < 60:

            pdp = 75

        elif desiccant < 80:

            pdp = 90

        else:

            pdp = 115

        # ==================================================
        # MAINTENANCE MODEL
        # ==================================================

        if maint > 5000:

            maintenance_due = 1

        else:

            maintenance_due = 0

        # ==================================================
        # FAULT LOGIC
        # ==================================================

        if (
            s2 >= 225
            and state != TRIP
        ):

            state = TRIP
            fault = FAULT_HIGH_TEMP

            add_fault(
                FAULT_HIGH_TEMP
            )

            alarms += 1

        elif (
            tower_a >= 95
            and tower_b >= 95
            and state != TRIP
        ):

            state = TRIP
            fault = FAULT_DRYER

            add_fault(
                FAULT_DRYER
            )

            alarms += 1

        elif (
            pressure >= 1300
            and state != TRIP
        ):

            state = TRIP
            fault = FAULT_OVERPRESSURE

            add_fault(
                FAULT_OVERPRESSURE
            )

            alarms += 1

        elif (
            maintenance_due == 1
            and fault == FAULT_NONE
        ):

            fault = FAULT_MAINTENANCE

        alarms = clamp(
            alarms,
            0,
            65535
        )

        runtime = clamp(
            runtime,
            0,
            65535
        )

        maint = clamp(
            maint,
            0,
            65535
        )

        # ==================================================
        # MODBUS WRITEBACK
        # ==================================================

        update = [
            pressure,
            vsd,

            s1,
            intercool,
            s2,

            condensate,
            desiccant,
            pdp,

            rh,
            state,

            start_cmd,
            reset_cmd,
            auto_mode,
            setpoint,

            fault,

            runtime,
            power,
            airflow,

            maint,
            alarms,

            tower_a,
            tower_b,
            active_tower,
            cycle_timer,

            ambient_temp,
            plant_demand,
            maintenance_due
        ]

        safe_update = []

        for value in update:

            safe_update.append(
                modbus_safe(value)
            )

        slave.setValues(
            3,
            0,
            safe_update
        )

# ==========================================================
# MAIN
# ==========================================================

async def main():

    asyncio.create_task(
        simulator(context)
    )

    print(
        "ZT37VSD DIGITAL TWIN V2 ONLINE"
    )

    print(
        "Modbus TCP : 127.0.0.1:5020"
    )

    await StartAsyncTcpServer(
        context=context,
        address=(
            "127.0.0.1",
            5020
        )
    )

if __name__ == "__main__":

    asyncio.run(
        main()
    )