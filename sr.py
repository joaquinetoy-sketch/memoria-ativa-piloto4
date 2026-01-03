from dataclasses import dataclass
from datetime import datetime, timedelta

@dataclass
class ScheduleState:
    due_date: datetime
    interval_days: float
    ease: float
    reps: int
    lapses: int

def clamp(x, lo, hi):
    return max(lo, min(hi, x))

def update(state: ScheduleState, rating: str) -> ScheduleState:
    now = datetime.now()
    ease = state.ease
    interval = state.interval_days
    reps = state.reps
    lapses = state.lapses

    if rating == "again":
        lapses += 1
        reps = 0
        interval = 0.5  # 12h
        ease = clamp(ease - 0.2, 1.3, 2.8)
    elif rating == "hard":
        reps += 1
        interval = max(1.0, interval * 1.2)
        ease = clamp(ease - 0.05, 1.3, 2.8)
    elif rating == "good":
        reps += 1
        if interval < 1:
            interval = 1.0
        elif interval < 3:
            interval = 3.0
        else:
            interval = interval * ease
        ease = clamp(ease, 1.3, 2.8)
    elif rating == "easy":
        reps += 1
        if interval < 1:
            interval = 2.0
        elif interval < 3:
            interval = 4.0
        else:
            interval = interval * (ease + 0.15)
        ease = clamp(ease + 0.05, 1.3, 2.8)
    else:
        raise ValueError("rating must be one of: again, hard, good, easy")

    interval = clamp(interval, 0.5, 365.0)
    due = now + timedelta(days=float(interval))
    return ScheduleState(due_date=due, interval_days=float(interval), ease=float(ease), reps=int(reps), lapses=int(lapses))
