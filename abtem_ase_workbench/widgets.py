"""Tk GUI helper widgets used by the Workbench.

Tk is only imported when a function/class is actually called, so this module
can be imported by non-GUI code paths without pulling tkinter in.
"""
import ase.gui.ui as ui


class Panel:
    """Packs ASE ``ui`` widgets into any Tk frame (mirrors ui.Window.add).

    Lets the GUI reuse the same ``ui`` widget objects (so ``.value`` and the
    sync/run/benchmark code are untouched) while placing them inside custom
    scrollable tab frames instead of one long column.
    """

    def __init__(self, frame):
        self.frame = frame

    def add(self, stuff, anchor="w"):
        if isinstance(stuff, str):
            stuff = ui.Label(stuff)
        elif isinstance(stuff, list):
            stuff = ui.Row(stuff)
        stuff.pack(self.frame, anchor=anchor)
        return stuff


def make_scrollable_tab(notebook, title, scrollers_sink):
    """Add a vertically-scrollable tab to a ttk.Notebook.

    Returns ``(Panel(inner), outer_frame)``. The ``(canvas, inner)`` pair is
    appended to ``scrollers_sink`` so the caller can wheel-bind every tab in
    one pass after all tabs are built.
    """
    import tkinter as tk
    outer = tk.Frame(notebook)
    notebook.add(outer, text=title)

    canvas = tk.Canvas(outer, borderwidth=0, highlightthickness=0)
    vbar = tk.Scrollbar(outer, orient="vertical", command=canvas.yview)
    canvas.configure(yscrollcommand=vbar.set)
    vbar.pack(side="right", fill="y")
    canvas.pack(side="left", fill="both", expand=True)

    inner = tk.Frame(canvas)
    window_id = canvas.create_window((0, 0), window=inner, anchor="nw")

    def _on_inner_configure(event, c=canvas):
        c.configure(scrollregion=c.bbox("all"))
    inner.bind("<Configure>", _on_inner_configure)

    def _on_canvas_configure(event, c=canvas, wid=window_id):
        c.itemconfigure(wid, width=event.width)
    canvas.bind("<Configure>", _on_canvas_configure)

    scrollers_sink.append((canvas, inner))
    return Panel(inner), outer


def _wheel_event(event, canvas):
    """Normalize wheel/trackpad events across platforms into canvas scroll."""
    num = getattr(event, "num", None)
    if num == 4:
        canvas.yview_scroll(-3, "units")
    elif num == 5:
        canvas.yview_scroll(3, "units")
    else:
        delta = getattr(event, "delta", 0)
        canvas.yview_scroll(-3 if delta > 0 else 3, "units")
    return "break"


def bind_wheel_recursive(widget, canvas):
    """Bind wheel/trackpad scroll on a widget and all its descendants."""
    try:
        widget.bind("<MouseWheel>", lambda e, c=canvas: _wheel_event(e, c))
        widget.bind("<Button-4>", lambda e, c=canvas: _wheel_event(e, c))
        widget.bind("<Button-5>", lambda e, c=canvas: _wheel_event(e, c))
    except Exception:
        pass
    try:
        children = widget.winfo_children()
    except Exception:
        children = []
    for child in children:
        bind_wheel_recursive(child, canvas)


__all__ = ["Panel", "make_scrollable_tab", "bind_wheel_recursive"]
