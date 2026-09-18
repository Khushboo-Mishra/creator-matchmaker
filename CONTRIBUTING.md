# Contributing

Three people, three lanes, no shared files. The point of the layout is that two
people almost never touch the same module.

## Lanes

| Lane | Owns | Touches |
|---|---|---|
| Data | Getting real numbers out of the API into a fixed shape | `src/pull.py`, `src/arithmetic.py`, `src/config.py` |
| Model | The three judgement scores | `src/score_ai.py` |
| Inputs | What the pipeline reads | `config/rules.md`, `data/handles.txt` |

`src/build_scores.py` and `schemas/` are shared. Changes there get a heads-up before
the commit, because they are the seams everyone else builds against.

## Branches

One branch per change, named `lane/what-it-does`, for example `model/calibration-examples`.
Open a pull request even for small things. It is the cheapest way for three people to
see what changed without reading the whole file.

## Never commit

Real API keys, `.env`, pulled channel data, generated scores. All of it is in
`.gitignore` already. If a key is ever committed, rotate it, do not just remove it.

## Changing a schema

`schemas/*.json` describe files that pass between people. If a field has to change:

1. Say so before you push.
2. Update the schema and the code that writes the file in the same commit.
3. Anyone consuming the file updates their stub to match.

## Working against stubs

Nobody waits for anyone. Every consumer writes a fake version of their input:

- The model lane develops against one committed sample channel record, not the full pull.
- The pull lane runs against a short placeholder handles list, not the final one.
- Anything reading scores works from a hand-written scores file that satisfies the schema.

Real files replace stubs with no code change, because the shape is already agreed.
