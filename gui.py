import tkinter as tk
from tkinter import ttk, messagebox
import time
from model import Piece, BoardState, PIECE_ICONS
from solvers import Solver


class ChessSolverGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("AI Solitaire Chess Solver")
        self.root.geometry("900x600")

        self.solver = Solver()
        self.delay = 0.1  # Animation speed
        self.is_running = False

        self.setup_ui()
        self.reset_board()

    def setup_ui(self):
        # Layout: Left (Board), Right (Controls & Logs)
        main_frame = tk.Frame(self.root, padx=10, pady=10)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # --- Left Side: Board ---
        board_frame = tk.Frame(main_frame, bg="#333")
        board_frame.pack(side=tk.LEFT, padx=20, pady=20)

        self.cells = {}
        for r in range(8):
            for c in range(8):
                color = "#EEE" if (r + c) % 2 == 0 else "#888"  # Chessboard pattern
                lbl = tk.Label(board_frame, text="", font=("Arial", 24),
                               width=4, height=2, bg=color, relief="raised")
                lbl.grid(row=r, column=c)
                self.cells[(r, c)] = lbl

                # Coordinate labels (optional logic omitted for brevity)

        # --- Right Side: Controls ---
        control_frame = tk.Frame(main_frame)
        control_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        tk.Label(control_frame, text="Algorithm Control", font=("Arial", 14, "bold")).pack(pady=10)

        self.algo_var = tk.StringVar(value="DFS")
        ttk.Radiobutton(control_frame, text="Blind Search (DFS)", variable=self.algo_var, value="DFS").pack(anchor="w")
        ttk.Radiobutton(control_frame, text="Heuristic Search (A*)", variable=self.algo_var, value="A*").pack(
            anchor="w")

        tk.Label(control_frame, text="Animation Speed:").pack(pady=(20, 0))
        self.speed_scale = ttk.Scale(control_frame, from_=0.01, to=1.0, value=0.1, orient=tk.HORIZONTAL)
        self.speed_scale.pack(fill=tk.X, padx=20)

        btn_frame = tk.Frame(control_frame)
        btn_frame.pack(pady=20)
        tk.Button(btn_frame, text="Start Solve", command=self.start_solving, bg="#4CAF50", fg="white",
                  font=("Arial", 12)).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="Reset", command=self.reset_board, bg="#f44336", fg="white", font=("Arial", 12)).pack(
            side=tk.LEFT, padx=5)

        tk.Label(control_frame, text="Log / Status:", font=("Arial", 12, "bold")).pack(anchor="w")
        self.log_text = tk.Text(control_frame, height=15, width=40, state="disabled", bg="#f0f0f0")
        self.log_text.pack(fill=tk.BOTH, expand=True)

    def log(self, message):
        self.log_text.config(state="normal")
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.log_text.config(state="disabled")

    def draw_board(self, state, highlight_color=None):
        # Clear board
        for r in range(8):
            for c in range(8):
                default_bg = "#EEE" if (r + c) % 2 == 0 else "#888"
                self.cells[(r, c)].config(text="", bg=default_bg, fg="black")

        # Draw pieces
        for p in state.pieces:
            icon = PIECE_ICONS.get(p.name, "?")
            self.cells[(p.row, p.col)].config(text=icon)

        self.root.update()

    def reset_board(self):
        # Default Scenario (Example)
        self.initial_pieces = [
            Piece('Pawn', 2, 3),  # d6
            Piece('Knight', 2, 4),  # e6
            Piece('Rook', 3, 4),  # e5
            Piece('Knight', 3, 5)  # f5
        ]
        self.initial_state = BoardState(self.initial_pieces)
        self.draw_board(self.initial_state)
        self.is_running = False
        self.log_text.config(state="normal")
        self.log_text.delete(1.0, tk.END)
        self.log_text.config(state="disabled")
        self.log("Board Reset. Ready.")

    def start_solving(self):
        if self.is_running: return
        self.is_running = True
        algo = self.algo_var.get()
        self.log(f"Starting {algo}...")

        generator = None
        if algo == "DFS":
            generator = self.solver.solve_dfs_generator(self.initial_state)
        else:
            generator = self.solver.solve_astar_generator(self.initial_state)

        self.run_step(generator)

    def run_step(self, generator):
        if not self.is_running: return

        try:
            delay = self.speed_scale.get()
            data = next(generator)
            state, event_type, count = data

            if event_type == 'visit':
                self.draw_board(state)
                # self.log(f"Visiting Node #{count}...")
                # (Commented out log to prevent lag, un-comment to see every step log)
                self.root.after(int(delay * 1000), lambda: self.run_step(generator))

            elif event_type == 'found':
                path = state
                self.log(f"SOLUTION FOUND! Explored {count} nodes.")
                self.animate_solution(path)
                self.is_running = False

            elif event_type == 'failed':
                self.log(f"No solution found after {count} nodes.")
                self.is_running = False

        except StopIteration:
            self.is_running = False

    def animate_solution(self, path):
        self.log("Replaying Solution Sequence...")
        for i, state in enumerate(path):
            self.draw_board(state)
            self.log(f"Step {i}: {state.move_description}")
            time.sleep(1.0)  # Slow replay for user to see
            self.root.update()


if __name__ == "__main__":
    root = tk.Tk()
    app = ChessSolverGUI(root)
    root.mainloop()