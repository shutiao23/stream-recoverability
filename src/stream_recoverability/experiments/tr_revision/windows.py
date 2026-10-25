"""Explicit native-target views for reusing the annual H30 fitting engine.

Native H7 data retain honest h7 names. Only the internal fitting view aliases
them to the legacy engine's h30 names; no H30 values are relabeled as H7.
"""
from __future__ import annotations
import pandas as pd


def primary_view(frame: pd.DataFrame,target="h7") -> pd.DataFrame:
    if target not in ["h7","h30"]:raise ValueError("Supported source statistics are H7 and H30")
    if target=="h30":return frame.copy()
    if not frame.primary_target.eq(target).all() or not frame.primary_window_days.eq(7).all():
        raise ValueError("Native source window metadata does not match the requested statistic")
    required=["eval_truth_h7","h7__policy","train_h7_mean","train_h7_sd","train_h7_q90"]
    if set(required)-set(frame):raise ValueError("Incomplete native H7 schema")
    retained=[c for c in frame if "h30" not in c]
    out=frame[retained].rename(columns={c:c.replace("h7","h30") for c in retained})
    if out.columns.duplicated().any():raise ValueError("Ambiguous target aliases")
    return out


def native_view(frame: pd.DataFrame,target="h7") -> pd.DataFrame:
    if target=="h30":return frame.copy()
    if target!="h7":raise ValueError("Supported source statistics are H7 and H30")
    return frame.rename(columns={c:c.replace("h30","h7") for c in frame})
