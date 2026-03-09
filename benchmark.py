from model import Piece, BoardState
from solvers import Solver


def run_benchmarks():
    solver = Solver()

    # Define Scenarios (Easy to Hard)
    scenarios = [
        {
            "name": "TC_1",
            "pieces": [Piece('Rook', 0, 0), Piece('Knight', 2, 0), Piece('Bishop', 2, 2), Piece('Queen', 0, 2)]
        },
        {
            "name": "TC_2",
            "pieces": [Piece('Pawn', 2, 3), Piece('Knight', 2, 4), Piece('Rook', 3, 4), Piece('Knight', 3, 5)]
        },
        {
            "name": "TC_3",
            "pieces": [Piece('Pawn', 2, 4), Piece('Rook', 2, 2), Piece('Rook', 4, 4), Piece('Bishop', 5, 3)]
        },
        {
            "name": "TC_4",
            "pieces": [Piece('Pawn', 2, 4), Piece('Pawn', 3, 5), Piece('Rook', 2, 2), Piece('Rook', 4, 4), Piece('Bishop', 5, 3)]
        },
        {
            "name": "TC_5",
            "pieces": [Piece('Rook', 3, 4), Piece('Rook', 3, 6), Piece('Pawn', 2, 3), Piece('Knight', 2, 4), Piece('Knight', 3, 5)]
        },
        {
            "name": "TC_6",
            # Trap: Rook at (0,0) can eat the whole row (0,1 -> 0,3),
            # but doing so leaves the Rook at (1,0) stranded.
            # Correct path: Rook at (1,0) must capture (0,0) first.
            "pieces": [
                Piece('Rook', 0, 0),
                Piece('Pawn', 0, 1),
                Piece('Pawn', 0, 2),
                Piece('Pawn', 0, 3),
                Piece('Rook', 1, 0)
            ]
        },
        {
            "name": "TC_7",
            # Two islands of pieces. The Bishop at (1,1) is the only bridge.
            # DFS might exhaustively try to clear one island first, getting stuck.
            "pieces": [
                Piece('Rook', 0, 0), Piece('Pawn', 0, 1),
                Piece('Bishop', 1, 1),  # The Connector
                Piece('Rook', 2, 0), Piece('Pawn', 2, 1),
                Piece('Pawn', 2, 2)
            ]
        },
        {
            "name": "TC_8",
            # 6 Pieces spread out.
            # Requires coordinating the Rooks at opposite ends.
            "pieces": [
                Piece('Rook', 0, 0),
                Piece('Rook', 0, 7),
                Piece('Pawn', 0, 2),
                Piece('Pawn', 0, 5),
                Piece('Queen', 4, 4),
                Piece('Pawn', 2, 2)
            ]
        },
        {
            "name": "TC_9",
            # 6 Pieces spread out.
            # Requires coordinating the Rooks at opposite ends.
            "pieces": [
                Piece('Pawn', 0, 2),
                Piece('Pawn', 0, 5),
                Piece('Queen', 4, 4),
                Piece('Rook', 0, 0),
                Piece('Rook', 0, 7),
                Piece('Pawn', 2, 2)
            ]
        },
        {
            "name": "TC_10",
            # 6 Pieces spread out.
            # Requires coordinating the Rooks at opposite ends.
            "pieces": [
                Piece('Queen', 4, 1),
                Piece('Rook', 0, 0),
                Piece('Rook', 0, 7),
                Piece('Pawn', 2, 2),
                Piece('Pawn', 0, 5),
                Piece('Pawn', 0, 2)
            ]
        },
        {
            "name": "TC_11",
            # 6 Pieces spread out.
            # Requires coordinating the Rooks at opposite ends.
            "pieces": [
                Piece('Queen', 4, 1),
                Piece('Rook', 0, 0),
                Piece('Rook', 0, 7),
                Piece('Pawn', 2, 2),
                Piece('Pawn', 0, 5),
                Piece('Pawn', 0, 2),
                Piece('King', 2, 3)
            ]
        }
    ]

    print(
        f"{'Scenario':<20} | {'Algorithm':<5} | {'Success':<7} | {'Time (s)':<10} | {'Memory (MB)':<12} | {'Nodes':<8} | {'Steps':<5}")
    print("-" * 85)

    for sc in scenarios:
        state = BoardState(sc['pieces'])

        # Test DFS
        res_dfs = solver.solve_with_metrics(state, 'dfs')
        print(
            f"{sc['name']:<20} | DFS       | {str(res_dfs['success']):<7} | {res_dfs['time_sec']:.6f}   | {res_dfs['memory_peak_mb']:.6f}     | {res_dfs['nodes_explored']:<8} | {res_dfs['path_length']:<5}")

        # Test A*
        res_astar = solver.solve_with_metrics(state, 'astar')
        print(
            f"{sc['name']:<20} | A*        | {str(res_astar['success']):<7} | {res_astar['time_sec']:.6f}   | {res_astar['memory_peak_mb']:.6f}     | {res_astar['nodes_explored']:<8} | {res_astar['path_length']:<5}")
        print("-" * 85)


if __name__ == "__main__":
    run_benchmarks()