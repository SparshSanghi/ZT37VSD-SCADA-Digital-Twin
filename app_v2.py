import streamlit as st
from pymodbus.client import ModbusTcpClient
import pandas as pd

st.set_page_config(
    page_title="ZT37VSD Digital Twin",
    layout="wide"
)

st.title("🏭 Atlas Copco ZT37VSD Digital Twin")
st.caption(
    "Industrial Compressor + Twin Tower Dryer Simulation"
)

# ==================================================
# MODBUS
# ==================================================

if "client" not in st.session_state:

    client = ModbusTcpClient(
        "127.0.0.1",
        port=5020
    )

    client.connect()

    st.session_state.client = client

client = st.session_state.client

if "trend" not in st.session_state:
    st.session_state.trend = []

# ==================================================
# CONTROLS
# ==================================================

st.subheader("🎮 Compressor Controls")

c1, c2, c3 = st.columns(3)

with c1:

    if st.button(
        "🟢 START",
        use_container_width=True
    ):

        client.write_register(
            address=10,
            value=1,
            slave=0
        )

with c2:

    if st.button(
        "🔴 STOP",
        use_container_width=True
    ):

        client.write_register(
            address=10,
            value=0,
            slave=0
        )

with c3:

    if st.button(
        "🟡 RESET TRIP",
        use_container_width=True
    ):

        client.write_register(
            address=11,
            value=1,
            slave=0
        )

st.divider()

# ==================================================
# PROCESS SETTINGS
# ==================================================

st.subheader("⚙️ Process Settings")

s1, s2, s3 = st.columns(3)

with s1:

    setpoint = st.slider(
        "Pressure Setpoint (PSI)",
        80,
        130,
        102
    )

    client.write_register(
        address=13,
        value=setpoint * 10,
        slave=0
    )

with s2:

    ambient_temp = st.slider(
        "Ambient Temperature (°C)",
        10,
        50,
        30
    )

    client.write_register(
        address=24,
        value=ambient_temp,
        slave=0
    )

with s3:

    plant_demand = st.slider(
        "Plant Demand (CFM)",
        20,
        250,
        40
    )

    client.write_register(
        address=25,
        value=plant_demand,
        slave=0
    )

st.divider()

# ==================================================
# DASHBOARD
# ==================================================

@st.fragment(run_every=1)
def dashboard():

    try:

        packet = client.read_holding_registers(
            address=0,
            count=27,
            slave=0
        )

        if packet.isError():

            st.error(
                "⚠️ Communication Failure"
            )

            return

    except Exception as e:

        st.error(str(e))
        return

    r = packet.registers

    pressure = r[0] / 10.0
    vsd = r[1]

    s1_temp = r[2]
    intercool = r[3]
    s2_temp = r[4]

    condensate = r[5]
    desiccant = r[6]

    pdp = r[7] - 100

    rh = r[8]
    state = r[9]

    fault = r[14]

    runtime = r[15]

    power = r[16] / 10.0
    airflow = r[17]

    maint = r[18]

    tower_a = r[20]
    tower_b = r[21]

    active_tower = r[22]
    cycle_timer = r[23]

    ambient_temp = r[24]
    plant_demand = r[25]

    maintenance_due = r[26]
    # ==================================================
    # STATE / FAULT MAPS
    # ==================================================

    states = {
        0: "READY",
        1: "STARTING",
        2: "LOADED",
        3: "UNLOADED",
        4: "SHUTDOWN",
        5: "TRIP"
    }

    faults = {
        0: "No Fault",
        1: "High Stage 2 Temperature",
        2: "Dryer Saturation",
        3: "Overpressure",
        4: "Maintenance Due"
    }

    # ==================================================
    # STATUS BAR
    # ==================================================

    st.subheader(
        f"Machine State : {states.get(state,'UNKNOWN')}"
    )

    if state == 5:

        st.error(
            f"🚨 TRIP : {faults.get(fault)}"
        )

    elif fault != 0:

        st.warning(
            f"⚠️ {faults.get(fault)}"
        )

    else:

        st.success(
            "✅ System Healthy"
        )

    # ==================================================
    # KPI SECTION
    # ==================================================

    k1, k2, k3, k4 = st.columns(4)

    k1.metric(
        "Pressure",
        f"{pressure:.1f} PSI"
    )

    k2.metric(
        "VSD Speed",
        f"{vsd}%"
    )

    k3.metric(
        "Power",
        f"{power:.1f} kW"
    )

    k4.metric(
        "Airflow",
        f"{airflow} CFM"
    )

    st.divider()

    # ==================================================
    # COMPRESSOR MIMIC
    # ==================================================

    st.subheader(
        "🌀 Compressor Process Flow"
    )

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

    # ==================================================
    # PERFORMANCE PANELS
    # ==================================================

    p1, p2, p3 = st.columns(3)

    with p1:

        st.write(
            "### ⚙️ Performance"
        )

        st.progress(
            min(
                1.0,
                pressure / 130
            )
        )

        st.metric(
            "Runtime",
            f"{runtime} sec"
        )

        st.metric(
            "Maintenance Counter",
            maint
        )

    with p2:

        st.write(
            "### 🌡️ Temperatures"
        )

        st.metric(
            "Stage 1",
            f"{s1_temp} °C"
        )

        st.metric(
            "Intercooler",
            f"{intercool} °C"
        )

        st.metric(
            "Stage 2",
            f"{s2_temp} °C"
        )

    with p3:

        st.write(
            "### 💨 Air Quality"
        )

        st.metric(
            "PDP",
            f"{pdp} °C"
        )

        st.metric(
            "Condensate",
            f"{condensate}%"
        )

        st.metric(
            "Dryer Load",
            f"{desiccant}%"
        )

    st.divider()

    # ==================================================
    # ENVIRONMENT
    # ==================================================

    st.subheader(
        "🌍 Environment"
    )

    e1, e2, e3 = st.columns(3)

    e1.metric(
        "Ambient Temperature",
        f"{ambient_temp} °C"
    )

    e2.metric(
        "Relative Humidity",
        f"{rh}%"
    )

    e3.metric(
        "Plant Demand",
        f"{plant_demand} CFM"
    )

    st.divider()

    # ==================================================
    # TWIN TOWER DRYER
    # ==================================================

    st.subheader(
        "🧪 Twin Tower Dryer"
    )

    d1, d2, d3, d4 = st.columns(4)

    d1.metric(
        "Tower A",
        f"{tower_a}%"
    )

    d2.metric(
        "Tower B",
        f"{tower_b}%"
    )

    d3.metric(
        "Active Tower",
        "A"
        if active_tower == 0
        else "B"
    )

    d4.metric(
        "Switch In",
        f"{cycle_timer}s"
    )

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
    # ==================================================
    # MAINTENANCE
    # ==================================================

    st.subheader(
        "🔧 Maintenance"
    )

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

        st.success(
            "✅ Maintenance Status Healthy"
        )

    st.divider()

    # ==================================================
    # TREND STORAGE
    # ==================================================

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

    df = pd.DataFrame(
        st.session_state.trend
    )

    # ==================================================
    # LIVE TRENDS
    # ==================================================

    st.subheader(
        "📈 Live Trends"
    )

    st.line_chart(
        df[
            [
                "Pressure",
                "Power",
                "Airflow"
            ]
        ]
    )

    st.line_chart(
        df[
            [
                "Tower A",
                "Tower B"
            ]
        ]
    )

    st.line_chart(
        df[
            [
                "PDP"
            ]
        ]
    )

    st.divider()

    # ==================================================
    # LIVE DATA TABLE
    # ==================================================

    st.subheader(
        "📋 Live Process Data"
    )

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
                (
                    "Tower A"
                    if active_tower == 0
                    else "Tower B"
                )
            ]
        }
    )

    st.dataframe(
        live_df,
        use_container_width=True
    )

# ==================================================
# RUN DASHBOARD
# ==================================================

dashboard()