# Star Academy Election Watch

Live dashboard of every 2026 to 2028 race in states where Star Academy (NOLA Education) operates.

Published dashboard: https://claude.ai/artifact/N6BsXbTRiboxX8JBmjHKEw

- `research/group_*.json`: raw research by state group (sources included)
- `merge.py`: flattens research into `races.json` (`python3 merge.py <dir>`)
- `races.json`, `footprint.json`: the datasets the dashboard reads
- `index.html`: dashboard page source

To update results: edit `status`, `winner`, `result_note` in `research/*.json`, rerun `merge.py`, then upload the new `races.json` to the dashboard.
