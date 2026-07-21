# ZT37VSD Digital Twin — Streamlit App

A single-file, self-contained Streamlit dashboard. No separate server
process, no open TCP ports, no `pymodbus` dependency — everything
that used to live in `app_server_v2.py` (the asyncio Modbus server)
now runs as a plain Python function (`step_simulation()`) driven by
Streamlit's own autorefresh, storing state in `st.session_state`
instead of Modbus holding registers.

## Why this was necessary

The original two-file setup (`app_v2.py` talking to `app_server_v2.py`
over Modbus TCP on `127.0.0.1:5020`) only works if both processes are
started together on the same machine, with the port free and
reachable. That's not something a normal Streamlit deployment
(Streamlit Community Cloud, most PaaS/container platforms) can do:
there's no way to launch a second background process, `localhost`
isn't guaranteed persistent across app restarts/reloads, and multiple
users would collide on a single global simulation. Folding the
simulator into the same script and same session state removes all of
that — each browser session gets its own independent simulation, and
the whole thing is just one file.

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Deploy on Streamlit Community Cloud

1. Push `app.py` and `requirements.txt` to a GitHub repo.
2. Go to https://share.streamlit.io → "New app" → point it at the
   repo/branch and set the main file path to `app.py`.
3. Deploy. No secrets, ports, or extra services needed.

Any other Streamlit-compatible host (Render, Railway, Hugging Face
Spaces, a Docker container running `streamlit run app.py`, etc.) works
the same way — just make sure `requirements.txt` is installed.

## What's simulated

Everything from the original twin: startup/shutdown sequencing,
load/unload pressure control, VSD speed, power draw, stage
temperatures, condensate/desiccant load, twin-tower dryer switching,
pressure dew point, a maintenance counter, and fault/trip logic
(high stage-2 temp, dryer saturation, overpressure). Controls
(START/STOP/RESET TRIP) and setpoint sliders (pressure, ambient
temp, plant demand) write straight into the same session state the
simulation reads from — no network round trip.

## Notes / limitations

- State is per browser session (`st.session_state`), so each visitor
  gets their own independent compressor — this matches how Streamlit
  apps are meant to work, but means the twin doesn't persist if you
  close the tab or the app restarts.
- The register/int clamping (`modbus_safe`, 0–65535) was kept
  intentionally so the underlying numeric behavior matches the
  original Modbus-based simulation exactly.
