# AC0TG Antenna Rotator GUI

**Ken – AC0TG**

Python scripts that provide a simple compass-style GUI for controlling an HF beam antenna rotator.  
Works with either **N3FJP** logging software or **N1MM Logger+** and sends commands to a `rotctld` (Hamlib) instance.

---

## Features

- Clean black compass face with N/E/S/W and degree marks
- Current antenna position shown as a 60° medium-grey wedge with a red center line
- Commanded heading shown as a green dashed line
- Start/Stop button (bottom right) — disables rotator commands when you’re on a different antenna
- When stopped, the commanded display shows **Cmd: OFF** in red
- Configurable update rate, minimum movement threshold, long-path option (N3FJP), etc.
- Automatic reconnection
- Public domain — free to use, modify, and distribute

## Requirements

- Python 3.6 or newer (tkinter is included with most Windows Python installs)
- N3FJP software **or** N1MM Logger+
- `rotctld` (from Hamlib) running and reachable on the network

## Quick Start

1. Download or clone this repository.
2. Edit the `CONFIG` section at the top of the script you want to use.
3. Double-click the matching `.bat` file, or run:
   ```bash
   python n3fjp_rotator_gui.py
   ```
   or
   ```bash
   python n1mm_rotator_gui.py
   ```

## Configuration

Open the `.py` file and edit the values near the top:

```python
# Common settings (both scripts)
ROTCTLD_HOST = "192.168.1.100"    # IP of the computer running rotctld
ROTCTLD_PORT = 4533               # Default rotctld port
ELEVATION = 0.0                   # Usually 0 for HF beams
MIN_AZ_CHANGE = 5                 # Degrees of change required before moving
UPDATE_INTERVAL = 2.0             # How often the display refreshes (seconds)
```

### N3FJP-specific

```python
N3FJP_HOST = "127.0.0.1"
N3FJP_PORT = 1100
USE_LONGPATH = False              # Set True to use long-path bearing
```

In N3FJP:  
**Settings → Application Program Interface** → check **TCP API Enabled (Server)**.

### N1MM Logger+-specific

```python
N1MM_LISTEN_PORT = 12040          # Default N1MM rotor UDP port
```

In N1MM:  
**Config → Configure Ports… → Broadcast Data** → set **Rotor** to `127.0.0.1:12040`  
(or the IP of the machine running the script).

Then enter a callsign and press **Alt+J** (Tools → Turn Rotor).

## Usage

1. Start `rotctld` on the rotator computer.
2. Start the Python script.
3. In your logger:
   - **N3FJP**: Enter a callsign and Tab out of the Call field.
   - **N1MM**: Enter a callsign and press **Alt+J**.
4. The green commanded line jumps to the new heading and the red wedge follows as the antenna turns.
5. Click **Stop** when you switch to a different antenna (commands are ignored). Click **Start** to resume.

The current position is polled from `rotctld` every `UPDATE_INTERVAL` seconds.

## Files

| File                         | Description                          |
|------------------------------|--------------------------------------|
| `n3fjp_rotator_gui.py`       | N3FJP version with compass GUI       |
| `n1mm_rotator_gui.py`        | N1MM Logger+ version with compass GUI|
| `start_rotator_gui.bat`      | Easy launcher for N3FJP version      |
| `start_n1mm_rotator_gui.bat` | Easy launcher for N1MM version       |

## License

This code is released into the **public domain**.  
You are free to use, modify, and distribute it for any purpose without restriction.

## Links

- Blog: [AC0TG.com](https://ac0tg.com)
- YouTube: [youtube.com/@Ken-AC0TG](https://youtube.com/@Ken-AC0TG)

73,  
**Ken – AC0TG**
