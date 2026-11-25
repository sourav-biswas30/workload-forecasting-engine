"""Split a day's workload between inspectors.

A task is a row with: task_id, effort (how heavy it is), urgency (higher = more urgent).
Every method returns a pandas Series: index = task_id, value = inspector number (0..n-1).
"""
import math
import numpy as np
import pandas as pd
from ortools.sat.python import cp_model


def inspectors_needed(total_effort, capacity_per_inspector, buffer=0.10):
    """How many inspectors cover the expected effort, with a safety buffer."""
    return max(1, math.ceil(round(total_effort * (1 + buffer) / capacity_per_inspector, 6)))


def solve_round_robin(tasks, n_workers):
    """Hand out tasks one by one like dealing cards."""
    return pd.Series(np.arange(len(tasks)) % n_workers, index=tasks["task_id"].values)


def solve_greedy(tasks, n_workers):
    """Most urgent first; each goes to whoever has the lightest load so far."""
    load = np.zeros(n_workers)
    out = {}
    for _, t in tasks.sort_values("urgency", ascending=False).iterrows():
        w = int(load.argmin())
        out[t["task_id"]] = w
        load[w] += t["effort"]
    return pd.Series(out)


def solve_optimal(tasks, n_workers, time_limit=10, scale=100):
    """Minimise the heaviest inspector's load (most even split). Uses OR-Tools CP-SAT."""
    eff = (tasks["effort"].values * scale).round().astype(int)
    n = len(tasks)
    m = cp_model.CpModel()
    x = [[m.NewBoolVar(f"x{i}_{w}") for w in range(n_workers)] for i in range(n)]
    for i in range(n):
        m.AddExactlyOne(x[i])
    top = m.NewIntVar(0, int(eff.sum()), "top")
    for w in range(n_workers):
        m.Add(sum(int(eff[i]) * x[i][w] for i in range(n)) <= top)
    m.Minimize(top)
    s = cp_model.CpSolver()
    s.parameters.max_time_in_seconds = time_limit
    s.parameters.num_workers = 4
    status = s.Solve(m)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return solve_greedy(tasks, n_workers)  # safety net
    return pd.Series([next(w for w in range(n_workers) if s.Value(x[i][w])) for i in range(n)],
                     index=tasks["task_id"].values)


def kpis(tasks, assignment, n_workers):
    """Numbers to compare methods: busiest load, evenness, and how fast urgent tasks start."""
    t = tasks.set_index("task_id").loc[assignment.index].copy()
    t["worker"] = assignment
    loads = t.groupby("worker")["effort"].sum().reindex(range(n_workers), fill_value=0.0)
    # position in each worker's queue (most urgent first) -> waiting effort before the task starts
    t = t.sort_values("urgency", ascending=False)
    t["wait"] = t.groupby("worker")["effort"].cumsum() - t["effort"]
    top = t["urgency"].quantile(0.8)
    return {"max_load": round(loads.max(), 2),
            "load_gap": round(loads.max() - loads.min(), 2),
            "avg_wait_urgent": round(t.loc[t["urgency"] >= top, "wait"].mean(), 2)}