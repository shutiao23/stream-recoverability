"""Panel layouts sized for the printed page.

The analysis figures are drawn wide, three or four panels in a row, which reads
well on a screen and in the Markdown reading copy. A journal column is 5.5
inches; a 3.9:1 figure scaled into it is an inch and a half tall and its tick
labels are unreadable.

Journal mode re-lays the same panels into a shape that fits, and draws them at
the size they will actually be printed so nothing is scaled down afterwards.
The panel order is unchanged, so a figure function keeps indexing ``axes[0]``,
``axes[1]``, ... and needs no other edit.
"""

from __future__ import annotations

import os
from collections.abc import Sequence

import matplotlib.pyplot as plt

#: Text width of the AGU single-column class, in inches (32.25 pc).
COLUMN_INCHES = 5.5

#: Height per panel row in journal mode, in inches.
ROW_INCHES = 2.45


def journal_mode() -> bool:
    return os.environ.get("WRR_JOURNAL_FIGURES") == "1"


def rc_overrides() -> dict:
    """Smaller type, because a journal panel is half the width of a wide one."""

    if not journal_mode():
        return {}
    return {
        "font.size": 7.0,
        "axes.labelsize": 7.0,
        "axes.titlesize": 7.6,
        "xtick.labelsize": 6.4,
        "ytick.labelsize": 6.4,
        "legend.fontsize": 6.2,
        "lines.linewidth": 1.5,
    }


def panel_grid(
    n_panels: int,
    wide_figsize: tuple[float, float],
    *,
    width_ratios: Sequence[float] | None = None,
    sharey: bool = False,
):
    """``plt.subplots(1, n)`` on screen; a stacked grid on the page.

    Returns ``(figure, axes)`` with ``axes`` in the same left-to-right order the
    caller wrote its panels in.
    """

    if not journal_mode():
        keywords = {"gridspec_kw": {"width_ratios": list(width_ratios)}} if width_ratios else {}
        return plt.subplots(1, n_panels, figsize=wide_figsize, sharey=sharey, **keywords)

    if n_panels == 1:
        figure, axis = plt.subplots(figsize=(COLUMN_INCHES, ROW_INCHES * 1.15))
        return figure, axis

    if n_panels == 2:
        figure, axes = plt.subplots(
            2, 1, figsize=(COLUMN_INCHES, ROW_INCHES * 2.0), sharey=False
        )
        return figure, axes

    if n_panels == 3:
        # Two on top, the third spanning underneath: the third panel is usually
        # the one with a colour bar or a long axis, and it needs the width.
        figure = plt.figure(figsize=(COLUMN_INCHES, ROW_INCHES * 2.05))
        grid = figure.add_gridspec(
            2, 2, height_ratios=[1.0, 1.05], width_ratios=list(width_ratios[:2]) if width_ratios else [1, 1]
        )
        axes = [
            figure.add_subplot(grid[0, 0]),
            figure.add_subplot(grid[0, 1]),
            figure.add_subplot(grid[1, :]),
        ]
        return figure, axes

    if n_panels == 4:
        figure, axes = plt.subplots(2, 2, figsize=(COLUMN_INCHES, ROW_INCHES * 2.0))
        return figure, axes.ravel()

    raise ValueError(f"no journal layout defined for {n_panels} panels")
