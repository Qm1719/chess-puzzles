"""
Solitaire Chess Solver v2 — single program.
- Board described by FEN (piece placement only).
- Random puzzles 4–11 pieces; solve check; benchmark (DFS + A*).
- Differences from v1: unify model and solver into one file, add A* search with a heuristic and basic performance
  metrics (nodes, time, memory), and introduce FEN-based random puzzle generation.
"""
import heapq
import os
import random
import re
import sys
import time
import tracemalloc

# --- FEN (piece placement only): rank8/rank7/.../rank1, a-h left to right ---
FEN_TO_NAME = {'K': 'King', 'Q': 'Queen', 'R': 'Rook', 'B': 'Bishop', 'N': 'Knight', 'P': 'Pawn'}
NAME_TO_FEN = {v: k for k, v in FEN_TO_NAME.items()}


def fen_to_pieces(fen: str):
    """Parse FEN placement (first segment if full FEN). Returns list of Piece."""
    placement = fen.strip().split()[0] if fen.strip() else fen.strip()
    ranks = placement.split('/')
    if len(ranks) != 8:
        raise ValueError("FEN must have 8 ranks")
    pieces = []
    for row, rank in enumerate(ranks):  # row 0 = rank 8 (top)
        col = 0
        for c in rank:
            if c.isdigit():
                col += int(c)
            elif c.upper() in FEN_TO_NAME:
                name = FEN_TO_NAME[c.upper()]
                pieces.append(Piece(name, row, col))
                col += 1
            else:
                raise ValueError(f"Invalid FEN character: {c}")
        if col != 8:
            raise ValueError(f"Rank {row} has {col} squares")
    return pieces


def pieces_to_fen(pieces):
    """Board state to FEN placement string (8 ranks)."""
    grid = [[''] * 8 for _ in range(8)]
    for p in pieces:
        if 0 <= p.row < 8 and 0 <= p.col < 8:
            grid[p.row][p.col] = NAME_TO_FEN[p.name]
    rows = []
    for r in range(8):
        s = ''
        empty = 0
        for c in range(8):
            if grid[r][c]:
                if empty:
                    s += str(empty)
                    empty = 0
                s += grid[r][c]
            else:
                empty += 1
        if empty:
            s += str(empty)
        rows.append(s or '8')
    return '/'.join(rows)


def move_description_to_san(desc):
    """Convert 'Rook (e5) -> Knight (f5)' to conventional 'Re5xf5'. Pawn: 'exd5'."""
    if not desc or desc == "Start":
        return None
    # Format: "PieceName (from_sq) -> TargetName (to_sq)"
    m = re.match(r"(\w+)\s*\(([a-h][1-8])\)\s*->\s*\w+\s*\(([a-h][1-8])\)", desc.strip())
    if not m:
        return desc
    piece_name, from_sq, to_sq = m.group(1), m.group(2), m.group(3)
    if piece_name == "Pawn":
        return from_sq[0] + "x" + to_sq  # e.g. exd5
    letter = NAME_TO_FEN.get(piece_name, "?")
    return letter + from_sq + "x" + to_sq  # e.g. Re5xf5, Nc3xe4


# --- Model (from original model.py) ---
COL_MAP = {0: 'a', 1: 'b', 2: 'c', 3: 'd', 4: 'e', 5: 'f', 6: 'g', 7: 'h'}
ROW_MAP = {0: '8', 1: '7', 2: '6', 3: '5', 4: '4', 5: '3', 6: '2', 7: '1'}


class Piece:
    def __init__(self, name, row, col):
        self.name = name
        self.row = row
        self.col = col

    def __repr__(self):
        return f"{self.name}({COL_MAP[self.col]}{ROW_MAP[self.row]})"

    def clone(self):
        return Piece(self.name, self.row, self.col)


class BoardState:
    def __init__(self, pieces, parent=None, move_description="Start"):
        self.pieces = pieces
        self.parent = parent
        self.move_description = move_description
        self.g = 0 if parent is None else parent.g + 1

    def is_goal(self):
        return len(self.pieces) == 1

    def get_piece_at(self, r, c):
        for p in self.pieces:
            if p.row == r and p.col == c:
                return p
        return None

    def state_key(self):
        """Hashable key for visited set (canonical ordering)."""
        return tuple(sorted((p.name, p.row, p.col) for p in self.pieces))

    def get_legal_moves(self):
        successors = []
        for p in self.pieces:
            targets = self._get_capturable_targets(p)
            for target in targets:
                new_pieces = [pc.clone() for pc in self.pieces if pc != p and pc != target]
                moved_p = p.clone()
                moved_p.row, moved_p.col = target.row, target.col
                new_pieces.append(moved_p)
                desc = f"{p.name} ({COL_MAP[p.col]}{ROW_MAP[p.row]}) -> {target.name} ({COL_MAP[target.col]}{ROW_MAP[target.row]})"
                new_state = BoardState(new_pieces, parent=self, move_description=desc)
                successors.append(new_state)
        return successors

    def _get_capturable_targets(self, p):
        targets = []
        directions = []
        if p.name in ['Rook', 'Queen']:
            directions.extend([(0, 1), (0, -1), (1, 0), (-1, 0)])
        if p.name in ['Bishop', 'Queen']:
            directions.extend([(1, 1), (1, -1), (-1, 1), (-1, -1)])
        if p.name == 'Knight':
            for dr, dc in [(2, 1), (2, -1), (-2, 1), (-2, -1), (1, 2), (1, -2), (-1, 2), (-1, -2)]:
                tr, tc = p.row + dr, p.col + dc
                t = self.get_piece_at(tr, tc)
                if t:
                    targets.append(t)
            return targets
        if p.name == 'King':
            for dr, dc in [(0, 1), (0, -1), (1, 0), (-1, 0), (1, 1), (1, -1), (-1, 1), (-1, -1)]:
                tr, tc = p.row + dr, p.col + dc
                t = self.get_piece_at(tr, tc)
                if t:
                    targets.append(t)
            return targets
        if p.name == 'Pawn':
            for dr, dc in [(-1, 1), (-1, -1)]:
                tr, tc = p.row + dr, p.col + dc
                t = self.get_piece_at(tr, tc)
                if t:
                    targets.append(t)
            return targets
        for dr, dc in directions:
            r, c = p.row + dr, p.col + dc
            while 0 <= r < 8 and 0 <= c < 8:
                t = self.get_piece_at(r, c)
                if t:
                    targets.append(t)
                    break
                r += dr
                c += dc
        return targets

    def __lt__(self, other):
        return self.g < other.g


# --- Solver (DFS + A* with visited set, from solvers.py) ---
class Solver:
    def get_solution_path(self, end_state):
        path = []
        current = end_state
        while current:
            path.append(current)
            current = current.parent
        return path[::-1]

    def heuristic(self, state):
        h = len(state.pieces) - 1
        center_bonus = sum(abs(p.row - 3.5) + abs(p.col - 3.5) for p in state.pieces)
        return h + center_bonus * 0.01

    def solve_dfs(self, initial_state):
        stack = [initial_state]
        visited = {initial_state.state_key()}
        while stack:
            curr = stack.pop()
            if curr.is_goal():
                return self.get_solution_path(curr)
            for child in curr.get_legal_moves():
                key = child.state_key()
                if key not in visited:
                    visited.add(key)
                    stack.append(child)
        return None

    def solve_astar(self, initial_state):
        h0 = self.heuristic(initial_state)
        open_set = [(h0, id(initial_state), initial_state)]
        visited = {initial_state.state_key()}
        while open_set:
            _, _, curr = heapq.heappop(open_set)
            if curr.is_goal():
                return self.get_solution_path(curr)
            for child in curr.get_legal_moves():
                key = child.state_key()
                if key not in visited:
                    visited.add(key)
                    f = child.g + self.heuristic(child)
                    heapq.heappush(open_set, (f, id(child), child))
        return None

    def solve_with_metrics(self, initial_state, algorithm='dfs'):
        tracemalloc.start()
        t0 = time.perf_counter()
        visited = {initial_state.state_key()}
        nodes_explored = 0
        solution_found = False
        path_length = 0

        if algorithm == 'dfs':
            stack = [initial_state]
            while stack:
                curr = stack.pop()
                nodes_explored += 1
                if curr.is_goal():
                    solution_found = True
                    path_length = len(self.get_solution_path(curr)) - 1
                    break
                for child in curr.get_legal_moves():
                    key = child.state_key()
                    if key not in visited:
                        visited.add(key)
                        stack.append(child)
        else:  # astar
            open_set = [(self.heuristic(initial_state), id(initial_state), initial_state)]
            while open_set:
                _, _, curr = heapq.heappop(open_set)
                nodes_explored += 1
                if curr.is_goal():
                    solution_found = True
                    path_length = len(self.get_solution_path(curr)) - 1
                    break
                for child in curr.get_legal_moves():
                    key = child.state_key()
                    if key not in visited:
                        visited.add(key)
                        f = child.g + self.heuristic(child)
                        heapq.heappush(open_set, (f, id(child), child))

        t1 = time.perf_counter()
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        return {
            'algorithm': algorithm,
            'success': solution_found,
            'time_sec': t1 - t0,
            'memory_peak_mb': peak / (1024 * 1024),
            'nodes_explored': nodes_explored,
            'path_length': path_length,
        }


# --- Randomizer: 4–11 pieces ---
PIECE_TYPES = ['King', 'Queen', 'Rook', 'Bishop', 'Knight', 'Pawn']


def _squares_that_can_reach(to_r, to_c, piece_name):
    """Squares (from_r, from_c) from which a piece of type piece_name can move to (to_r, to_c)."""
    out = []
    if piece_name == 'Knight':
        for dr, dc in [(2, 1), (2, -1), (-2, 1), (-2, -1), (1, 2), (1, -2), (-1, 2), (-1, -2)]:
            fr, fc = to_r - dr, to_c - dc
            if 0 <= fr < 8 and 0 <= fc < 8:
                out.append((fr, fc))
    elif piece_name == 'King':
        for dr, dc in [(0, 1), (0, -1), (1, 0), (-1, 0), (1, 1), (1, -1), (-1, 1), (-1, -1)]:
            fr, fc = to_r - dr, to_c - dc
            if 0 <= fr < 8 and 0 <= fc < 8:
                out.append((fr, fc))
    elif piece_name == 'Pawn':
        # Pawn captures: moved up-left or up-right (row decreases). So from (to_r+1, to_c±1)
        for fc in (to_c - 1, to_c + 1):
            fr = to_r + 1
            if 0 <= fr < 8 and 0 <= fc < 8:
                out.append((fr, fc))
    elif piece_name in ('Rook', 'Queen'):
        for dc in range(8):
            if dc != to_c:
                out.append((to_r, dc))
        for dr in range(8):
            if dr != to_r:
                out.append((dr, to_c))
    if piece_name in ('Bishop', 'Queen'):
        for dr in range(-7, 8):
            for dc in range(-7, 8):
                if dr != 0 and dc != 0 and abs(dr) == abs(dc):
                    fr, fc = to_r - dr, to_c - dc
                    if 0 <= fr < 8 and 0 <= fc < 8:
                        out.append((fr, fc))
    return out


def _occupied_set(pieces):
    return {(p.row, p.col) for p in pieces}


def random_puzzle(num_pieces=None):
    """Generate random board with 4–11 pieces (may be unsolvable). Returns (pieces, fen)."""
    if num_pieces is None:
        num_pieces = random.randint(4, 11)
    else:
        num_pieces = max(4, min(11, num_pieces))
    squares = [(r, c) for r in range(8) for c in range(8)]
    chosen = random.sample(squares, num_pieces)
    pieces = [Piece(random.choice(PIECE_TYPES), r, c) for (r, c) in chosen]
    fen = pieces_to_fen(pieces)
    return pieces, fen


def random_solvable_puzzle(num_pieces=None, max_attempts=50):
    """
    Generate a random *solvable* puzzle by backward construction (like puzzle-chess.com’s approach).
    Start from 1 piece, repeatedly undo a capture: add a victim and move the capturer back.
    Returns (pieces, fen) with 4–11 pieces, or None if construction failed (e.g. no valid undo).
    """
    if num_pieces is None:
        num_pieces = random.randint(4, 11)
    else:
        num_pieces = max(4, min(11, num_pieces))
    if num_pieces == 1:
        r, c = random.randint(0, 7), random.randint(0, 7)
        pieces = [Piece(random.choice(PIECE_TYPES), r, c)]
        return pieces, pieces_to_fen(pieces)

    # Start with one random piece
    r0, c0 = random.randint(0, 7), random.randint(0, 7)
    pieces = [Piece(random.choice(PIECE_TYPES), r0, c0)]

    for _ in range(num_pieces - 1):  # undo (num_pieces - 1) captures: 1 -> num_pieces
        occupied = _occupied_set(pieces)
        candidates = []  # (piece_index, from_square, victim_type)
        for i, p in enumerate(pieces):
            from_squares = _squares_that_can_reach(p.row, p.col, p.name)
            empty_from = [(fr, fc) for (fr, fc) in from_squares if (fr, fc) not in occupied]
            for (fr, fc) in empty_from:
                for vtype in PIECE_TYPES:
                    candidates.append((i, (fr, fc), vtype))
        if not candidates:
            return None
        i, (fr, fc), vtype = random.choice(candidates)
        capturer = pieces[i]
        # New board: capturer moves back to (fr, fc), victim appears at (capturer.row, capturer.col)
        new_pieces = []
        for j, p in enumerate(pieces):
            if j == i:
                new_pieces.append(Piece(capturer.name, fr, fc))
            else:
                new_pieces.append(Piece(p.name, p.row, p.col))
        new_pieces.append(Piece(vtype, capturer.row, capturer.col))
        pieces = new_pieces

    fen = pieces_to_fen(pieces)
    return pieces, fen


# --- Load .fen data file ---
DEFAULT_FEN_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "puzzle_chess_boards.fen")


def load_fen_file(path=None):
    """Load FEN lines from a file. Returns list of (fen, piece_count or None). Line format: FEN or FEN\t# N pieces."""
    path = path or DEFAULT_FEN_FILE
    if not os.path.isfile(path):
        return []
    out = []
    with open(path, "r", encoding="utf-8") as f:
        for i, line in enumerate(f):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            fen = line.split("\t")[0].split("#")[0].strip()
            if not fen:
                continue
            n = None
            if "#" in line:
                rest = line.split("#", 1)[1].strip()
                for w in rest.split():
                    if w.isdigit():
                        n = int(w)
                        break
            out.append((fen, n))
    return out


def load_benchmark_scenarios(path=None):
    """Load .fen file into list of {'name': ..., 'fen': ...} for run_benchmark."""
    rows = load_fen_file(path)
    return [{"name": f"line_{i+1}", "fen": fen} for i, (fen, _) in enumerate(rows)]


# --- Benchmark ---
def run_benchmark(scenarios=None, use_random=0):
    """
    scenarios: list of dicts with 'name' and 'fen' (or 'pieces').
    use_random: if > 0, add this many random (4–11 piece) boards to the benchmark.
    """
    solver = Solver()
    if scenarios is None:
        scenarios = []

    if use_random > 0:
        for i in range(use_random):
            pieces, fen = random_puzzle()
            scenarios.append({'name': f'Random_{i+1}_{len(pieces)}p', 'fen': fen})

    header = f"{'Scenario':<22} | {'Algo':<5} | {'Success':<7} | {'Time (s)':<10} | {'Memory (MB)':<12} | {'Nodes':<10} | {'Steps':<5}"
    print(header)
    print("-" * len(header))

    all_results = []  # list of (sc_name, algo, res) for averages
    for sc in scenarios:
        if 'pieces' in sc:
            pieces = sc['pieces']
        else:
            pieces = fen_to_pieces(sc['fen'])
        state = BoardState(pieces)

        for algo in ('dfs', 'astar'):
            res = solver.solve_with_metrics(state, algo)
            all_results.append((sc['name'], algo, res))
            print(f"{sc['name']:<22} | {algo.upper():<5} | {str(res['success']):<7} | {res['time_sec']:.6f}   | {res['memory_peak_mb']:.6f}     | {res['nodes_explored']:<10} | {res['path_length']:<5}")
        print("-" * len(header))

    # Overall averages per algorithm
    if scenarios:
        print()
        for algo in ('dfs', 'astar'):
            subset = [res for (_, a, res) in all_results if a == algo]
            succ = sum(1 for r in subset if r['success'])
            avg_time = sum(r['time_sec'] for r in subset) / len(subset)
            avg_mem = sum(r['memory_peak_mb'] for r in subset) / len(subset)
            avg_nodes = sum(r['nodes_explored'] for r in subset) / len(subset)
            avg_steps = sum(r['path_length'] for r in subset) / len(subset)
            print(f"AVERAGE ({algo.upper():<5}) | success {succ}/{len(subset)} | time {avg_time:.6f} s | memory {avg_mem:.6f} MB | nodes {avg_nodes:.0f} | steps {avg_steps:.1f}")
    # Print averages, but only for scenarios in index 701 to 800 inclusive
    if len(scenarios) >= 160:
        print("\nAverages for scenarios 701–800 only (1-based index):")
        selected_indices = range(699, 799 + 1)  # python 0-based
        selected_results = []
        for idx in selected_indices:
            # Each scenario spawns two results (DFS and ASTAR), so find those in all_results
            sc_name = scenarios[idx]['name']
            for algo in ('dfs', 'astar'):
                for r_name, r_algo, r in all_results:
                    if r_name == sc_name and r_algo == algo:
                        selected_results.append((algo, r))
        for algo in ('dfs', 'astar'):
            subset = [r for a, r in selected_results if a == algo]
            if subset:
                succ = sum(1 for r in subset if r['success'])
                avg_time = sum(r['time_sec'] for r in subset) / len(subset)
                avg_mem = sum(r['memory_peak_mb'] for r in subset) / len(subset)
                avg_nodes = sum(r['nodes_explored'] for r in subset) / len(subset)
                avg_steps = sum(r['path_length'] for r in subset) / len(subset)
                print(f"AVG (lines 701–800, {algo.upper():<5}) | success {succ}/{len(subset)} | time {avg_time:.6f} s | memory {avg_mem:.6f} MB | nodes {avg_nodes:.0f} | steps {avg_steps:.1f}")
            else:
                print(f"No results for algorithm {algo} in lines 701–800.")


# --- Main: menu ---
def main():
    solver = Solver()
    default_url = "https://www.puzzle-chess.com/chess-ranger-4/"

    while True:
        print("\n--- Solitaire Chess Solver v2 ---")
        print("1) Solve from URL (fetch puzzle-chess.com)")
        print("2) Solve 1 random board from .fen file")
        print("3) Run benchmark (DFS + A*) on all boards in .fen file")
        print("4) Quit")
        choice = input("Choice [1-4]: ").strip() or "4"

        if choice == '4':
            break

        if choice == '1':
            try:
                from fetch_puzzle_chess import fetch_board_from_url
            except ImportError:
                print("Option 1 requires fetch_puzzle_chess.py (and playwright). Run from v2 folder.", file=sys.stderr)
                continue
            url = input(f"URL [{default_url}]: ").strip() or default_url
            print("Fetching...", file=sys.stderr)
            fen, count = fetch_board_from_url(url)
            if not fen:
                print("Failed to fetch board.", file=sys.stderr)
                continue
            try:
                pieces = fen_to_pieces(fen)
            except Exception as e:
                print("Invalid FEN from page:", e, file=sys.stderr)
                continue
            state = BoardState(pieces)
            print(f"FEN: {fen}")
            print(f"Pieces: {len(pieces)} — {pieces}")
            path = solver.solve_astar(state)
            if path:
                print("Solution: YES.")
                print(f"Steps: {len(path) - 1}")
                for i, s in enumerate(path):
                    print(f"  {i}: {s.move_description}")
            else:
                print("Solution: NO.")

        elif choice == '2':
            rows = load_fen_file()
            if not rows:
                print(f"No FEN file found or empty: {DEFAULT_FEN_FILE}", file=sys.stderr)
                continue
            idx = random.randrange(len(rows))
            fen, _ = rows[idx]
            line_num = idx + 1
            try:
                pieces = fen_to_pieces(fen)
            except Exception as e:
                print("Invalid FEN in file:", e, file=sys.stderr)
                continue
            state = BoardState(pieces)
            print(f"# {line_num}")
            print(f"FEN: {fen}")
            print(f"Pieces: {len(pieces)} — {pieces}")
            path = solver.solve_astar(state)
            if path:
                for i, s in enumerate(path):
                    if i == 0 and s.move_description == "Start":
                        continue
                    san = move_description_to_san(s.move_description)
                    if san:
                        print(san)
            else:
                print("No solution.")

        elif choice == '3':
            scenarios = load_benchmark_scenarios()
            if not scenarios:
                print(f"No boards in .fen file: {DEFAULT_FEN_FILE}", file=sys.stderr)
                continue
            print(f"Benchmarking {len(scenarios)} boards (DFS + A*)...", file=sys.stderr)
            run_benchmark(scenarios, use_random=0)


if __name__ == "__main__":
    main()
