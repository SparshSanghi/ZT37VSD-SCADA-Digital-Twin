import time
import random
import math

import streamlit as st
import pandas as pd

# ==================================================================
# ZT37VSD DIGITAL TWIN - SELF-CONTAINED STREAMLIT APP
#
# This version has NO external dependency on a Modbus TCP server.
# The simulation engine (originally app_server_v2.py, a standalone
# asyncio/pymodbus process) has been ported to run directly inside
# Streamlit's session_state, driven by an autorefreshing fragment.
# This makes the app deployable as a single file on Streamlit
# Community Cloud or any other Streamlit host, with no separate
# background process, open ports, or network access required.
# ==================================================================

st.set_page_config(
    page_title="ZT37VSD Digital Twin",
    layout="wide"
)

st.title("🏭 Atlas Copco ZT37VSD Digital Twin")
st.caption(
    "Industrial Compressor + Twin Tower Dryer Simulation (Self-Contained)"
)

# ==================================================================
# CONSTANTS
# ==================================================================

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

STATES = {
    0: "READY",
    1: "STARTING",
    2: "LOADED",
    3: "UNLOADED",
    4: "SHUTDOWN",
    5: "TRIP"
}

FAULTS = {
    0: "No Fault",
    1: "High Stage 2 Temperature",
    2: "Dryer Saturation",
    3: "Overpressure",
    4: "Maintenance Due"
}


def clamp(value, low, high):
    return max(low, min(high, value))


def modbus_safe(value):
    """Kept for parity with the original register model (0-65535 int)."""
    try:
        value = int(value)
    except Exception:
        value = 0
    return clamp(value, 0, 65535)


# ==================================================================
# SIMULATION STATE INITIALISATION
# ==================================================================

def initial_sim_state():
    return {
        "pressure": 1025,
        "vsd": 0,

        "s1": 30,
        "intercool": 30,
        "s2": 30,

        "condensate": 0,
        "desiccant": 10,
        "pdp": 60,

        "rh": 65,
        "state": READY,

        "start_cmd": 0,
        "reset_cmd": 0,
        "auto_mode": 1,
        "setpoint": 1025,

        "fault": FAULT_NONE,
        "runtime": 0,
        "power": 0,
        "airflow": 0,
        "maint": 0,
        "alarms": 0,

        "tower_a": 10,
        "tower_b": 10,
        "active_tower": 0,
        "cycle_timer": 60,

        "ambient_temp": 30,
        "plant_demand": 40,
        "maintenance_due": 0,

        # internal helper, not a "register" in the original map
        "state_timer": 0,

        "last_tick": time.time(),
    }


if "sim" not in st.session_state:
    st.session_state.sim = initial_sim_state()

if "trend" not in st.session_state:
    st.session_state.trend = []

if "fault_history" not in st.session_state:
    st.session_state.fault_history = []


def add_fault(code):
    fh = st.session_state.fault_history
    if len(fh) >= 200:
        fh.pop(0)
    fh.append((time.strftime("%H:%M:%S"), code))


# ==================================================================
# SIMULATION STEP
# (ported 1:1 from the original asyncio simulator loop, operating on
# the session_state "sim" dict instead of Modbus holding registers)
# ==================================================================

def step_simulation():
    s = st.session_state.sim

    pressure = s["pressure"]
    vsd = s["vsd"]

    s1 = s["s1"]
    intercool = s["intercool"]
    s2 = s["s2"]

    condensate = s["condensate"]
    desiccant = s["desiccant"]
    pdp = s["pdp"]

    rh = s["rh"]
    state = s["state"]

    start_cmd = s["start_cmd"]
    reset_cmd = s["reset_cmd"]
    setpoint = s["setpoint"]

    fault = s["fault"]
    runtime = s["runtime"]
    power = s["power"]
    airflow = s["airflow"]

    maint = s["maint"]
    alarms = s["alarms"]

    tower_a = s["tower_a"]
    tower_b = s["tower_b"]
    active_tower = s["active_tower"]
    cycle_timer = s["cycle_timer"]

    ambient_temp = s["ambient_temp"]
    plant_demand = s["plant_demand"]
    maintenance_due = s["maintenance_due"]

    state_timer = s["state_timer"]

    # --------------------------------------------------------------
    # COMMAND HANDLING
    # --------------------------------------------------------------

    if reset_cmd == 1:
        fault = FAULT_NONE
        if state == TRIP:
            state = READY
        reset_cmd = 0

    # --------------------------------------------------------------
    # STARTUP
    # --------------------------------------------------------------

    if state == READY and start_cmd == 1 and fault == FAULT_NONE:
        state = STARTING
        state_timer = 5

    # --------------------------------------------------------------
    # SHUTDOWN
    # --------------------------------------------------------------

    if state in (LOADED, UNLOADED) and start_cmd == 0:
        state = SHUTDOWN
        state_timer = 5

    # --------------------------------------------------------------
    # STARTING STATE
    # --------------------------------------------------------------

    if state == STARTING:
        state_timer -= 1
        vsd = min(35, vsd + 8)
        pressure += 2

        if state_timer <= 0:
            state = LOADED

    # --------------------------------------------------------------
    # SHUTDOWN STATE
    # --------------------------------------------------------------

    elif state == SHUTDOWN:
        state_timer -= 1
        vsd = max(0, vsd - 10)
        pressure = max(0, pressure - 5)

        if state_timer <= 0:
            state = READY

    # --------------------------------------------------------------
    # NORMAL OPERATION
    # --------------------------------------------------------------

    elif state in (LOADED, UNLOADED):

        # Pressure controller
        error = setpoint - pressure
        vsd += int(error * 0.015)
        vsd = clamp(vsd, 20, 100)

        # Airflow model
        airflow = int(250 * (vsd / 100))
        net_flow = airflow - plant_demand
        pressure += int(net_flow * 0.25)
        pressure = clamp(pressure, 0, 1300)

        # Load / unload logic
        if pressure > setpoint + 20:
            state = UNLOADED
        elif pressure < setpoint - 30:
            state = LOADED

        if state == UNLOADED:
            pressure -= random.randint(3, 8)

        runtime += 1
        maint += 1

    # --------------------------------------------------------------
    # READY STATE
    # --------------------------------------------------------------

    elif state == READY:
        pressure = max(0, pressure - random.randint(2, 6))
        vsd = 0

    # --------------------------------------------------------------
    # TRIP STATE
    # --------------------------------------------------------------

    elif state == TRIP:
        vsd = 0
        pressure = max(0, pressure - 10)

    # --------------------------------------------------------------
    # POWER MODEL
    # --------------------------------------------------------------

    power = int(37 * (vsd / 100) * 10)

    # --------------------------------------------------------------
    # THERMAL MODEL
    # --------------------------------------------------------------

    if vsd > 0:
        s1 = int(ambient_temp + 30 + (vsd * 0.45))
        intercool = int(ambient_temp + 5 + (vsd * 0.12))
        s2 = int(ambient_temp + 75 + (vsd * 0.75))
    else:
        s1 = max(ambient_temp, s1 - 3)
        intercool = max(ambient_temp, intercool - 2)
        s2 = max(ambient_temp, s2 - 4)

    # --------------------------------------------------------------
    # CONDENSATE GENERATION
    # --------------------------------------------------------------

    moisture_factor = (rh / 100) * (airflow / 250)
    condensate += int(moisture_factor * 4)
    condensate = clamp(condensate, 0, 100)

    # --------------------------------------------------------------
    # TWIN TOWER DRYER
    # --------------------------------------------------------------

    cycle_timer -= 1

    if cycle_timer <= 0:
        active_tower = 1 - active_tower
        cycle_timer = 60

    if state in (LOADED, UNLOADED):
        moisture_load = max(1, int((rh / 20) * (airflow / 100)))

        if active_tower == 0:
            tower_a += moisture_load
            tower_b -= 3
        else:
            tower_b += moisture_load
            tower_a -= 3
    else:
        tower_a -= 1
        tower_b -= 1

    tower_a = clamp(tower_a, 0, 100)
    tower_b = clamp(tower_b, 0, 100)

    desiccant = tower_a if active_tower == 0 else tower_b

    # --------------------------------------------------------------
    # PDP MODEL
    # --------------------------------------------------------------

    if desiccant < 30:
        pdp = 60
    elif desiccant < 60:
        pdp = 75
    elif desiccant < 80:
        pdp = 90
    else:
        pdp = 115

    # --------------------------------------------------------------
    # MAINTENANCE MODEL
    # --------------------------------------------------------------

    maintenance_due = 1 if maint > 5000 else 0

    # --------------------------------------------------------------
    # FAULT LOGIC
    # --------------------------------------------------------------

    if s2 >= 225 and state != TRIP:
        state = TRIP
        fault = FAULT_HIGH_TEMP
        add_fault(FAULT_HIGH_TEMP)
        alarms += 1

    elif tower_a >= 95 and tower_b >= 95 and state != TRIP:
        state = TRIP
        fault = FAULT_DRYER
        add_fault(FAULT_DRYER)
        alarms += 1

    elif pressure >= 1300 and state != TRIP:
        state = TRIP
        fault = FAULT_OVERPRESSURE
        add_fault(FAULT_OVERPRESSURE)
        alarms += 1

    elif maintenance_due == 1 and fault == FAULT_NONE:
        fault = FAULT_MAINTENANCE

    alarms = clamp(alarms, 0, 65535)
    runtime = clamp(runtime, 0, 65535)
    maint = clamp(maint, 0, 65535)

    # --------------------------------------------------------------
    # WRITEBACK (with the same 0-65535 safety clamp as the original
    # Modbus register writeback)
    # --------------------------------------------------------------

    s["pressure"] = modbus_safe(pressure)
    s["vsd"] = modbus_safe(vsd)

    s["s1"] = modbus_safe(s1)
    s["intercool"] = modbus_safe(intercool)
    s["s2"] = modbus_safe(s2)

    s["condensate"] = modbus_safe(condensate)
    s["desiccant"] = modbus_safe(desiccant)
    s["pdp"] = modbus_safe(pdp)

    s["rh"] = modbus_safe(rh)
    s["state"] = modbus_safe(state)

    s["start_cmd"] = modbus_safe(start_cmd)
    s["reset_cmd"] = modbus_safe(reset_cmd)
    s["setpoint"] = modbus_safe(setpoint)

    s["fault"] = modbus_safe(fault)
    s["runtime"] = modbus_safe(runtime)
    s["power"] = modbus_safe(power)
    s["airflow"] = modbus_safe(airflow)

    s["maint"] = modbus_safe(maint)
    s["alarms"] = modbus_safe(alarms)

    s["tower_a"] = modbus_safe(tower_a)
    s["tower_b"] = modbus_safe(tower_b)
    s["active_tower"] = modbus_safe(active_tower)
    s["cycle_timer"] = modbus_safe(cycle_timer)

    s["ambient_temp"] = modbus_safe(ambient_temp)
    s["plant_demand"] = modbus_safe(plant_demand)
    s["maintenance_due"] = modbus_safe(maintenance_due)

    s["state_timer"] = state_timer
    s["last_tick"] = time.time()


# ==================================================================
# CONTROLS
# ==================================================================

st.subheader("🎮 Compressor Controls")

c1, c2, c3 = st.columns(3)

with c1:
    if st.button("🟢 START", use_container_width=True):
        st.session_state.sim["start_cmd"] = 1

with c2:
    if st.button("🔴 STOP", use_container_width=True):
        st.session_state.sim["start_cmd"] = 0

with c3:
    if st.button("🟡 RESET TRIP", use_container_width=True):
        st.session_state.sim["reset_cmd"] = 1

st.divider()

# ==================================================================
# PROCESS SETTINGS
# ==================================================================

st.subheader("⚙️ Process Settings")

s1_col, s2_col, s3_col = st.columns(3)

with s1_col:
    setpoint = st.slider("Pressure Setpoint (PSI)", 80, 130, 102)
    st.session_state.sim["setpoint"] = setpoint * 10

with s2_col:
    ambient_temp = st.slider("Ambient Temperature (°C)", 10, 50, 30)
    st.session_state.sim["ambient_temp"] = ambient_temp

with s3_col:
    plant_demand = st.slider("Plant Demand (CFM)", 20, 250, 40)
    st.session_state.sim["plant_demand"] = plant_demand

st.divider()


# ==================================================================
# DASHBOARD (auto-refreshing fragment, runs the sim step + renders)
# ==================================================================

@st.fragment(run_every=1)
def dashboard():

    step_simulation()

    s = st.session_state.sim

    pressure = s["pressure"] / 10.0
    vsd = s["vsd"]

    s1_temp = s["s1"]
    intercool = s["intercool"]
    s2_temp = s["s2"]

    condensate = s["condensate"]
    desiccant = s["desiccant"]

    pdp = s["pdp"] - 100

    rh = s["rh"]
    state = s["state"]

    fault = s["fault"]

    runtime = s["runtime"]

    power = s["power"] / 10.0
    airflow = s["airflow"]

    maint = s["maint"]

    tower_a = s["tower_a"]
    tower_b = s["tower_b"]

    active_tower = s["active_tower"]
    cycle_timer = s["cycle_timer"]

    ambient_temp = s["ambient_temp"]
    plant_demand = s["plant_demand"]

    maintenance_due = s["maintenance_due"]

    # --------------------------------------------------------------
    # STATUS BAR
    # --------------------------------------------------------------

    st.subheader(f"Machine State : {STATES.get(state, 'UNKNOWN')}")

    if state == 5:
        st.error(f"🚨 TRIP : {FAULTS.get(fault)}")
    elif fault != 0:
        st.warning(f"⚠️ {FAULTS.get(fault)}")
    else:
        st.success("✅ System Healthy")

    # --------------------------------------------------------------
    # KPI SECTION
    # --------------------------------------------------------------

    k1, k2, k3, k4 = st.columns(4)

    k1.metric("Pressure", f"{pressure:.1f} PSI")
    k2.metric("VSD Speed", f"{vsd}%")
    k3.metric("Power", f"{power:.1f} kW")
    k4.metric("Airflow", f"{airflow} CFM")

    st.divider()

    # --------------------------------------------------------------
    # COMPRESSOR MIMIC
    # --------------------------------------------------------------

    st.subheader("🌀 Compressor Process Flow")

    if state in (2, 3):
        st.success(
            """
COMPRESSOR
     ↓
INTERCOOLER
     ↓
MOISTURE SEPARATOR
     ↓
TWIN TOWER DRYER
     ↓
PLANT HEADER
"""
        )
    else:
        st.info(
            """
COMPRESSOR OFFLINE
"""
        )

    # --------------------------------------------------------------
    # PERFORMANCE PANELS
    # --------------------------------------------------------------

    p1, p2, p3 = st.columns(3)

    with p1:
        st.write("### ⚙️ Performance")
        st.progress(min(1.0, pressure / 130))
        st.metric("Runtime", f"{runtime} sec")
        st.metric("Maintenance Counter", maint)

    with p2:
        st.write("### 🌡️ Temperatures")
        st.metric("Stage 1", f"{s1_temp} °C")
        st.metric("Intercooler", f"{intercool} °C")
        st.metric("Stage 2", f"{s2_temp} °C")

    with p3:
        st.write("### 💨 Air Quality")
        st.metric("PDP", f"{pdp} °C")
        st.metric("Condensate", f"{condensate}%")
        st.metric("Dryer Load", f"{desiccant}%")

    st.divider()

    # --------------------------------------------------------------
    # ENVIRONMENT
    # --------------------------------------------------------------

    st.subheader("🌍 Environment")

    e1, e2, e3 = st.columns(3)

    e1.metric("Ambient Temperature", f"{ambient_temp} °C")
    e2.metric("Relative Humidity", f"{rh}%")
    e3.metric("Plant Demand", f"{plant_demand} CFM")

    st.divider()

    # --------------------------------------------------------------
    # TWIN TOWER DRYER
    # --------------------------------------------------------------

    st.subheader("🧪 Twin Tower Dryer")

    d1, d2, d3, d4 = st.columns(4)

    d1.metric("Tower A", f"{tower_a}%")
    d2.metric("Tower B", f"{tower_b}%")
    d3.metric("Active Tower", "A" if active_tower == 0 else "B")
    d4.metric("Switch In", f"{cycle_timer}s")

    if active_tower == 0:
        st.info(
            """
AIR IN
  ↓
[TOWER A : DRYING]
  ↓
PLANT HEADER

[TOWER B : REGENERATING]
"""
        )
    else:
        st.info(
            """
AIR IN
  ↓
[TOWER B : DRYING]
  ↓
PLANT HEADER

[TOWER A : REGENERATING]
"""
        )

    st.divider()

    # --------------------------------------------------------------
    # MAINTENANCE
    # --------------------------------------------------------------

    st.subheader("🔧 Maintenance")

    if maintenance_due == 1:
        st.warning(
            """
⚠️ Maintenance Due

Recommended Actions:

• Inspect intake filter
• Inspect dryer towers
• Drain condensate separator
• Check cooling system
• Verify pressure sensors
"""
        )
    else:
        st.success("✅ Maintenance Status Healthy")

    st.divider()

    # --------------------------------------------------------------
    # TREND STORAGE
    # --------------------------------------------------------------

    st.session_state.trend.append(
        {
            "Pressure": pressure,
            "Power": power,
            "Airflow": airflow,
            "Tower A": tower_a,
            "Tower B": tower_b,
            "PDP": pdp
        }
    )

    if len(st.session_state.trend) > 180:
        st.session_state.trend.pop(0)

    df = pd.DataFrame(st.session_state.trend)

    # --------------------------------------------------------------
    # LIVE TRENDS
    # --------------------------------------------------------------

    st.subheader("📈 Live Trends")

    st.line_chart(df[["Pressure", "Power", "Airflow"]])
    st.line_chart(df[["Tower A", "Tower B"]])
    st.line_chart(df[["PDP"]])

    st.divider()

    # --------------------------------------------------------------
    # LIVE DATA TABLE
    # --------------------------------------------------------------

    st.subheader("📋 Live Process Data")

    live_df = pd.DataFrame(
        {
            "Parameter": [
                "Pressure",
                "VSD Speed",
                "Power",
                "Airflow",
                "Stage1 Temp",
                "Intercooler Temp",
                "Stage2 Temp",
                "PDP",
                "Tower A",
                "Tower B",
                "Active Tower"
            ],
            "Value": [
                f"{pressure:.1f} PSI",
                f"{vsd} %",
                f"{power:.1f} kW",
                f"{airflow} CFM",
                f"{s1_temp} °C",
                f"{intercool} °C",
                f"{s2_temp} °C",
                f"{pdp} °C",
                f"{tower_a} %",
                f"{tower_b} %",
                "Tower A" if active_tower == 0 else "Tower B"
            ]
        }
    )

    st.dataframe(live_df, use_container_width=True)


# ==================================================================
# RUN DASHBOARD
# ==================================================================

dashboard()
