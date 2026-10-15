# 4DVisualizer

An interactive visualizer for 4D points (barycentric coordinates) projected onto a
regular three-dimensional tetrahedron. A windowed Python application (Tkinter +
Matplotlib) that loads data from a CSV file, lets you rotate and zoom the scene,
hide elements, label points, and select and recolor chosen points.

## Requirements

- Python 3.14 (tested on 3.14.7)
- `numpy` (tested on 2.3.5)
- `matplotlib` (tested on 3.10.8)
- `tkinter` (included in the standard Python installation on Windows)

Install the missing packages:

```powershell
pip install numpy matplotlib
```

## Running

From a terminal:

```powershell
python 4DVisualizer.py
```

or double-click the `4DVisualizer.py` file. When launched by double-click (Windows),
the script automatically switches to `pythonw.exe` so that no console window appears.

## Input data format (CSV)

Each row describes one 4D point.

- Separator: comma `,` or semicolon `;` (detected automatically).
- Decimal commas are converted to dots (`0,25` → `0.25`).
- Four numeric columns are required (any extra columns are ignored).
- An optional first column with a (textual) label — see the "Skip header" and
  "Skip first column" options.

Example (with header and labels in the first column):

```csv
name,a,b,c,d
P1,0.2,0.3,0.4,0.1
P2,0.5,0.5,0.5,-0.2
P3,1.2,-0.1,0.0,-0.1
```

Example (numeric data only):

```csv
0.2,0.3,0.4,0.1
0.5,0.5,0.5,-0.2
1.2,-0.1,0.0,-0.1
```

## Interface

### Top bar

- **CSV file** + **Browse...** — choose the data file.
- **Skip header** — skip the first row (header).
- **Skip first column** — treat the first column as the point label.
- **Hide axes** — hide the X/Y/Z axes.
- **Hide tetrahedron** — hide the tetrahedron and its vertices.
- **Hide labels** — hide the point labels.
- **Load & Plot** — load and plot the data from the file.
- **Sample** — load sample data.
- **Clear** — clear the plot.

### Controls row

- **Font size** — font size of the labels.
- **Label gap** — distance between a label and its point (X/Y/Z offset in data units).
- **Vertical** — vertical viewing angle (elev).
- **Horizontal** — horizontal viewing angle (azim).
- **Font** — font family of the labels.
- **Text color → Choose...** — label color.
- **Points → Recolor selected...** — change the color of the selected points;
  the number of selected points is shown next to it.

## Mouse controls

- **Click a point** — select the point.
- **Ctrl / Shift + click** — add/remove a point from the selection (multi-select).
- **Click on empty space** — clear the selection.
- **Mouse wheel** — zoom the scene in/out.
- **Drag** — rotate/pan/zoom the view (dragging does not select points).
- **Bottom toolbar** — standard Matplotlib tools (including saving the image).

## Point colors

- **Green** — point inside the tetrahedron.
- **Red** — point outside the tetrahedron.
- **Blue outline** — the currently selected point.
- A color chosen via "Recolor selected..." overrides a point's color. After a color
  change the selection is cleared, so you can recolor further groups of points.

## How it works

The 4D points `(a, b, c, d)` are interpreted as barycentric coordinates and projected
onto a tetrahedron with vertices:

```
v1 = (1, 0, 0)
v2 = (0, 1, 0)
v3 = (0, 0, 1)
v4 = (0, 0, 0)
```

Position in 3D: `P = a*v1 + b*v2 + c*v3 + d*v4`.

A point is considered **inside** when `a, b, c, d >= 0` and `a+b+c+d ≈ 1`.

## Notes

- When zooming, points may extend beyond the axes area — they are still drawn
  (without clipping) and can still be selected.
- The script uses the Matplotlib `TkAgg` backend.
