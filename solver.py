"""
Solitaire Chess Solver v5 — pure DFS and A* (Wikipedia/textbook).
Improvements: compact state key, strictly admissible heuristic + tie-break, goal-on-generation.
"""
import heapq
import os
import random
import re
import sys
import time
import tracemalloc

# --- FEN (piece placement only): rank8/rank7/.../rank1, a-h left to right ---, uppercase for white, lowercase for black
FEN_TO_NAME = {'K': 'King', 'Q': 'Queen', 'R': 'Rook', 'B': 'Bishop', 'N': 'Knight', 'P': 'Pawn', 'k': 'King', 'q': 'Queen', 'r': 'Rook', 'b': 'Bishop', 'n': 'Knight', 'p': 'Pawn'}
NAME_TO_FEN = {
    ('King', 'white'): 'K',
    ('Queen', 'white'): 'Q',
    ('Rook', 'white'): 'R',
    ('Bishop', 'white'): 'B',
    ('Knight', 'white'): 'N',
    ('Pawn', 'white'): 'P',
    ('King', 'black'): 'k',
    ('Queen', 'black'): 'q',
    ('Rook', 'black'): 'r',
    ('Bishop', 'black'): 'b',
    ('Knight', 'black'): 'n',
    ('Pawn', 'black'): 'p',
}

# For move text (SAN-like). Independent from NAME_TO_FEN (which is keyed by (name,color)).
PIECE_NAME_TO_SAN = {
    'King': 'K',
    'Queen': 'Q',
    'Rook': 'R',
    'Bishop': 'B',
    'Knight': 'N',
}


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
            elif c in FEN_TO_NAME:
                name = FEN_TO_NAME[c]
                color = 'white' if c.isupper() else 'black'
                pieces.append(Piece(name, row, col, color))
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
            grid[p.row][p.col] = NAME_TO_FEN[(p.name, p.color)]
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
    # print(desc)
    """Convert 'Rook (e5) -> Knight (f5)' to conventional 'Re5xf5'. Pawn: 'exd5'."""
    if not desc or desc == "Start":
        return None
    m = re.match(r"(\w+)\s*\(([a-h][1-8])\)\s*->\s*\w+\s*\(([a-h][1-8])\)", desc.strip())
    if not m:
        return desc
    piece_name, from_sq, to_sq = m.group(1), m.group(2), m.group(3)
    if piece_name == "Pawn":
        return from_sq[0] + " x " + to_sq
    letter = PIECE_NAME_TO_SAN.get(piece_name, "?")
    return letter + from_sq + " x " + to_sq


# --- Model ---
COL_MAP = {0: 'a', 1: 'b', 2: 'c', 3: 'd', 4: 'e', 5: 'f', 6: 'g', 7: 'h'}
ROW_MAP = {0: '8', 1: '7', 2: '6', 3: '5', 4: '4', 5: '3', 6: '2', 7: '1'}


class Piece:
    def __init__(self, name, row, col, color):
        self.name = name
        self.row = row
        self.col = col
        self.color = color
        self.move_count = 0
        
    def __repr__(self):
        return f"{self.name}({COL_MAP[self.col]}{ROW_MAP[self.row]})"
    
    def __melee_repr__(self):
        return f"{self.color} {self.name}({COL_MAP[self.col]}{ROW_MAP[self.row]})"

    def clone(self):
        new_piece = Piece(self.name, self.row, self.col, self.color)
        new_piece.move_count = self.move_count
        return new_piece


class BoardState:
    def __init__(self, pieces, parent=None, move_description="Start", turn="white"):
        self.pieces = pieces
        self.parent = parent
        self.move_description = move_description
        self.g = 0 if parent is None else parent.g + 1
        self.turn = turn
        
    def is_goal(self):
        return len(self.pieces) == 1

    def get_piece_at(self, r, c):
        for p in self.pieces:
            if p.row == r and p.col == c:
                return p
        return None

    def state_key(self):
        """Hashable key for visited set (includes color and side-to-move)."""
        return (self.turn, tuple(sorted((p.name, p.color, p.row, p.col, p.move_count) for p in self.pieces)))

    def get_ranger_legal_moves(self):
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
    
    def get_melee_legal_moves(self, turn): #white pieces move first, black pieces move second in order
        successors = []
        for p in [p for p in self.pieces if p.color == turn]:
            targets = self._get_melee_capturable_targets(p, turn)
            for target in targets:
                new_pieces = [pc.clone() for pc in self.pieces if pc != p and pc != target]
                moved_p = p.clone()
                moved_p.row, moved_p.col = target.row, target.col
                new_pieces.append(moved_p)
                desc = f"{p.name} ({COL_MAP[p.col]}{ROW_MAP[p.row]}) -> {target.name} ({COL_MAP[target.col]}{ROW_MAP[target.row]})"
                new_state = BoardState(new_pieces, parent=self, move_description=desc)
                successors.append(new_state)
        return successors
    
    def get_solo_legal_moves(self):
        successors = []
        for p in self.pieces:
            if p.move_count >= 2:
                continue
            targets = self._get_solo_capturable_targets(p)
            for target in targets:
                new_pieces = [pc.clone() for pc in self.pieces if pc != p and pc != target]
                moved_p = p.clone()
                moved_p.move_count = p.move_count + 1
                moved_p.row, moved_p.col = target.row, target.col
                new_pieces.append(moved_p)
                desc = f"{p.name} ({COL_MAP[p.col]}{ROW_MAP[p.row]}) -> {target.name} ({COL_MAP[target.col]}{ROW_MAP[target.row]})"
                new_state = BoardState(new_pieces, parent=self, move_description=desc)
                successors.append(new_state)
        return successors
    
    def _get_capturable_targets(self, p, turn = 'white'):
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
            # Pawns capture diagonally forward relative to side to move.
            # Ranger (no colors) uses the default 'white' direction (up the board).
            if turn == 'black':
                pawn_dirs = [(1, 1), (1, -1)]     # black moves "down"
            else:
                pawn_dirs = [(-1, 1), (-1, -1)]   # white / default moves "up"
            for dr, dc in pawn_dirs:
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
    
    def _get_melee_capturable_targets(self, p, turn):
        targets = self._get_capturable_targets(p, turn)
        return [t for t in targets if t.color != p.color]
    
    def _get_solo_capturable_targets(self, p):
        targets = self._get_capturable_targets(p)
        return [t for t in targets if t.name != 'King']
    
    def __lt__(self, other):
        return self.g < other.g


# --- Solver: pure DFS and A* ---
class RangerSolver:
    """
    - Pieces move as standard chess pieces.
    - You can perform only capture moves.
    - You are allowed to capture the king.
    - The goal is to end up with one single piece on the board.
    """
    def _ranger_next_states(self, state):
        return state.get_ranger_legal_moves()

    def solve_dfs(self, initial_state):
        return dfs(initial_state, self._ranger_next_states)

    def solve_astar(self, initial_state):
        return astar(initial_state, self._ranger_next_states)

    def solve_with_metrics(self, initial_state, algorithm='dfs'):
        tracemalloc.start()
        t0 = time.perf_counter()
        tracked_metrics = [0, False, 0] # [nodes_explored, solution_found, path_length]

        if algorithm == 'dfs':
            dfs(initial_state, self._ranger_next_states, with_metrics=True, tracked_metrics=tracked_metrics)
        else:
            astar(initial_state, self._ranger_next_states, with_metrics=True, tracked_metrics=tracked_metrics)

        t1 = time.perf_counter()
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        return {
            'algorithm': algorithm,
            'success': tracked_metrics[1],
            'time_sec': t1 - t0,
            'memory_peak_mb': peak / (1024 * 1024),
            'nodes_explored': tracked_metrics[0],
            'path_length': tracked_metrics[2],
        }

class MeleeSolver:
    """
    - Pieces move as standard chess pieces.
    - White moves first.
    - You can perform only capture moves.
    - The goal is to end up with one single piece on the board.
    """
    def _melee_next_states(self, state):
        # Generate children and flip side-to-move for melee.
        children = []
        for child in state.get_melee_legal_moves(state.turn):
            child.turn = 'black' if state.turn == 'white' else 'white'
            children.append(child)
        return children

    def solve_dfs(self, initial_state):
        initial_state.turn = 'white'
        return dfs(initial_state, self._melee_next_states)

    def solve_astar(self, initial_state):
        initial_state.turn = 'white'
        return astar(initial_state, self._melee_next_states)
    
    def solve_with_metrics(self, initial_state, algorithm='dfs'):
        tracemalloc.start()
        t0 = time.perf_counter()
        initial_state.turn = 'white'
        tracked_metrics = [0, False, 0] # [nodes_explored, solution_found, path_length]

        if algorithm == 'dfs':
            dfs(initial_state, self._melee_next_states, with_metrics=True, tracked_metrics=tracked_metrics)
        else:
            astar(initial_state, self._melee_next_states, with_metrics=True, tracked_metrics=tracked_metrics)

        t1 = time.perf_counter()
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        return {
            'algorithm': algorithm,
            'success': tracked_metrics[1],
            'time_sec': t1 - t0,
            'memory_peak_mb': peak / (1024 * 1024),
            'nodes_explored': tracked_metrics[0],
            'path_length': tracked_metrics[2],
        }
       
class SoloSolver:
    """
    - Pieces move as standard chess pieces.
    - You can perform only capture moves.
    - You can move a piece only twice.
    - You are NOT allowed to capture the king.
    - The goal is to end up with one single piece (the king) on the board.
    """
    def _solo_next_states(self, state):
        return state.get_solo_legal_moves()
    
    def solve_dfs(self, initial_state):
        return dfs(initial_state, self._solo_next_states)

    def solve_astar(self, initial_state):
        return astar(initial_state, self._solo_next_states)

    def solve_with_metrics(self, initial_state, algorithm='dfs'):
        tracemalloc.start()
        t0 = time.perf_counter()
        tracked_metrics = [0, False, 0] # [nodes_explored, solution_found, path_length]

        if algorithm == 'dfs':
            dfs(initial_state, self._solo_next_states, with_metrics=True, tracked_metrics=tracked_metrics)
        else:
            astar(initial_state, self._solo_next_states, with_metrics=True, tracked_metrics=tracked_metrics)

        t1 = time.perf_counter()
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        return {
            'algorithm': algorithm,
            'success': tracked_metrics[1],
            'time_sec': t1 - t0,
            'memory_peak_mb': peak / (1024 * 1024),
            'nodes_explored': tracked_metrics[0],
            'path_length': tracked_metrics[2],
        }
        
# --- Load .fen data file ---
def _default_ranger_fen_path():
    v5_dir = os.path.dirname(os.path.abspath(__file__))
    p = os.path.join(v5_dir, "chess-ranger-boards.fen")
    if os.path.isfile(p):
        return p
    v5_path = os.path.join(os.path.dirname(v5_dir), "v5", "chess-ranger-boards.fen")
    return v5_path if os.path.isfile(v5_path) else p


def _default_melee_fen_path():
    v5_dir = os.path.dirname(os.path.abspath(__file__))
    p = os.path.join(v5_dir, "chess-melee-boards.fen")
    if os.path.isfile(p):
        return p
    v5_path = os.path.join(os.path.dirname(v5_dir), "v5", "chess-melee-boards.fen")
    return v5_path if os.path.isfile(v5_path) else p

def _default_solo_fen_path():
    v5_dir = os.path.dirname(os.path.abspath(__file__))
    p = os.path.join(v5_dir, "solo-chess-boards.fen")
    if os.path.isfile(p):
        return p
    v5_path = os.path.join(os.path.dirname(v5_dir), "v5", "solo-chess-boards.fen")
    return v5_path if os.path.isfile(v5_path) else p

def load_ranger_fen_file(path=None):
    path = path or _default_ranger_fen_path()
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

def load_melee_fen_file(path=None):
    path = path or _default_melee_fen_path()
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

def load_solo_fen_file(path=None):
    path = path or _default_solo_fen_path()
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

def load_ranger_benchmark_scenarios(path=None):
    rows = load_ranger_fen_file(path)
    return [{"name": f"line_{i+1}", "fen": fen} for i, (fen, _) in enumerate(rows)]

def load_melee_benchmark_scenarios(path=None):
    rows = load_melee_fen_file(path)
    return [{"name": f"line_{i+1}", "fen": fen} for i, (fen, _) in enumerate(rows)]

def load_solo_benchmark_scenarios(path=None):
    rows = load_solo_fen_file(path)
    return [{"name": f"line_{i+1}", "fen": fen} for i, (fen, _) in enumerate(rows)]

# --- Benchmark ---
def run_benchmark(scenarios=None, use_random=0, solver_obj=None):
    if solver_obj is None:
        solver_obj = RangerSolver()
    if scenarios is None:
        scenarios = []

    header = f"{'Scenario':<22} | {'Algo':<5} | {'Success':<7} | {'Time (s)':<10} | {'Memory (MB)':<12} | {'Nodes':<10} | {'Steps':<5}"
    print(header)
    print("-" * len(header))
    all_results = []
    for sc in scenarios:
        pieces = sc['pieces'] if 'pieces' in sc else fen_to_pieces(sc['fen'])
        state = BoardState(pieces)
        for algo in ('dfs', 'astar'):
            res = solver_obj.solve_with_metrics(state, algo)
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
        # Print averages, but only for scenarios in index 701 to 800
        if len(scenarios) >= 700:
            print("\nAverages for scenarios 701–800 only (11-piece boards):")
            selected_indices = range(700, 800)  # python 0-based
            selected_results = []
            for idx in selected_indices:
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





def get_solution_path(end_state):
        path = []
        current = end_state
        while current:
            path.append(current)
            current = current.parent
        return path[::-1]

def heuristic(state):
    """Admissible: minimum remaining captures = pieces - 1."""
    return len(state.pieces) - 1

def heuristic_h_and_center(state):
    """Single pass: (h, center_sum) for A* and tie-breaking. Avoids two iterations over pieces."""
    n = len(state.pieces)
    h = n - 1
    c = sum(abs(p.row - 3.5) + abs(p.col - 3.5) for p in state.pieces)
    return h, c
    
def dfs(initial_state, next_states_fn, with_metrics=False, tracked_metrics=None):
    # tracked_metrics = [nodes_explored, solution_found, path_length] = [0, False, 0]
    stack = [initial_state]
    visited = {initial_state.state_key()}
    while stack:
        if with_metrics:
            tracked_metrics[0] += 1
        curr = stack.pop()
        if curr.is_goal():
            path = get_solution_path(curr)
            if with_metrics:
                tracked_metrics[1] = True
                tracked_metrics[2] = len(path) - 1
            return path
        for child in next_states_fn(curr):
            key = child.state_key()
            if key not in visited:
                visited.add(key)
                stack.append(child)
    return None

def astar(initial_state, next_states_fn, with_metrics=False, tracked_metrics=None):
    # tracked_metrics = [nodes_explored, solution_found, path_length] = [0, False, 0]
    h0, c0 = heuristic_h_and_center(initial_state)
    push_order = 0
    open_set = [(h0, h0, c0, -push_order, initial_state)]
    push_order += 1
    visited = {initial_state.state_key()}
    while open_set:
        if with_metrics:
            tracked_metrics[0] += 1
        _, _, _, _, curr = heapq.heappop(open_set)
        if curr.is_goal():
            path = get_solution_path(curr)
            if with_metrics:
                tracked_metrics[1] = True
                tracked_metrics[2] = len(path) - 1
            return path
        for child in next_states_fn(curr):
            key = child.state_key()
            if key not in visited:
                visited.add(key)
                h, c = heuristic_h_and_center(child)
                f = child.g + h
                heapq.heappush(open_set, (f, h, c, -push_order, child))
                push_order += 1
    return None

# --- Main ---
def main():
    ranger_solver = RangerSolver()
    melee_solver = MeleeSolver()
    solo_solver = SoloSolver()
    solver = {
        'ranger': ranger_solver,
        'melee': melee_solver,
        'solo': solo_solver,
    }
    default_url = "https://www.puzzle-chess.com/chess-ranger-4/?e=MDoxMSw0NjMsNjM1"

    while True:
        print("\n--- Solitaire Chess Solver v5 (pure DFS + A*) ---")
        print("1) Solve from URL (fetch puzzle-chess.com)")
        print("2) Solve 1 random board from ranger .fen file")
        print("3) Solve 1 random board from melee .fen file")
        print("4) Solve 1 random board from solo .fen file")
        print("5) Run benchmark (DFS + A*) on all boards in ranger .fen file")
        print("6) Run benchmark (DFS + A*) on all boards in melee .fen file")
        print("7) Run benchmark (DFS + A*) on all boards in solo .fen file")
        print("8) Quit")
        choice = input("Choice [1-8]: ").strip() or "8"
        if choice == '8':
            break

        if choice == '1':
            # Fetch a board from puzzle-chess.com (Ranger / Solo / Melee) and solve it.
            try:
                from fetch_puzzle_chess import fetch_board_from_url
            except ImportError:
                print("Option 1 requires v5/fetch_puzzle_chess.py (and playwright).", file=sys.stderr)
                continue
            print("Click Share button, copy the link in 'Embed URL:' and paste it here")
            url = input(f"Example URL [{default_url}]: ").strip() or default_url
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

            url_lower = url.lower()
            if "solo-chess" in url_lower:
                solver_obj = solo_solver
            elif "chess-melee" in url_lower or "melee" in url_lower:
                solver_obj = melee_solver
            else:
                solver_obj = ranger_solver

            path = solver_obj.solve_astar(state)
            if path:
                print("Solution: YES.", f"Steps: {len(path)-1}")
                for i, s in enumerate(path):
                    print(f"  {i}: {s.move_description}")
            else:
                print("Solution: NO.")

        elif choice == '2' or choice == '3' or choice == '4':
            if choice == '2':
                rows = load_ranger_fen_file()
            elif choice == '3':
                rows = load_melee_fen_file()
            elif choice == '4':
                rows = load_solo_fen_file()
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
            if choice == '2':
                path = solver['ranger'].solve_astar(state)
            elif choice == '3':
                path = solver['melee'].solve_astar(state)
            elif choice == '4':
                path = solver['solo'].solve_astar(state)
            else:
                print("Invalid choice.", file=sys.stderr)
                continue
            if path:
                for s in path:
                    if s.move_description != "Start":
                        san = move_description_to_san(s.move_description)
                        if san:
                            print(san)
            else:
                print("No solution.")

        elif choice == '5' or choice == '6' or choice == '7':
            if choice == '5':
                scenarios = load_ranger_benchmark_scenarios()
                bench_solver = ranger_solver
            elif choice == '6':
                scenarios = load_melee_benchmark_scenarios()
                bench_solver = melee_solver
            elif choice == '7':
                scenarios = load_solo_benchmark_scenarios()
                bench_solver = solo_solver
            if not scenarios:
                print("No boards in .fen file.", file=sys.stderr)
                continue
            print(f"Benchmarking {len(scenarios)} boards...", file=sys.stderr)
            run_benchmark(scenarios, use_random=0, solver_obj=bench_solver)


if __name__ == "__main__":
    main()
