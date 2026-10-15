# Price Alert Tool

A small, dependency-free command-line tool that evaluates price level and moving-average-crossing alerts. It accepts an out-of-order CSV price file and a JSON rule list, then prints only the alerts that fired.

## Run

Python 3.10+ is the only requirement:

```sh
python alerts.py sample/prices.csv sample/rules.json
```

## Test

```sh
python -m unittest discover -s tests -v
```

The static browser companion lives in `web/`; open it through a local static server (for example `python -m http.server -d web`) when needed.

## How I used the assistant (prompts in brief)

TODO (author fills in)

## What the assistant got wrong, and what I changed and why

TODO (author fills in)
