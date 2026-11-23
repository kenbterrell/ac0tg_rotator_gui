#!/usr/bin/env python3
"""
N3FJP to rotctld Antenna Rotator Controller with Compass GUI
(with debounce to ignore intermediate prefix bearings while typing)

Connects to N3FJP logging software TCP API, listens for CALLTABEVENT
(bearing when operator tabs from the Call field), and commands a remote
rotctld instance.

Debounce: waits a short time after the last bearing update before
commanding the rotator, so intermediate prefix-based bearings (while
typing) are ignored and only the final bearing is used.

Includes a small compass-style GUI:
- Current azimuth shown as a 60° wide medium-grey wedge with a red center line
- Commanded azimuth shown as a green line (or "OFF" in red when stopped)
- Start/Stop button in bottom-right corner
- Manual "Read Bearing" button in bottom-center (sends CALLTAB to N3FJP)
- Updates every few seconds (configurable)

Requirements:
- Python 3.6+ (standard library only — tkinter is included)
- N3FJP with TCP API Enabled (Server), default port 1100
- rotctld running (default port 4533)

Usage:
1. Edit the CONFIG section below.
2. Run: python n3fjp_rotator_gui.py
3. Enter a callsign in N3FJP and Tab out of the Call field.
"""

import socket
import re
import time
import threading
import math
import tkinter as tk
import queue

# ===================== CONFIG =====================
N3FJP_HOST = "127.0.0.1"          # IP of the PC running N3FJP
N3FJP_PORT = 1100                 # Default N3FJP API port

ROTCTLD_HOST = "192.168.10.135"    # IP of the PC running rotctld
ROTCTLD_PORT = 4533               # Default rotctld port

USE_LONGPATH = False              # True = use LONGPATH bearing
ELEVATION = 0.0                   # Elevation (most HF beams are AZ only)
MIN_AZ_CHANGE = 5                 # Minimum degrees change before new command

UPDATE_INTERVAL = 2.0             # Seconds between GUI / current-position updates
DEBOUNCE_SECONDS = 1.2            # Wait this long after last bearing before commanding
                                  # (avoids intermediate prefix bearings while typing)
RECONNECT_DELAY = 5               # Seconds before reconnect attempts

DEBUG = True                     # True = print all N3FJP traffic and rotctld commands
# ==================================================

# Shared state (protected by lock)
state_lock = threading.Lock()
current_azimuth = None            # from rotctld poll
commanded_azimuth = None          # last commanded heading
last_commanded = None             # for change detection
rotator_enabled = True            # Start/Stop toggle

# Debounce state
pending_azimuth = None
pending_timer = None
debounce_lock = threading.Lock()

# Command queue for sending messages to N3FJP from the GUI
cmd_queue = queue.Queue()

def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}")

def debug(msg):
    if DEBUG:
        print(f"[{time.strftime('%H:%M:%S')}] DEBUG: {msg}")

def send_to_rotctld(azimuth):
    """Send set_pos command to rotctld."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(5)
            s.connect((ROTCTLD_HOST, ROTCTLD_PORT))
            cmd = f"P {azimuth:.1f} {ELEVATION:.1f}\n"
            debug(f"TO rotctld: {cmd.strip()}")
            s.sendall(cmd.encode("ascii"))
            response = s.recv(1024).decode("ascii", errors="ignore")
            debug(f"FROM rotctld: {response.strip()}")
            if "RPRT 0" in response or not response.strip():
                log(f"rotctld: commanded to AZ {azimuth:.1f}°")
                return True
            else:
                log(f"rotctld unexpected response: {response.strip()}")
                return False
    except Exception as e:
        log(f"rotctld command error: {e}")
        return False

def get_current_azimuth():
    """Poll rotctld for current azimuth. Returns float or None.
    (Position polls are intentionally not logged in DEBUG.)
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(3)
            s.connect((ROTCTLD_HOST, ROTCTLD_PORT))
            s.sendall(b"p\n")
            response = s.recv(1024).decode("ascii", errors="ignore")
            lines = [ln.strip() for ln in response.splitlines() if ln.strip()]
            if lines:
                try:
                    return float(lines[0]) % 360
                except ValueError:
                    pass
    except Exception:
        pass
    return None

def extract_bearing(xml_msg):
    tag = "LONGPATH" if USE_LONGPATH else "BEARING"
    match = re.search(rf"<{tag}>([\d.]+)</{tag}>", xml_msg, re.IGNORECASE)
    if match:
        try:
            return float(match.group(1)) % 360
        except ValueError:
            return None
    return None

def schedule_command(az):
    """Debounce: schedule the rotator command after DEBOUNCE_SECONDS of no new bearings."""
    global pending_azimuth, pending_timer

    def do_command():
        global pending_azimuth, pending_timer, commanded_azimuth, last_commanded
        with debounce_lock:
            to_send = pending_azimuth
            pending_azimuth = None
            pending_timer = None
        if to_send is None:
            return

        with state_lock:
            enabled = rotator_enabled
            prev = last_commanded

        if not enabled:
            log(f"Bearing {to_send:.1f}° ignored (rotator disabled)")
            return

        diff = 0 if prev is None else min(abs(to_send - prev), 360 - abs(to_send - prev))
        if prev is None or diff >= MIN_AZ_CHANGE:
            log(f"Commanding rotator to {to_send:.1f}°")
            if send_to_rotctld(to_send):
                with state_lock:
                    commanded_azimuth = to_send
                    last_commanded = to_send

    with debounce_lock:
        pending_azimuth = az
        if pending_timer is not None:
            pending_timer.cancel()
        pending_timer = threading.Timer(DEBOUNCE_SECONDS, do_command)
        pending_timer.daemon = True
        pending_timer.start()

def n3fjp_listener():
    """Background thread: listen for CALLTABEVENT and schedule rotator command.
    Also sends any queued commands to N3FJP.
    """
    buffer = ""
    while True:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.connect((N3FJP_HOST, N3FJP_PORT))
                sock.settimeout(0.5)  # so we can check the command queue periodically
                log("Connected to N3FJP API")
                while True:
                    # Check for outgoing commands
                    try:
                        while True:
                            cmd = cmd_queue.get_nowait()
                            debug(f"TO N3FJP: {cmd.strip()}")
                            sock.sendall(cmd.encode("ascii"))
                            log(f"Sent to N3FJP: {cmd.strip()}")
                    except queue.Empty:
                        pass

                    try:
                        data = sock.recv(4096)
                        if not data:
                            break
                        chunk = data.decode("ascii", errors="ignore")
                        if DEBUG and chunk.strip():
                            debug(f"FROM N3FJP: {chunk.strip()}")
                        buffer += chunk
                        while "</CMD>" in buffer:
                            end = buffer.find("</CMD>") + len("</CMD>")
                            msg = buffer[:end]
                            buffer = buffer[end:]
                            if "<CALLTABEVENT>" in msg:
                                az = extract_bearing(msg)
                                if az is not None:
                                    log(f"Bearing update received: {az:.1f}° (debouncing)")
                                    schedule_command(az)
                    except socket.timeout:
                        continue
        except Exception as e:
            log(f"N3FJP connection error: {e}")
            time.sleep(RECONNECT_DELAY)

def request_bearing():
    """Send CALLTAB action to N3FJP to force a bearing lookup for the current callsign."""
    cmd = "<CMD><ACTION><VALUE>CALLTAB</VALUE></CMD>"
    cmd_queue.put(cmd)
    log("Requested manual bearing read from N3FJP")

class CompassApp:
    def __init__(self, root):
        self.root = root
        self.root.title("N3FJP Rotator Compass")
        self.root.geometry("400x400")
        self.root.resizable(False, False)
        self.root.configure(bg="#000000")

        self.canvas = tk.Canvas(root, width=400, height=400, bg="#000000",
                                 highlightthickness=0, bd=0)
        self.canvas.pack(fill="both", expand=True)

        self.center = 200
        self.radius = 165

        # Stop/Start button - bottom right
        self.btn = tk.Button(root, text="Stop", width=8, font=("Segoe UI", 9, "bold"),
                             bg="#333333", fg="#ffffff", activebackground="#555555",
                             command=self.toggle_rotator)
        self.btn.place(relx=1.0, rely=1.0, anchor="se", x=-8, y=-8)

        # Read Bearing button - bottom center
        self.read_btn = tk.Button(root, text="Read Bearing", width=12, font=("Segoe UI", 9, "bold"),
                                  bg="#333333", fg="#ffffff", activebackground="#555555",
                                  command=request_bearing)
        self.read_btn.place(relx=0.5, rely=1.0, anchor="s", y=-8)

        threading.Thread(target=n3fjp_listener, daemon=True).start()
        self.update_display()

    def polar_to_xy(self, angle_deg, r):
        rad = math.radians(angle_deg - 90)
        x = self.center + r * math.cos(rad)
        y = self.center + r * math.sin(rad)
        return x, y

    def draw_compass(self):
        c = self.canvas
        c.delete("all")
        cx, cy, r = self.center, self.center, self.radius

        c.create_oval(cx - r, cy - r, cx + r, cy + r, outline="#555555", width=2)

        for deg in range(0, 360, 10):
            outer = r if deg % 30 == 0 else r - 8
            x1, y1 = self.polar_to_xy(deg, r - 2)
            x2, y2 = self.polar_to_xy(deg, outer)
            color = "#888" if deg % 30 == 0 else "#555"
            c.create_line(x1, y1, x2, y2, fill=color, width=2 if deg % 30 == 0 else 1)

        labels = [(0, "N"), (90, "E"), (180, "S"), (270, "W")]
        for ang, text in labels:
            x, y = self.polar_to_xy(ang, r - 28)
            c.create_text(x, y, text=text, fill="#ccc", font=("Segoe UI", 14, "bold"))

        for deg in range(0, 360, 30):
            if deg % 90 != 0:
                x, y = self.polar_to_xy(deg, r - 22)
                c.create_text(x, y, text=str(deg), fill="#888", font=("Segoe UI", 9))

        with state_lock:
            curr = current_azimuth
            cmd = commanded_azimuth
            enabled = rotator_enabled

        if curr is not None:
            half = 30
            points = [cx, cy]
            for a in range(int(curr - half), int(curr + half) + 1, 2):
                px, py = self.polar_to_xy(a % 360, r - 35)
                points.extend([px, py])
            if len(points) > 4:
                c.create_polygon(points, fill="#808080", outline="")

            x1, y1 = self.polar_to_xy(curr, 25)
            x2, y2 = self.polar_to_xy(curr, r - 12)
            c.create_line(x1, y1, x2, y2, fill="#ff2222", width=3)

        if enabled and cmd is not None:
            x1, y1 = self.polar_to_xy(cmd, 35)
            x2, y2 = self.polar_to_xy(cmd, r - 22)
            c.create_line(x1, y1, x2, y2, fill="#22ff22", width=2, dash=(5, 3))
            tipx, tipy = self.polar_to_xy(cmd, r - 18)
            c.create_oval(tipx - 4, tipy - 4, tipx + 4, tipy + 4, fill="#22ff22", outline="")

        curr_text = f"Current: {curr:.1f}°" if curr is not None else "Current: ---°"
        if enabled:
            cmd_text = f"Cmd: {cmd:.1f}°" if cmd is not None else "Cmd: ---°"
            cmd_color = "#66ff66"
        else:
            cmd_text = "Cmd: OFF"
            cmd_color = "#ff4444"

        c.create_text(12, 18, text=curr_text, fill="#ff6666", font=("Segoe UI", 12, "bold"), anchor="nw")
        c.create_text(388, 18, text=cmd_text, fill=cmd_color, font=("Segoe UI", 12, "bold"), anchor="ne")

        c.create_oval(cx - 5, cy - 5, cx + 5, cy + 5, fill="#666", outline="#aaa")

    def update_display(self):
        global current_azimuth
        az = get_current_azimuth()
        with state_lock:
            current_azimuth = az
        self.draw_compass()
        self.root.after(int(UPDATE_INTERVAL * 1000), self.update_display)

    def toggle_rotator(self):
        global rotator_enabled
        with state_lock:
            rotator_enabled = not rotator_enabled
            enabled = rotator_enabled
        if enabled:
            self.btn.config(text="Stop", bg="#333333")
            log("Rotator ENABLED")
        else:
            self.btn.config(text="Start", bg="#664444")
            log("Rotator DISABLED")
        self.draw_compass()

def main():
    root = tk.Tk()
    app = CompassApp(root)
    log(f"GUI started — update every {UPDATE_INTERVAL}s, debounce {DEBOUNCE_SECONDS}s")
    log(f"N3FJP: {N3FJP_HOST}:{N3FJP_PORT}  |  rotctld: {ROTCTLD_HOST}:{ROTCTLD_PORT}")
    if DEBUG:
        log("DEBUG mode enabled")
    root.mainloop()

if __name__ == "__main__":
    main()
