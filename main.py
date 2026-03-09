# main.py
from model import Piece, BoardState
from solvers import Solver

def run_demo():
    # 1. Setup bàn cờ mẫu (4 quân)
    # Lưu ý tọa độ: Row 0-7, Col 0-7.
    # (0,0) là góc trên trái (a8), (7,7) là góc dưới phải (h1)

    initial_pieces = [
        Piece('Pawn', 2, 3),
        Piece('Knight', 2, 4), 
        Piece('Rook', 3, 4),
        Piece('Knight', 3, 5) 
    ]

    initial_state = BoardState(initial_pieces)
    solver = Solver()

    # 2. Chạy DFS
    print("\n================ BLIND SEARCH (DFS) ================")
    dfs_path = solver.solve_dfs(initial_state)
    print_solution(dfs_path)

    # 3. Chạy A*
    print("\n================ HEURISTIC SEARCH (A*) ================")
    astar_path = solver.solve_astar(initial_state)
    print_solution(astar_path)

def print_solution(path):
    if not path:
        print("No solution found.")
        return

    print(f"Solution found in {len(path)-1} steps:")
    for i, state in enumerate(path):
        print(f"Step {i}: {state.move_description}")
        print(f"   Board: {state.pieces}")
        print("-" * 30)

if __name__ == "__main__":
    run_demo()