"""Instrument presets: beam voltage + typical Cs / partial-coherence values.

Keys match the ComboBox values in gui.py; values are plain dicts the GUI
splashes into its ``voltage`` / ``cs`` / ``focal_spread`` / ``angular_spread``
fields when the user clicks "Apply Preset".
"""

# voltage in kV; Cs in Å; focal_spread in Å; angular_spread in rad.
INSTRUMENT_PRESETS = {
    "lv80":    dict(voltage=80.0,  cs=1200.0,  focal_spread=8.0, angular_spread=1.2e-3),
    "hr200":   dict(voltage=200.0, cs=0.001,   focal_spread=4.0, angular_spread=0.3e-3),
    "hr300":   dict(voltage=300.0, cs=0.001,   focal_spread=3.0, angular_spread=0.2e-3),
    "conv300": dict(voltage=300.0, cs=12000.0, focal_spread=8.0, angular_spread=0.5e-3),
}

PRESET_LABELS = [
    ("none",    "— choose a preset —"),
    ("lv80",    "Low-voltage TEM (80 kV)"),
    ("hr200",   "HRTEM 200 kV (Cs-corrected)"),
    ("hr300",   "HRTEM 300 kV (Cs-corrected)"),
    ("conv300", "Conventional 300 kV"),
]


def get_preset(key):
    """Return the preset dict for ``key`` or ``None`` if unknown / 'none'."""
    return INSTRUMENT_PRESETS.get(key)


__all__ = ["INSTRUMENT_PRESETS", "PRESET_LABELS", "get_preset"]
