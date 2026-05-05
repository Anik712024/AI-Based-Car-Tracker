import tkinter as tk
from tkinter import ttk, messagebox
import datetime
import random
import threading
import urllib.request
import json
import queue

# ─── Optional OpenCV import ───────────────────────────────────────────────────
try:
    import cv2
    from PIL import Image, ImageTk
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False

# ─── Online criminal plate list ───────────────────────────────────────────────
# Replace this URL with your own JSONbin.io bin URL:
# 1. Go to https://jsonbin.io and create a free account
# 2. Create a new bin with content: {"plates": ["DHA-1142", "KHI-5507"]}
# 3. Paste your bin's API URL below
CRIMINAL_LIST_URL = "https://api.jsonbin.io/v3/b/YOUR_BIN_ID/latest"

criminal_plates = set()   # fast O(1) lookup set

def refresh_criminal_list():
    """Fetch the criminal plate list from the online JSON bin."""
    global criminal_plates
    try:
        req = urllib.request.Request(
            CRIMINAL_LIST_URL,
            headers={"X-Bin-Meta": "false"}  # JSONbin: return data only
        )
        with urllib.request.urlopen(req, timeout=5) as r:
            data = json.load(r)
            new_plates = set(p.strip().upper() for p in data.get("plates", []))
            criminal_plates = new_plates
            criminal_count_var.set(str(len(criminal_plates)))
            update_criminal_tree()
    except Exception as e:
        # Silently fail — keep using the last known list
        print(f"Could not refresh criminal list: {e}")
    root.after(60_000, refresh_criminal_list)   # refresh every 60 seconds

def push_criminal_list():
    """Push the local criminal list back to JSONbin (requires API key in URL or header)."""
    messagebox.showinfo(
        "Update online list",
        "To update the online list, log in to jsonbin.io and edit your bin directly.\n\n"
        "Or set up an API key to enable push from this app."
    )

# ─── App state (replaces bare globals) ────────────────────────────────────────
class AppState:
    def __init__(self):
        self.cars = []             # full detection log
        self.total = 0
        self.violations = 0
        self.speed_sum = 0
        self.criminal_hits = 0

state = AppState()

# ─── Detection logic (stub) ───────────────────────────────────────────────────
def simulate_detection():
    """Replace with your real camera + OCR pipeline."""
    plates = ["DHA-1142", "CHI-8823", "RAJ-3391", "KHI-5507", "LHR-2204",
              "MUL-7731", "ISB-4402", "PES-9918"]
    plate = random.choice(plates)
    speed = random.randint(40, 180)
    return plate, speed

# ─── Core actions ─────────────────────────────────────────────────────────────
SPEED_LIMIT = 80  # km/h

def detect_and_log():
    plate, speed = simulate_detection()
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d  %H:%M:%S")

    is_criminal = plate.upper() in criminal_plates

    if is_criminal:
        status = "CRIMINAL"
    elif speed > int(speed_limit_var.get()):
        status = "OVER LIMIT"
    else:
        status = "Normal"

    entry = {"plate": plate, "speed": speed, "timestamp": timestamp, "status": status}
    state.cars.append(entry)

    # Update running totals — no need to re-scan the whole list
    state.total += 1
    state.speed_sum += speed
    if status == "OVER LIMIT":
        state.violations += 1
    if status == "CRIMINAL":
        state.criminal_hits += 1

    tag = "criminal" if status == "CRIMINAL" else ("over" if status == "OVER LIMIT" else "normal")
    tree.insert("", 0, values=(plate, f"{speed} km/h", timestamp, status), tags=(tag,))
    update_stats()
    status_bar.config(text=f"Last detection: {plate}  |  {speed} km/h  |  {timestamp}")

    live_plate_var.set(plate)
    live_speed_var.set(f"{speed} km/h")
    live_status_var.set(status)

    # Auto-track criminal vehicles
    if is_criminal:
        trigger_camera_track(plate)

def trigger_camera_track(plate):
    """Called when a criminal plate is detected — auto-starts camera and alerts."""
    if camera_cap is None:
        start_camera()
    status_bar.config(
        text=f"  ALERT: Criminal vehicle detected — {plate} — Camera tracking active",
        foreground="#dc2626"
    )
    messagebox.showwarning(
        "Criminal vehicle detected",
        f"Plate  {plate}  is on the criminal watch list!\n\nCamera tracking has been activated."
    )

# ─── Cached search (avoids full rebuild when query hasn't changed) ─────────────
_last_search_query = None

def search_plate():
    global _last_search_query
    query = search_var.get().strip().upper()
    if query == _last_search_query:
        return              # nothing changed — skip expensive rebuild
    _last_search_query = query

    for item in tree.get_children():
        tree.delete(item)

    results = [c for c in state.cars if query in c["plate"].upper()] if query else state.cars
    for c in reversed(results):
        tag = "criminal" if c["status"] == "CRIMINAL" else ("over" if c["status"] == "OVER LIMIT" else "normal")
        tree.insert("", "end", values=(c["plate"], f"{c['speed']} km/h", c["timestamp"], c["status"]), tags=(tag,))

    status_bar.config(text=f"Search: {len(results)} result(s) for '{query}'" if query else "Showing all records")

def clear_search():
    global _last_search_query
    _last_search_query = None
    search_var.set("")
    search_plate()

def clear_all():
    if messagebox.askyesno("Clear records", "Delete all tracked records?"):
        state.cars.clear()
        state.total = 0
        state.violations = 0
        state.speed_sum = 0
        state.criminal_hits = 0
        for item in tree.get_children():
            tree.delete(item)
        update_stats()
        status_bar.config(text="All records cleared.")

def update_stats():
    """Uses running totals — no full-list scan."""
    avg = (state.speed_sum / state.total) if state.total else 0
    lbl_total.config(text=str(state.total))
    lbl_violations.config(text=str(state.violations))
    lbl_avg.config(text=f"{avg:.1f} km/h")
    lbl_criminals.config(text=str(state.criminal_hits))

def export_txt():
    if not state.cars:
        messagebox.showinfo("Export", "No records to export.")
        return
    fname = f"car_log_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    with open(fname, "w") as f:
        f.write(f"{'Plate':<14}{'Speed':<12}{'Timestamp':<22}{'Status'}\n")
        f.write("-" * 60 + "\n")
        for c in state.cars:
            f.write(f"{c['plate']:<14}{c['speed']:<12}{c['timestamp']:<22}{c['status']}\n")
    messagebox.showinfo("Exported", f"Saved as:  {fname}")
    status_bar.config(text=f"Exported → {fname}")

# ─── Toggle live detection ─────────────────────────────────────────────────────
live_job = None

def toggle_live():
    global live_job
    if live_job is None:
        btn_live.config(text="⏹  Stop Live", style="Danger.TButton")
        _run_live()
    else:
        root.after_cancel(live_job)
        live_job = None
        btn_live.config(text="▶  Start Live", style="Accent.TButton")
        status_bar.config(text="Live detection stopped.")

def _run_live():
    global live_job
    detect_and_log()
    interval = int(interval_var.get()) * 1000
    live_job = root.after(interval, _run_live)

# ─── Live video feed (threaded frame reading) ──────────────────────────────────
camera_cap    = None
camera_job    = None
frame_queue   = queue.Queue(maxsize=2)   # buffer between camera thread and UI
_camera_thread_running = False

def _camera_reader_thread():
    """Reads frames from camera in a background thread — never touches Tkinter."""
    global _camera_thread_running
    _camera_thread_running = True
    while _camera_thread_running and camera_cap and camera_cap.isOpened():
        ret, frame = camera_cap.read()
        if ret:
            if not frame_queue.full():
                frame_queue.put(frame)
    _camera_thread_running = False

def _update_frame():
    """Pulls a frame from the queue and draws it. Always runs on the UI thread."""
    global camera_job
    if camera_cap is None or not camera_cap.isOpened():
        return

    if not frame_queue.empty():
        frame = frame_queue.get_nowait()

        if CV2_AVAILABLE:
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            frame = cv2.resize(frame, (video_canvas.winfo_width() or 640,
                                       video_canvas.winfo_height() or 400))
            h, w = frame.shape[:2]

            # Bounding box
            color = (220, 38, 38) if live_status_var.get() == "CRIMINAL" else (37, 99, 235)
            cv2.rectangle(frame, (w//4, h//4), (3*w//4, 3*h//4), color, 2)

            plate_text = live_plate_var.get()
            speed_text = live_speed_var.get()
            if plate_text:
                cv2.putText(frame, f"{plate_text}  {speed_text}",
                            (w//4 + 6, h//4 - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.65, color, 2)

            # Criminal alert overlay
            if live_status_var.get() == "CRIMINAL":
                cv2.putText(frame, "! CRIMINAL VEHICLE",
                            (10, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (220, 38, 38), 2)

            img = ImageTk.PhotoImage(Image.fromarray(frame))
            video_canvas.create_image(0, 0, anchor="nw", image=img)
            video_canvas._photo = img   # prevent GC

    camera_job = root.after(30, _update_frame)   # ~33 fps

def start_camera():
    global camera_cap, camera_job
    if not CV2_AVAILABLE:
        messagebox.showerror(
            "Missing libraries",
            "opencv-python and Pillow are required for live video.\n\n"
            "Install them with:\n  pip install opencv-python Pillow"
        )
        return
    if camera_cap is not None:
        return

    src = cam_source_var.get().strip()
    try:
        src = int(src)
    except ValueError:
        pass

    camera_cap = cv2.VideoCapture(src)
    if not camera_cap.isOpened():
        messagebox.showerror("Camera error", f"Cannot open source: {src!r}")
        camera_cap = None
        return

    # Start background reader thread
    t = threading.Thread(target=_camera_reader_thread, daemon=True)
    t.start()

    btn_cam_start.config(state="disabled")
    btn_cam_stop.config(state="normal")
    cam_status_lbl.config(text="● LIVE", foreground="#22c55e")
    _update_frame()

def stop_camera():
    global camera_cap, camera_job, _camera_thread_running
    _camera_thread_running = False
    if camera_job is not None:
        root.after_cancel(camera_job)
        camera_job = None
    if camera_cap is not None:
        camera_cap.release()
        camera_cap = None
    video_canvas.delete("all")
    video_canvas.create_text(
        video_canvas.winfo_width() // 2 or 320,
        video_canvas.winfo_height() // 2 or 200,
        text="Camera stopped", fill="#6b7280", font=("Helvetica", 14)
    )
    btn_cam_start.config(state="normal")
    btn_cam_stop.config(state="disabled")
    cam_status_lbl.config(text="● OFFLINE", foreground="#6b7280")

def take_snapshot():
    if camera_cap is None or not camera_cap.isOpened():
        messagebox.showinfo("Snapshot", "Camera is not running.")
        return
    if not frame_queue.empty():
        frame = frame_queue.queue[0]   # peek without removing
        fname = f"snapshot_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
        cv2.imwrite(fname, frame)
        messagebox.showinfo("Snapshot saved", f"Saved as: {fname}")

# ─── Criminal list tab helpers ─────────────────────────────────────────────────
def update_criminal_tree():
    """Refresh the criminal plates treeview."""
    for item in criminal_tree.get_children():
        criminal_tree.delete(item)
    for plate in sorted(criminal_plates):
        criminal_tree.insert("", "end", values=(plate,))
    criminal_count_var.set(str(len(criminal_plates)))

def add_criminal_plate():
    plate = new_plate_var.get().strip().upper()
    if not plate:
        messagebox.showwarning("Add plate", "Please enter a plate number.")
        return
    if plate in criminal_plates:
        messagebox.showinfo("Add plate", f"{plate} is already in the list.")
        return
    criminal_plates.add(plate)
    new_plate_var.set("")
    update_criminal_tree()
    status_bar.config(text=f"Added {plate} to criminal list.")

def remove_criminal_plate():
    selected = criminal_tree.selection()
    if not selected:
        messagebox.showwarning("Remove plate", "Select a plate to remove.")
        return
    plate = criminal_tree.item(selected[0])["values"][0]
    criminal_plates.discard(plate)
    update_criminal_tree()
    status_bar.config(text=f"Removed {plate} from criminal list.")

# ─── Window ────────────────────────────────────────────────────────────────────
root = tk.Tk()
root.title("Car Speed Tracker")
root.geometry("960x700")
root.minsize(800, 560)
root.configure(bg="#f0f2f5")

# ─── Shared live-overlay vars ──────────────────────────────────────────────────
live_plate_var  = tk.StringVar(value="")
live_speed_var  = tk.StringVar(value="")
live_status_var = tk.StringVar(value="")
criminal_count_var = tk.StringVar(value="0")
new_plate_var   = tk.StringVar(value="")

# ─── Styles ────────────────────────────────────────────────────────────────────
style = ttk.Style(root)
style.theme_use("clam")
style.configure(".",              background="#f0f2f5", foreground="#1a1a2e", font=("Helvetica", 10))
style.configure("TFrame",        background="#f0f2f5")
style.configure("Card.TFrame",   background="#ffffff", relief="flat")
style.configure("TLabel",        background="#f0f2f5", foreground="#1a1a2e")
style.configure("Card.TLabel",   background="#ffffff")
style.configure("Header.TLabel", background="#1a1a2e", foreground="#ffffff",
                font=("Helvetica", 13, "bold"), padding=10)
style.configure("Stat.TLabel",   background="#ffffff", foreground="#1a1a2e",
                font=("Helvetica", 22, "bold"))
style.configure("StatSub.TLabel",background="#ffffff", foreground="#6b7280",
                font=("Helvetica", 9))
style.configure("Accent.TButton",  background="#2563eb", foreground="#ffffff",
                font=("Helvetica", 10, "bold"), padding=6)
style.configure("Danger.TButton",  background="#dc2626", foreground="#ffffff",
                font=("Helvetica", 10, "bold"), padding=6)
style.configure("Neutral.TButton", background="#e5e7eb", foreground="#374151",
                font=("Helvetica", 10), padding=6)
style.configure("Warning.TButton", background="#d97706", foreground="#ffffff",
                font=("Helvetica", 10, "bold"), padding=6)
style.map("Accent.TButton",  background=[("active","#1d4ed8")])
style.map("Danger.TButton",  background=[("active","#b91c1c")])
style.map("Neutral.TButton", background=[("active","#d1d5db")])
style.map("Warning.TButton", background=[("active","#b45309")])
style.configure("Treeview",
    background="#ffffff", foreground="#1a1a2e",
    fieldbackground="#ffffff", rowheight=26, font=("Helvetica", 10))
style.configure("Treeview.Heading",
    background="#1a1a2e", foreground="#ffffff", font=("Helvetica", 10, "bold"))
style.map("Treeview", background=[("selected","#dbeafe")])

# ─── Header bar ───────────────────────────────────────────────────────────────
hdr = ttk.Label(root, text="🚗  Car Speed & Criminal Tracker", style="Header.TLabel", anchor="w")
hdr.pack(fill="x")

# ─── Tab notebook ─────────────────────────────────────────────────────────────
notebook = ttk.Notebook(root)
notebook.pack(fill="both", expand=True, padx=8, pady=8)

# ════════════════════════════════════════════════════════════════════════════════
# TAB 1 — Dashboard
# ════════════════════════════════════════════════════════════════════════════════
tab_dash = ttk.Frame(notebook, padding=12)
notebook.add(tab_dash, text="📊  Dashboard")

tab_dash.columnconfigure(0, weight=1)
tab_dash.rowconfigure(3, weight=1)

# Control row
ctrl = ttk.Frame(tab_dash)
ctrl.grid(row=0, column=0, sticky="ew", pady=(0, 10))

ttk.Button(ctrl, text="📷  Detect Once", style="Accent.TButton",
           command=detect_and_log).pack(side="left", padx=(0, 6))
btn_live = ttk.Button(ctrl, text="▶  Start Live", style="Accent.TButton",
                      command=toggle_live)
btn_live.pack(side="left", padx=(0, 6))

ttk.Label(ctrl, text="Interval (s):").pack(side="left", padx=(8, 4))
interval_var = tk.StringVar(value="3")
ttk.Spinbox(ctrl, from_=1, to=30, textvariable=interval_var, width=4).pack(side="left", padx=(0, 12))

ttk.Label(ctrl, text="Speed limit (km/h):").pack(side="left", padx=(0, 4))
speed_limit_var = tk.StringVar(value=str(SPEED_LIMIT))
ttk.Spinbox(ctrl, from_=20, to=200, textvariable=speed_limit_var, width=5).pack(side="left", padx=(0, 12))

ttk.Button(ctrl, text="📤  Export",    style="Neutral.TButton", command=export_txt).pack(side="right", padx=(6, 0))
ttk.Button(ctrl, text="🗑  Clear All", style="Neutral.TButton", command=clear_all).pack(side="right", padx=(6, 0))

# Stat cards — now includes criminal hits
cards = ttk.Frame(tab_dash)
cards.grid(row=1, column=0, sticky="ew", pady=(0, 10))
for i in range(4):
    cards.columnconfigure(i, weight=1)

def make_card(parent, col, title, total_cols=4):
    padx = (0, 8) if col < total_cols - 1 else 0
    f = ttk.Frame(parent, style="Card.TFrame", padding=12)
    f.grid(row=0, column=col, sticky="ew", padx=padx)
    val = ttk.Label(f, text="0", style="Stat.TLabel")
    val.pack()
    ttk.Label(f, text=title, style="StatSub.TLabel").pack()
    return val

lbl_total      = make_card(cards, 0, "Total Detections")
lbl_violations = make_card(cards, 1, "Speed Violations")
lbl_avg        = make_card(cards, 2, "Average Speed")
lbl_criminals  = make_card(cards, 3, "Criminal Matches")

# Search bar
srow = ttk.Frame(tab_dash)
srow.grid(row=2, column=0, sticky="new", pady=(0, 6))
ttk.Label(srow, text="Search plate:").pack(side="left", padx=(0, 6))
search_var = tk.StringVar()
ttk.Entry(srow, textvariable=search_var, width=20).pack(side="left", padx=(0, 6))
ttk.Button(srow, text="Search", style="Accent.TButton",  command=search_plate).pack(side="left", padx=(0, 4))
ttk.Button(srow, text="Clear",  style="Neutral.TButton", command=clear_search).pack(side="left")

# Records table
tbl_frame = ttk.Frame(tab_dash)
tbl_frame.grid(row=3, column=0, sticky="nsew", pady=(4, 0))

cols = ("Plate Number", "Speed", "Timestamp", "Status")
tree = ttk.Treeview(tbl_frame, columns=cols, show="headings", selectmode="browse")
for c, w in zip(cols, (160, 100, 200, 130)):
    tree.heading(c, text=c)
    tree.column(c, width=w, anchor="center")
tree.tag_configure("criminal", foreground="#7c3aed", font=("Helvetica", 10, "bold"))
tree.tag_configure("over",     foreground="#dc2626", font=("Helvetica", 10, "bold"))
tree.tag_configure("normal",   foreground="#15803d")

scrollbar = ttk.Scrollbar(tbl_frame, orient="vertical", command=tree.yview)
tree.configure(yscrollcommand=scrollbar.set)
tree.pack(side="left", fill="both", expand=True)
scrollbar.pack(side="right", fill="y")

# ════════════════════════════════════════════════════════════════════════════════
# TAB 2 — Live Video Feed
# ════════════════════════════════════════════════════════════════════════════════
tab_video = ttk.Frame(notebook, padding=10)
notebook.add(tab_video, text="📹  Live Video Feed")

tab_video.columnconfigure(0, weight=1)
tab_video.rowconfigure(1, weight=1)

cam_ctrl = ttk.Frame(tab_video)
cam_ctrl.grid(row=0, column=0, sticky="ew", pady=(0, 8))

ttk.Label(cam_ctrl, text="Camera source:").pack(side="left", padx=(0, 4))
cam_source_var = tk.StringVar(value="0")
ttk.Entry(cam_ctrl, textvariable=cam_source_var, width=28).pack(side="left", padx=(0, 8))
ttk.Label(cam_ctrl, text="(0 = webcam, or RTSP URL / file path)", foreground="#6b7280",
          font=("Helvetica", 9)).pack(side="left", padx=(0, 16))

btn_cam_start = ttk.Button(cam_ctrl, text="▶  Start Camera", style="Accent.TButton",
                            command=start_camera)
btn_cam_start.pack(side="left", padx=(0, 6))

btn_cam_stop = ttk.Button(cam_ctrl, text="⏹  Stop Camera", style="Danger.TButton",
                           command=stop_camera, state="disabled")
btn_cam_stop.pack(side="left", padx=(0, 6))

ttk.Button(cam_ctrl, text="📸  Snapshot", style="Neutral.TButton",
           command=take_snapshot).pack(side="left", padx=(0, 6))

cam_status_lbl = ttk.Label(cam_ctrl, text="● OFFLINE", foreground="#6b7280",
                            font=("Helvetica", 10, "bold"))
cam_status_lbl.pack(side="right")

video_outer = ttk.Frame(tab_video)
video_outer.grid(row=1, column=0, sticky="nsew")
video_outer.columnconfigure(0, weight=1)
video_outer.columnconfigure(1, minsize=200)
video_outer.rowconfigure(0, weight=1)

video_canvas = tk.Canvas(video_outer, bg="#111827", cursor="crosshair",
                          highlightthickness=0)
video_canvas.grid(row=0, column=0, sticky="nsew")
video_canvas.create_text(320, 200, text="No camera feed\nPress ▶ Start Camera",
                          fill="#6b7280", font=("Helvetica", 14), justify="center")

side = ttk.Frame(video_outer, style="Card.TFrame", padding=14)
side.grid(row=0, column=1, sticky="nsew", padx=(8, 0))

ttk.Label(side, text="Detection Overlay", style="Card.TLabel",
          font=("Helvetica", 11, "bold")).pack(anchor="w", pady=(0, 10))

def _info_row(parent, label):
    f  = ttk.Frame(parent, style="Card.TFrame")
    f.pack(fill="x", pady=3)
    ttk.Label(f, text=label, style="Card.TLabel",
              foreground="#6b7280", font=("Helvetica", 9)).pack(anchor="w")
    val = ttk.Label(f, text="—", style="Card.TLabel",
                    font=("Helvetica", 13, "bold"))
    val.pack(anchor="w")
    return val

ov_plate  = _info_row(side, "LAST PLATE")
ov_speed  = _info_row(side, "SPEED")
ov_status = _info_row(side, "STATUS")

ttk.Separator(side, orient="horizontal").pack(fill="x", pady=10)

def _sync_overlay(*_):
    ov_plate.config(text=live_plate_var.get() or "—")
    ov_speed.config(text=live_speed_var.get() or "—")
    status_val = live_status_var.get()
    if status_val == "CRIMINAL":
        ov_status.config(text="! CRIMINAL",    foreground="#7c3aed")
    elif status_val == "OVER LIMIT":
        ov_status.config(text="⚠ OVER LIMIT", foreground="#dc2626")
    elif status_val == "Normal":
        ov_status.config(text="✓ Normal",      foreground="#15803d")
    else:
        ov_status.config(text="—",             foreground="#1a1a2e")

live_plate_var.trace_add("write", _sync_overlay)
live_speed_var.trace_add("write", _sync_overlay)

ttk.Label(side, text="Quick Detect", style="Card.TLabel",
          font=("Helvetica", 11, "bold")).pack(anchor="w", pady=(0, 6))
ttk.Button(side, text="📷  Detect Once", style="Accent.TButton",
           command=detect_and_log).pack(fill="x", pady=(0, 4))

ttk.Label(side, text="Speed limit (km/h):", style="Card.TLabel",
          foreground="#6b7280", font=("Helvetica", 9)).pack(anchor="w")
ttk.Spinbox(side, from_=20, to=200, textvariable=speed_limit_var, width=8).pack(anchor="w", pady=(2, 0))

# ════════════════════════════════════════════════════════════════════════════════
# TAB 3 — Criminal Plate List
# ════════════════════════════════════════════════════════════════════════════════
tab_criminal = ttk.Frame(notebook, padding=12)
notebook.add(tab_criminal, text="🚨  Criminal List")

tab_criminal.columnconfigure(0, weight=1)
tab_criminal.rowconfigure(2, weight=1)

# Info + refresh row
cinfo = ttk.Frame(tab_criminal)
cinfo.grid(row=0, column=0, sticky="ew", pady=(0, 10))

ttk.Label(cinfo, text="Plates on watch list:").pack(side="left", padx=(0, 6))
ttk.Label(cinfo, textvariable=criminal_count_var,
          font=("Helvetica", 11, "bold"), foreground="#7c3aed").pack(side="left", padx=(0, 20))

ttk.Button(cinfo, text="🔄  Refresh from web", style="Neutral.TButton",
           command=refresh_criminal_list).pack(side="left", padx=(0, 6))
ttk.Button(cinfo, text="ℹ  How to update online list", style="Neutral.TButton",
           command=push_criminal_list).pack(side="left")

# Add plate row
addrow = ttk.Frame(tab_criminal)
addrow.grid(row=1, column=0, sticky="ew", pady=(0, 10))

ttk.Label(addrow, text="Add plate:").pack(side="left", padx=(0, 6))
ttk.Entry(addrow, textvariable=new_plate_var, width=16).pack(side="left", padx=(0, 6))
ttk.Button(addrow, text="➕  Add", style="Warning.TButton",
           command=add_criminal_plate).pack(side="left", padx=(0, 6))
ttk.Button(addrow, text="🗑  Remove selected", style="Danger.TButton",
           command=remove_criminal_plate).pack(side="left")

# Criminal plates table
ctbl_frame = ttk.Frame(tab_criminal)
ctbl_frame.grid(row=2, column=0, sticky="nsew")

criminal_tree = ttk.Treeview(ctbl_frame, columns=("Plate Number",), show="headings",
                               selectmode="browse")
criminal_tree.heading("Plate Number", text="Plate Number")
criminal_tree.column("Plate Number", width=200, anchor="center")
criminal_tree.tag_configure("criminal", foreground="#7c3aed", font=("Helvetica", 10, "bold"))

cscroll = ttk.Scrollbar(ctbl_frame, orient="vertical", command=criminal_tree.yview)
criminal_tree.configure(yscrollcommand=cscroll.set)
criminal_tree.pack(side="left", fill="both", expand=True)
cscroll.pack(side="right", fill="y")

# ─── Cleanup on close ─────────────────────────────────────────────────────────
def on_close():
    global _camera_thread_running
    _camera_thread_running = False
    stop_camera()
    root.destroy()

root.protocol("WM_DELETE_WINDOW", on_close)

# ─── Status bar ───────────────────────────────────────────────────────────────
status_bar = ttk.Label(root, text="Ready — press 'Detect Once' or start live detection.",
                        anchor="w", relief="flat", padding=(8, 4),
                        background="#1a1a2e", foreground="#9ca3af", font=("Helvetica", 9))
status_bar.pack(fill="x", side="bottom")

# ─── Startup ──────────────────────────────────────────────────────────────────
# Kick off the first criminal list refresh (runs every 60s after that)
root.after(500, refresh_criminal_list)

root.mainloop()
