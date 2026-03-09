Solitaire Chess Solver (v5)
============================

This folder contains a Solitaire Chess solver and tools for working with three puzzle types from puzzle-chess.com:
Chess Ranger, Chess Melee, and Solo Chess. The core logic is implemented in `solver.py`, with an optional Pygame
GUI in `gui.py` and a crawler in `fetch_puzzle_chess.py` for collecting Solo Chess boards into FEN files.

Requirements
------------

- Python 3.8+ (tested with 3.9)
- `pygame>=2.1.0` for the GUI
- Optional: `playwright` (and a browser engine such as Chromium) if you want to crawl puzzles from puzzle-chess.com

You can install the basic dependency with:

```bash
pip install pygame
```

For crawling support (optional):

```bash
pip install playwright
python -m playwright install chromium  # or: firefox, webkit
```

Files
-----

- `solver.py` – core solver:
  - Implements DFS and A* search with an admissible heuristic.
  - Supports three modes via separate solver classes:
    - `RangerSolver` (Chess Ranger)
    - `MeleeSolver` (Chess Melee)
    - `SoloSolver` (Solo Chess)
  - Includes benchmark utilities that run DFS and A* over the `.fen` datasets and report time, memory, nodes, and steps.

- `gui.py` – Pygame desktop GUI:
  - Displays an 8×8 chessboard with Unicode chess symbols.
  - Allows:
    - Loading a random puzzle from Ranger / Melee / Solo FEN files.
    - Jumping to a specific FEN by global index (1–2400).
    - Solving the current position by DFS or A*.
    - Stepping through the solution with Prev/Next buttons or A/D / arrow keys.
    - Playing manually by clicking pieces and targets to capture.

- `fetch_puzzle_chess.py` – Solo Chess crawler:
  - Loads Solo Chess puzzle pages using Playwright.
  - Extracts the board as FEN (piece-placement only).
  - Appends boards to `solo-chess-boards.fen`.

- `chess-ranger-boards.fen`, `chess-melee-boards.fen`, `solo-chess-boards.fen`:
  - Pre-collected FEN datasets (800 positions per mode, with 4–11 pieces).

How to use: command-line solver
-------------------------------

From the `chess-puzzles` folder:

```bash
python solver.py
```

The menu offers:

1. Solve from URL (fetch a board from puzzle-chess.com and solve it with A*).
2. Solve one random board from `chess-ranger-boards.fen`.
3. Solve one random board from `chess-melee-boards.fen`.
4. Solve one random board from `solo-chess-boards.fen`.
5. Run a DFS and A* benchmark on all Ranger boards.
6. Run a DFS and A* benchmark on all Melee boards.
7. Run a DFS and A* benchmark on all Solo boards.
8. Quit.

For option 1 you need `playwright` installed; the script will ask for a puzzle URL (or use a default example) and
will infer the mode (Ranger, Melee, Solo) from the URL.

How to use: GUI
---------------

From the `chess-puzzles` folder:

```bash
python gui.py
```

In the window:

- Use the top buttons to choose:
  - New random puzzle from any mode.
  - A random puzzle within Ranger, Melee, or Solo.
  - A specific puzzle by entering a FEN index (1–2400).
- Use the Solve DFS / Solve A* buttons to compute a solution from the current position.
- Use Prev / Next (or A/D / arrow keys) to move backward and forward through the combined history of manual and
  solver moves, shown in the right-hand Solution panel.
- Click a piece to select it (highlighted) and click a target square to attempt a capture; valid captures update
  the board and are recorded in the move history.

Notes
-----

- FEN strings in the `.fen` files use piece placement only (no side-to-move or castling fields).
- The solver treats colors and side-to-move correctly for Melee and Solo; Ranger allows captures between any pieces.
- Benchmarks can be slow if you run them over all 800 positions per mode; they are intended for offline analysis.

