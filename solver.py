"""
Solitaire Chess Solver v3 — pure DFS and A* (Wikipedia/textbook).
Differences from v2: keep the same single-variant model but replace the heuristic with a strictly admissible
  one (pieces − 1), add a center-based tie-break for A*, and clean up DFS/A* and metrics to follow the textbook
  versions more closely (compact state keys, goal-on-generation, stable heap ordering).
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
    for row, rank in enumerate(ranks):
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
    m = re.match(r"(\w+)\s*\(([a-h][1-8])\)\s*->\s*\w+\s*\(([a-h][1-8])\)", desc.strip())
    if not m:
        return desc
    piece_name, from_sq, to_sq = m.group(1), m.group(2), m.group(3)
    if piece_name == "Pawn":
        return from_sq[0] + "x" + to_sq
    letter = NAME_TO_FEN.get(piece_name, "?")
    return letter + from_sq + "x" + to_sq


# --- Model ---
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
        """Hashable key for visited set (canonical tuple; fast to build and hash)."""
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


# --- Solver: pure DFS and A* ---
class Solver:
    def get_solution_path(self, end_state):
        path = []
        current = end_state
        while current:
            path.append(current)
            current = current.parent
        return path[::-1]

    def heuristic(self, state):
        """Admissible: minimum remaining captures = pieces - 1."""
        return len(state.pieces) - 1

    @staticmethod
    def _h_and_center(state):
        """Single pass: (h, center_sum) for A* and tie-breaking. Avoids two iterations over pieces."""
        n = len(state.pieces)
        h = n - 1
        c = sum(abs(p.row - 3.5) + abs(p.col - 3.5) for p in state.pieces)
        return h, c

    def solve_dfs(self, initial_state):
        """Pure DFS: stack, visited set. Goal checked when expanding (faster than on every child)."""
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
        """Pure A*: f = g + h, admissible h. Tie-break: more-central first, then LIFO. Single-pass h+c."""
        h0, c0 = self._h_and_center(initial_state)
        push_order = 0
        open_set = [(h0, h0, c0, -push_order, initial_state)]
        push_order += 1
        visited = {initial_state.state_key()}
        while open_set:
            _, _, _, _, curr = heapq.heappop(open_set)
            if curr.is_goal():
                return self.get_solution_path(curr)
            for child in curr.get_legal_moves():
                key = child.state_key()
                if key not in visited:
                    visited.add(key)
                    h, c = self._h_and_center(child)
                    f = child.g + h
                    heapq.heappush(open_set, (f, h, c, -push_order, child))
                    push_order += 1
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
        else:
            h0, c0 = self._h_and_center(initial_state)
            push_order = 0
            open_set = [(h0, h0, c0, -push_order, initial_state)]
            push_order += 1
            while open_set:
                _, _, _, _, curr = heapq.heappop(open_set)
                nodes_explored += 1
                if curr.is_goal():
                    solution_found = True
                    path_length = len(self.get_solution_path(curr)) - 1
                    break
                for child in curr.get_legal_moves():
                    key = child.state_key()
                    if key not in visited:
                        visited.add(key)
                        h, c = self._h_and_center(child)
                        f = child.g + h
                        heapq.heappush(open_set, (f, h, c, -push_order, child))
                        push_order += 1

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


# --- Load .fen data file ---
def _default_fen_path():
    v3_dir = os.path.dirname(os.path.abspath(__file__))
    p = os.path.join(v3_dir, "puzzle_chess_boards.fen")
    if os.path.isfile(p):
        return p
    v2_path = os.path.join(os.path.dirname(v3_dir), "v2", "puzzle_chess_boards.fen")
    return v2_path if os.path.isfile(v2_path) else p


def load_fen_file(path=None):
    path = path or _default_fen_path()
    if not os.path.isfile(path):
        return []
    out = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            fen = line.split("\t")[0].split("#")[0].strip()
            if not fen:
                continue
            out.append((fen, None))
    return out


def load_benchmark_scenarios(path=None):
    rows = load_fen_file(path)
    return [{"name": f"line_{i+1}", "fen": fen} for i, (fen, _) in enumerate(rows)]


# --- Benchmark ---
def run_benchmark(scenarios=None, use_random=0):
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
    all_results = []
    for sc in scenarios:
        pieces = sc['pieces'] if 'pieces' in sc else fen_to_pieces(sc['fen'])
        state = BoardState(pieces)
        for algo in ('dfs', 'astar'):
            res = solver.solve_with_metrics(state, algo)
            all_results.append((sc['name'], algo, res))
            print(f"{sc['name']:<22} | {algo.upper():<5} | {str(res['success']):<7} | {res['time_sec']:.6f}   | {res['memory_peak_mb']:.6f}     | {res['nodes_explored']:<10} | {res['path_length']:<5}")
        print("-" * len(header))
    if scenarios:
        print()
        for algo in ('dfs', 'astar'):
            subset = [res for (_, a, res) in all_results if a == algo]
            succ = sum(1 for r in subset if r['success'])
            n = len(subset)
            print(f"AVERAGE ({algo.upper():<5}) | success {succ}/{n} | time {sum(r['time_sec'] for r in subset)/n:.6f} s | memory {sum(r['memory_peak_mb'] for r in subset)/n:.6f} MB | nodes {sum(r['nodes_explored'] for r in subset)/n:.0f} | steps {sum(r['path_length'] for r in subset)/n:.1f}")
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
                        n = len(subset)
                        print(f"AVERAGE (lines 701–800, {algo.upper():<5}) | success {succ}/{n} | time {sum(r['time_sec'] for r in subset)/n:.6f} s | memory {sum(r['memory_peak_mb'] for r in subset)/n:.6f} MB | nodes {sum(r['nodes_explored'] for r in subset)/n:.0f} | steps {sum(r['path_length'] for r in subset)/n:.1f}")
                    else:
                        print(f"No results for algorithm {algo} in lines 701–800.")


# --- Randomizer (minimal) ---
PIECE_TYPES = ['King', 'Queen', 'Rook', 'Bishop', 'Knight', 'Pawn']


def random_puzzle(num_pieces=None):
    if num_pieces is None:
        num_pieces = random.randint(4, 11)
    num_pieces = max(4, min(11, num_pieces))
    squares = [(r, c) for r in range(8) for c in range(8)]
    chosen = random.sample(squares, num_pieces)
    pieces = [Piece(random.choice(PIECE_TYPES), r, c) for (r, c) in chosen]
    return pieces, pieces_to_fen(pieces)


# --- Main ---
def main():
    solver = Solver()
    default_url = "https://www.puzzle-chess.com/chess-ranger-4/"

    while True:
        print("\n--- Solitaire Chess Solver v3 (pure DFS + A*) ---")
        print("1) Solve from URL (fetch puzzle-chess.com)")
        print("2) Solve 1 random board from .fen file")
        print("3) Run benchmark (DFS + A*) on all boards in .fen file")
        print("4) Quit")
        choice = input("Choice [1-4]: ").strip() or "4"
        if choice == '4':
            break

        if choice == '1':
            try:
                sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "v2"))
                from fetch_puzzle_chess import fetch_board_from_url
            except ImportError:
                print("Option 1 requires v2/fetch_puzzle_chess.py (and playwright).", file=sys.stderr)
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
                print("Invalid FEN:", e, file=sys.stderr)
                continue
            state = BoardState(pieces)
            print(f"FEN: {fen}\nPieces: {len(pieces)} — {pieces}")
            path = solver.solve_astar(state)
            if path:
                print("Solution: YES.", f"Steps: {len(path)-1}")
                for i, s in enumerate(path):
                    print(f"  {i}: {s.move_description}")
            else:
                print("Solution: NO.")

        elif choice == '2':
            rows = load_fen_file()
            if not rows:
                print("No .fen file found.", file=sys.stderr)
                continue
            idx = random.randrange(len(rows))
            fen, _ = rows[idx]
            try:
                pieces = fen_to_pieces(fen)
            except Exception as e:
                print("Invalid FEN:", e, file=sys.stderr)
                continue
            state = BoardState(pieces)
            print(f"# {idx+1}\nFEN: {fen}\nPieces: {len(pieces)} — {pieces}")
            path = solver.solve_astar(state)
            if path:
                for s in path:
                    if s.move_description != "Start":
                        san = move_description_to_san(s.move_description)
                        if san:
                            print(san)
            else:
                print("No solution.")

        elif choice == '3':
            scenarios = load_benchmark_scenarios()
            if not scenarios:
                print("No boards in .fen file.", file=sys.stderr)
                continue
            print(f"Benchmarking {len(scenarios)} boards...", file=sys.stderr)
            run_benchmark(scenarios, use_random=0)


if __name__ == "__main__":
    main()
