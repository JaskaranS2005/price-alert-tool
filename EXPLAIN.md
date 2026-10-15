# Six-minute walkthrough

The CLI reads prices and rules, validates both, groups each instrument's rows, sorts them by date, then evaluates every valid rule. Warnings go to standard error so standard output remains machine-readable.

A level-below rule at 1500 fires only when yesterday was at or above 1500 and today is strictly below it. For a moving-average rule, the tool keeps a running sum rather than adding every window again: add today's close, subtract the one that just left the window, then divide by the window length. This makes each SMA update constant time.

`Decimal` is used because financial threshold equality must be exact: binary floating point can make apparently equal decimal values compare differently.

Likely questions:

1. Why can the first row not alert? It has no preceding trading row to cross from.
2. What happens at weekends? They do not exist in the series; rows are trading observations.
3. Why `short < long`? Otherwise it is not a short-versus-long crossover.
4. What about malformed data? Bad rows are skipped with line-numbered warnings; whole-file format errors fail cleanly.
5. How did you verify it? Tests cover crossings, equality, ordering, duplicate rows, malformed input, and the CLI end-to-end.
