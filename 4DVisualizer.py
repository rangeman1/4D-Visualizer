#!/usr/bin/env python3.14
import os
import sys


def _parent_process_name():
    """Best-effort name (lower-case) of the parent process, or "" on failure."""
    try:
        import ctypes
        from ctypes import wintypes
        kernel32 = ctypes.windll.kernel32
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, os.getppid())
        if not handle:
            return ""
        try:
            size = wintypes.DWORD(260)
            buf = ctypes.create_unicode_buffer(size.value)
            if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
                return os.path.basename(buf.value).lower()
        finally:
            kernel32.CloseHandle(handle)
    except Exception:
        pass
    return ""


def _relaunch_windowed():
    """When double-clicked on Windows, a .py file is opened through the Python
    launcher (py.exe) or explorer.exe and shows a console/terminal window.
    Detect that case and re-launch the same script with pythonw.exe (no console)
    instead, then exit this process. Running from a terminal is left untouched."""
    if os.name != "nt" or getattr(sys, "frozen", False):
        return
    if os.environ.get("TETRA_WINDOWED") == "1":
        return
    exe = sys.executable or ""
    if not exe.lower().endswith("python.exe"):
        return
    # Double-clicking a .py goes through explorer.exe -> py.exe -> python.exe,
    # so the parent is either explorer.exe or the py launcher.
    if _parent_process_name() not in ("explorer.exe", "py.exe"):
        return
    pythonw = os.path.join(os.path.dirname(exe), "pythonw.exe")
    if not os.path.exists(pythonw):
        return
    import subprocess
    env = dict(os.environ, TETRA_WINDOWED="1")
    subprocess.Popen([pythonw, os.path.abspath(__file__)], env=env, close_fds=True)
    sys.exit(0)


_relaunch_windowed()

import numpy as np
import matplotlib
matplotlib.use("TkAgg")   # interactive backend (zoom, pan, rotate)
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
from mpl_toolkits.mplot3d import proj3d
from matplotlib.patches import Rectangle
import csv
import tkinter as tk
from tkinter import filedialog, messagebox, colorchooser
import tkinter.font as tkfont

# --- Vertices of a regular tetrahedron ---
V = np.array([
    [1, 0, 0],  # v1
    [0, 1, 0],  # v2
    [0, 0, 1],  # v3
    [0, 0, 0]   # v4
])

FACES = [
    [V[0], V[1], V[2]],
    [V[0], V[1], V[3]],
    [V[0], V[2], V[3]],
    [V[1], V[2], V[3]],
]

FONT = ("Segoe UI", 11)
FONT_BOLD = ("Segoe UI", 11, "bold")

# Gap between a point and its label (data units), so the text does not sit on
# top of the marker.
LABEL_OFFSET = 0.007

# How close (in screen pixels) a click must be to a marker to select it.
PICK_RADIUS_PX = 12

# If the mouse moves more than this between press and release it counts as a
# drag (rotate/pan/zoom), not a click that selects a point.
CLICK_MOVE_TOL_PX = 6

# Scene magnification (box zoom) limits for the mouse wheel.
# Zooming magnifies the whole tetrahedron together with the points, so the
# points are never cropped away by the axis ranges; they only leave the frame
# when the magnified scene grows past the plot area.
MIN_ZOOM = 0.2
MAX_ZOOM = 8.0

SAMPLE_POINTS = [
    (0.2, 0.3, 0.4, 0.1),
    (0.5, 0.5, 0.5, -0.2),
    (1.2, -0.1, 0.0, -0.1),
    (0.0, 0.0, 1.0, 0.0),
    (0.25, 0.25, 0.25, 0.25),
]


def load_csv_4d(path, skip_header=True, skip_first_col=False):
    """
    Reads a CSV file with 4D points.
    - automatically detects the separator
    - converts commas to dots
    - if skip_first_col is True, the first column is always treated as a
      label and excluded from the numeric data
    - otherwise the first column is treated as a label only when it is textual
    - returns 4D points + point labels (or None)
    """
    points = []
    labels = []

    with open(path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    if skip_header and lines:
        lines = lines[1:]

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # separator
        if ";" in line:
            parts = line.split(";")
        else:
            parts = line.split(",")

        # label detection
        first = parts[0].strip()
        if skip_first_col:
            label = first if first else None  # first column skipped as a label
            parts = parts[1:]
        else:
            try:
                float(first.replace(",", "."))
                label = None  # first column is a number
            except ValueError:
                label = first  # first column is a label
                parts = parts[1:]  # skip the label

        numeric = []
        for cell in parts:
            cell = cell.strip().replace(",", ".")
            try:
                numeric.append(float(cell))
            except ValueError:
                continue

        if len(numeric) < 4:
            raise ValueError(
                f"Found only {len(numeric)} numeric columns — 4 are required.\n"
                f"Row: {line}"
            )

        points.append(tuple(numeric[:4]))
        labels.append(label)

    return points, labels


def barycentric_to_cartesian(points4d):
    cartesian = []
    inside = []

    for (a, b, c, d) in points4d:
        P = a*V[0] + b*V[1] + c*V[2] + d*V[3]
        cartesian.append(P)
        inside.append((abs(a+b+c+d - 1) < 1e-9) and a >= 0 and b >= 0 and c >= 0 and d >= 0)

    return np.array(cartesian), np.array(inside)


class TetraedrApp:
    def __init__(self, root):
        self.root = root
        root.title("Tetrahedron GUI — Barycentric projection of 4D points")
        root.geometry("1200x800")
        root.minsize(1000, 640)

        # --- Compact single-row top toolbar ---
        top = tk.Frame(root)
        top.pack(side="top", fill="x", padx=8, pady=6)

        tk.Label(top, text="CSV file:", font=FONT).pack(side="left")

        self.path_var = tk.StringVar()
        tk.Entry(top, textvariable=self.path_var, font=FONT).pack(
            side="left", fill="x", expand=True, padx=6
        )
        tk.Button(top, text="Browse...", command=self.browse, font=FONT_BOLD, padx=8).pack(side="left")

        self.skip_header_var = tk.BooleanVar(value=True)
        tk.Checkbutton(top, text="Skip header", variable=self.skip_header_var, font=FONT).pack(
            side="left", padx=(8, 0)
        )

        self.skip_first_col_var = tk.BooleanVar(value=False)
        tk.Checkbutton(top, text="Skip first column", variable=self.skip_first_col_var, font=FONT).pack(
            side="left", padx=(8, 0)
        )

        self.hide_axes_var = tk.BooleanVar(value=False)
        tk.Checkbutton(top, text="Hide axes", variable=self.hide_axes_var, font=FONT,
                       command=self.toggle_axes).pack(side="left", padx=(8, 0))

        self.hide_tetra_var = tk.BooleanVar(value=False)
        tk.Checkbutton(top, text="Hide tetrahedron", variable=self.hide_tetra_var, font=FONT,
                       command=self.toggle_tetra).pack(side="left", padx=(8, 0))

        self.hide_labels_var = tk.BooleanVar(value=False)
        tk.Checkbutton(top, text="Hide labels", variable=self.hide_labels_var, font=FONT,
                       command=self.toggle_labels).pack(side="left", padx=(8, 0))

        tk.Button(top, text="Load & Plot", command=self.load_and_plot, font=FONT_BOLD, padx=10).pack(
            side="left", padx=(8, 0)
        )
        tk.Button(top, text="Sample", command=self.use_sample, font=FONT_BOLD, padx=10).pack(
            side="left", padx=(6, 0)
        )
        tk.Button(top, text="Clear", command=self.clear_plot, font=FONT_BOLD, padx=10).pack(
            side="left", padx=(6, 0)
        )

        # --- Controls row: label font + view rotation + label style ---
        ctrl = tk.Frame(root)
        ctrl.pack(side="top", fill="x", padx=8, pady=(0, 4))

        tk.Label(ctrl, text="Font size:", font=FONT).pack(side="left")
        self.label_fontsize_var = tk.IntVar(value=9)
        tk.Scale(ctrl, from_=4, to=32, orient="horizontal", length=120,
                 variable=self.label_fontsize_var, command=self.on_label_font_change).pack(
            side="left", padx=(4, 8)
        )

        tk.Label(ctrl, text="Label gap:", font=FONT).pack(side="left")
        self.label_offset_var = tk.DoubleVar(value=LABEL_OFFSET)
        tk.Scale(ctrl, from_=0.0, to=0.1, resolution=0.001, orient="horizontal", length=110,
                 variable=self.label_offset_var, command=self.on_label_offset_change).pack(
            side="left", padx=(4, 8)
        )

        tk.Label(ctrl, text="Vertical:", font=FONT).pack(side="left")
        self.elev_var = tk.IntVar(value=30)
        tk.Scale(ctrl, from_=-90, to=90, orient="horizontal", length=110,
                 variable=self.elev_var, command=self.on_view_change).pack(side="left", padx=(4, 8))

        tk.Label(ctrl, text="Horizontal:", font=FONT).pack(side="left")
        self.azim_var = tk.IntVar(value=-60)
        tk.Scale(ctrl, from_=-180, to=180, orient="horizontal", length=110,
                 variable=self.azim_var, command=self.on_view_change).pack(side="left", padx=(4, 8))

        tk.Label(ctrl, text="Font:", font=FONT).pack(side="left")
        families = sorted(set(tkfont.families()))
        default_family = "Segoe UI" if "Segoe UI" in families else (
            families[0] if families else "TkDefaultFont")
        self.label_font_var = tk.StringVar(value=default_family)
        font_menu = tk.OptionMenu(ctrl, self.label_font_var, *families,
                                  command=self.on_label_font_change)
        font_menu.config(width=14)
        font_menu.pack(side="left", padx=(4, 8))

        self.label_color = "blue"
        tk.Label(ctrl, text="Text color:", font=FONT).pack(side="left")
        self.color_btn = tk.Button(ctrl, text="Choose...", font=FONT_BOLD, padx=8,
                                   bg=self.label_color, command=self.choose_label_color)
        self.color_btn.pack(side="left", padx=4)

        tk.Label(ctrl, text="Points:", font=FONT).pack(side="left", padx=(8, 0))
        self.recolor_btn = tk.Button(ctrl, text="Recolor selected...", font=FONT_BOLD,
                                     padx=8, command=self.recolor_selected)
        self.recolor_btn.pack(side="left", padx=4)
        self.sel_count_var = tk.StringVar(value="0 selected")
        tk.Label(ctrl, textvariable=self.sel_count_var, font=FONT).pack(side="left", padx=(2, 0))

        # Status text kept for internal messages (not displayed).
        self.status_var = tk.StringVar()

        # --- Embedded matplotlib figure ---
        self.fig = Figure(figsize=(9, 7))
        self.ax = self.fig.add_subplot(111, projection="3d")
        self.zoom = 1.0
        # Point-selection / recolor state (see render / on_pick).
        self.points3d = None
        self.inside = None
        self.points_scatter = None
        self.point_colors = []
        self.selected = set()
        self._press_px = None
        self.canvas = FigureCanvasTkAgg(self.fig, master=root)

        toolbar_frame = tk.Frame(root)
        toolbar_frame.pack(side="bottom", fill="x")
        self.toolbar = NavigationToolbar2Tk(self.canvas, toolbar_frame)
        self.toolbar.update()

        self.canvas.get_tk_widget().pack(side="top", fill="both", expand=True)
        self.canvas.mpl_connect("scroll_event", self.on_scroll)
        self.canvas.mpl_connect("button_press_event", self.on_press)
        self.canvas.mpl_connect("button_release_event", self.on_release)

        self.render()

    # ------------------------------------------------------------------
    def browse(self):
        path = filedialog.askopenfilename(
            title="Select CSV file",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if path:
            self.path_var.set(path)

    def load_and_plot(self):
        path = self.path_var.get().strip()
        if not path:
            messagebox.showerror("Error", "No input file selected.")
            return
        try:
            points4d, labels = load_csv_4d(
                path,
                skip_header=self.skip_header_var.get(),
                skip_first_col=self.skip_first_col_var.get(),
            )
        except Exception as e:
            messagebox.showerror("Error", f"Could not load the file:\n{e}")
            self.status_var.set("Load failed.")
            return

        if not points4d:
            messagebox.showerror("Error", "The file contains no data rows.")
            self.status_var.set("No data rows.")
            return

        self.render(points4d, labels)
        self.status_var.set(f"Loaded {len(points4d)} points from: {path}")

    def use_sample(self):
        self.render(SAMPLE_POINTS, [None] * len(SAMPLE_POINTS))
        self.status_var.set("Sample data loaded.")

    def clear_plot(self):
        self.render()
        self.status_var.set("Plot cleared.")

    def toggle_axes(self):
        if self.hide_axes_var.get():
            self.ax.set_axis_off()
        else:
            self.ax.set_axis_on()
        self.canvas.draw_idle()

    def toggle_tetra(self):
        visible = not self.hide_tetra_var.get()
        self.poly.set_visible(visible)
        self.vertices.set_visible(visible)
        self.canvas.draw_idle()

    def toggle_labels(self):
        visible = not self.hide_labels_var.get()
        for txt in getattr(self, "label_texts", []):
            txt.set_visible(visible)
        self.canvas.draw_idle()

    def on_label_font_change(self, value=None):
        self._apply_label_style()

    def on_label_offset_change(self, value=None):
        # Move the labels relative to their anchor points, without redrawing
        # the whole plot.
        offset = self.label_offset_var.get()
        anchors = getattr(self, "label_anchor", [])
        for (x, y, z), txt in zip(anchors, getattr(self, "label_texts", [])):
            txt.set_position((x + offset, y + offset))
            txt.set_3d_properties(z + offset, 'z')
        canvas = getattr(self, "canvas", None)
        if canvas is not None:
            canvas.draw_idle()

    def _apply_label_style(self):
        size = int(float(self.label_fontsize_var.get()))
        font_var = getattr(self, "label_font_var", None)
        family = font_var.get() if font_var is not None else None
        color = getattr(self, "label_color", "blue")
        for txt in getattr(self, "label_texts", []):
            txt.set_fontsize(size)
            if family:
                txt.set_fontfamily(family)
            txt.set_color(color)
        canvas = getattr(self, "canvas", None)
        if canvas is not None:
            canvas.draw_idle()

    def choose_label_color(self):
        chosen = colorchooser.askcolor(color=self.label_color, title="Select label color")
        if chosen and chosen[1]:
            self.label_color = chosen[1]
            self.color_btn.configure(bg=self.label_color)
            self._apply_label_style()

    def on_view_change(self, value=None):
        ax = getattr(self, "ax", None)
        if ax is None:
            return
        ax.view_init(elev=self.elev_var.get(), azim=self.azim_var.get())
        canvas = getattr(self, "canvas", None)
        if canvas is not None:
            canvas.draw_idle()

    # ------------------------------------------------------------------
    def render(self, points4d=None, labels=None):
        self.ax.clear()
        self.label_texts = []
        self.label_anchor = []

        self.poly = Poly3DCollection(FACES, alpha=0.15, facecolor='cyan')
        self.poly.set_edgecolor('black')
        self.poly.set_clip_on(False)
        self.ax.add_collection3d(self.poly)

        self.vertices = self.ax.scatter(V[:, 0], V[:, 1], V[:, 2], color='black', s=60, clip_on=False)

        tetra_visible = not self.hide_tetra_var.get()
        self.poly.set_visible(tetra_visible)
        self.vertices.set_visible(tetra_visible)

        self.points_scatter = None
        if points4d:
            points3d, inside = barycentric_to_cartesian(points4d)
            self.points3d = points3d
            self.inside = inside
            n = len(points4d)
            # Fresh data: drop any selection/overrides from the previous file.
            self.point_colors = [None] * n
            self.selected = set()

            facecolors = [self.point_colors[i] or ('green' if inside[i] else 'red')
                          for i in range(n)]
            edgecolors = ['blue' if i in self.selected else 'none' for i in range(n)]
            linewidths = [2 if i in self.selected else 0 for i in range(n)]
            self.points_scatter = self.ax.scatter(
                points3d[:, 0], points3d[:, 1], points3d[:, 2],
                s=50, facecolors=facecolors, edgecolors=edgecolors,
                linewidths=linewidths, clip_on=False)
            self._update_selection_label()

            offset = self.label_offset_var.get()
            for (x, y, z), label in zip(points3d, labels or [None] * len(points4d)):
                if label is not None:
                    txt = self.ax.text(x + offset, y + offset, z + offset,
                                       label, fontsize=self.label_fontsize_var.get(),
                                       fontfamily=self.label_font_var.get(),
                                       color=self.label_color, clip_on=False,
                                       visible=not self.hide_labels_var.get())
                    self.label_texts.append(txt)
                    self.label_anchor.append((x, y, z))

        self.zoom = 1.0
        self._apply_zoom()

        self.ax.set_xlabel("X")
        self.ax.set_ylabel("Y")
        self.ax.set_zlabel("Z")

        if self.hide_axes_var.get():
            self.ax.set_axis_off()
        else:
            self.ax.set_axis_on()

        self.ax.view_init(elev=self.elev_var.get(), azim=self.azim_var.get())

        self.canvas.draw_idle()

    # ------------------------------------------------------------------
    def on_scroll(self, event):
        if event.button == 'up':
            factor = 1.1
        elif event.button == 'down':
            factor = 1.0 / 1.1
        else:
            return

        self.zoom = min(MAX_ZOOM, max(MIN_ZOOM, self.zoom * factor))
        self._apply_zoom()
        self.canvas.draw_idle()

    def _apply_zoom(self):
        # Magnify the whole scene inside the axes without touching the axis
        # ranges, so data points are never culled by the limits.
        aspect = self.ax.get_box_aspect()
        if aspect is None:
            ranges = [hi - lo for lo, hi in
                      (self.ax.get_xlim(), self.ax.get_ylim(), self.ax.get_zlim())]
            largest = max(ranges) or 1.0
            aspect = tuple(r / largest for r in ranges)
        self.ax.set_box_aspect(aspect, zoom=self.zoom)

    # ------------------------------------------------------------------
    def _is_multi_modifier(self, event):
        if getattr(event, "key", None) in ("shift", "control"):
            return True
        gui = getattr(event, "guiEvent", None)
        state = getattr(gui, "state", 0) if gui is not None else 0
        # 0x0001 = Shift, 0x0004 = Control (Tk/X11 modifier bits).
        return bool(state & 0x0001) or bool(state & 0x0004)

    def on_press(self, event):
        # Record where a left-click began so a click (select) can be told apart
        # from a drag (rotate/pan/zoom).
        if event.button == 1:
            self._press_px = (event.x, event.y)

    def on_release(self, event):
        if event.button != 1:
            return
        start = getattr(self, "_press_px", None)
        self._press_px = None
        if start is None:
            return
        # Only a near-stationary click selects; dragging rotates/pans instead.
        if (abs(event.x - start[0]) > CLICK_MOVE_TOL_PX
                or abs(event.y - start[1]) > CLICK_MOVE_TOL_PX):
            return
        self._select_at(event)

    def _pick_radius_px(self):
        # Marker radius in pixels (scatter s is in points^2) plus a tolerance
        # margin, so even small markers are easy to hit.
        sizes = self.points_scatter.get_sizes()
        marker_r = np.sqrt(sizes.max()) / 2.0 if sizes.size else 0.0
        marker_r *= self.fig.dpi / 72.0
        return max(PICK_RADIUS_PX, marker_r + PICK_RADIUS_PX)

    def _select_at(self, event):
        # Selection is decided purely by screen distance to the nearest marker.
        # The click may land outside the 2D axes rectangle (points are drawn
        # with clip_on=False), so event.inaxes is intentionally not required.
        if self.points_scatter is None:
            return

        proj = self.ax.get_proj()
        xs, ys, _ = proj3d.proj_transform(
            self.points3d[:, 0], self.points3d[:, 1], self.points3d[:, 2], proj)
        display = self.ax.transData.transform(np.column_stack([xs, ys]))
        dist = np.hypot(display[:, 0] - event.x, display[:, 1] - event.y)
        index = int(np.argmin(dist))

        if dist[index] > self._pick_radius_px():
            if not self._is_multi_modifier(event):
                self.selected = set()
                self._refresh_point_styles()
            return

        if self._is_multi_modifier(event):
            if index in self.selected:
                self.selected.discard(index)
            else:
                self.selected.add(index)
        else:
            self.selected = {index}
        self._refresh_point_styles()

    def _update_selection_label(self):
        var = getattr(self, "sel_count_var", None)
        if var is not None:
            var.set(f"{len(self.selected)} selected")

    def _refresh_point_styles(self):
        if self.points_scatter is None:
            return
        n = len(self.point_colors)
        facecolors = [self.point_colors[i] or ('green' if self.inside[i] else 'red')
                      for i in range(n)]
        edgecolors = ['blue' if i in self.selected else 'none' for i in range(n)]
        linewidths = [2 if i in self.selected else 0 for i in range(n)]
        self.points_scatter.set_facecolor(facecolors)
        self.points_scatter.set_edgecolor(edgecolors)
        self.points_scatter.set_linewidth(linewidths)
        self._update_selection_label()
        self.canvas.draw_idle()

    def recolor_selected(self):
        if not self.selected:
            messagebox.showinfo(
                "Recolor points",
                "Click a point to select it first (hold Ctrl or Shift to pick several).")
            return
        chosen = colorchooser.askcolor(title="Select point color")
        if not chosen or not chosen[1]:
            return
        for i in self.selected:
            self.point_colors[i] = chosen[1]
        # Drop the selection after the color is applied so the next group of
        # points can be picked cleanly: this lets the user recolor point groups
        # over and over instead of only the first time.
        self.selected = set()
        self._refresh_point_styles()


def main():
    root = tk.Tk()
    TetraedrApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
