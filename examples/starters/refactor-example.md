# Refactor Example

`scripts/report_summary.py` repeats the same date parsing block in three
functions. Extract one helper, preserve output exactly, and run the existing
summary tests before closing.
