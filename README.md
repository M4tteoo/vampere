# vampere

GreenOps for SMEs — sprintd Basel 2026, case "Green AI & Data" (ALTYCA × Basel 2037).

## Setup

```bash
git clone --recurse-submodules https://github.com/M4tteoo/vampere.git
# already cloned without submodules?
git submodule update --init
```

## Structure

- `case.md` — case description
- `data/case/` — case data (git submodule, read-only): https://github.com/Fa-Bee/sprintd-basel-green-ai-data

Update the case data if the organisers push fixes:

```bash
git submodule update --remote data/case
```

Data: «Sample data ALTYCA, sprintd Basel 2026» (synthetic).
