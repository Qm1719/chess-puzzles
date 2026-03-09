"""
Solitaire Chess Solver v4 — Pygame GUI.
Differences from v3: introduce a desktop GUI for the first time, rendering an 8×8 board and allowing
  click-to-capture interaction driven by the v4 Ranger solver, with buttons to load random puzzles,
  solve them by DFS/A*, and step through the resulting solution or reset back to the initial position.
"""
import os
import sys
import random as rnd

# Allow importing from v3
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from v4.solver import (
    RangerSolver,
    fen_to_pieces,
    pieces_to_fen,
    BoardState,
    move_description_to_san,
)

import pygame

# --- Constants ---
SQ = 60
BOARD_SIZE = 8 * SQ
MARGIN = 16
BUTTON_H = 36
FONT_SIZE = 18
TITLE_H = 40
WIN_W = BOARD_SIZE + 2 * MARGIN
WIN_H = BOARD_SIZE + 2 * MARGIN + TITLE_H + BUTTON_H * 2 + 24

LIGHT = (240, 217, 181)
DARK = (181, 136, 99)
HIGHLIGHT = (255, 255, 100)
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
BUTTON_BG = (70, 130, 180)
BUTTON_HOVER = (100, 160, 210)
BOARD_OX = MARGIN
BOARD_OY = MARGIN + TITLE_H

# Piece name -> single letter for drawing
NAME_TO_LETTER = {
    "King": "K", "Queen": "Q", "Rook": "R",
    "Bishop": "B", "Knight": "N", "Pawn": "P",
}


def pixel_to_square(px, py):
    """Return (row, col) 0-7 if (px,py) is on the board, else None."""
    c = (px - BOARD_OX) // SQ
    r = (py - BOARD_OY) // SQ
    if 0 <= r < 8 and 0 <= c < 8:
        return r, c
    return None


def find_move_child(parent_state, from_r, from_c, to_r, to_c):
    """If moving (from_r,from_c) -> (to_r,to_c) is a legal capture, return that child BoardState else None."""
    if not parent_state.get_piece_at(from_r, from_c) or not parent_state.get_piece_at(to_r, to_c):
        return None
    for child in parent_state.get_legal_moves():
        if child.get_piece_at(from_r, from_c) is None and child.get_piece_at(to_r, to_c) is not None:
            if child.get_piece_at(to_r, to_c).name == parent_state.get_piece_at(from_r, from_c).name:
                return child
    return None


def _fen_path():
    v4_dir = os.path.dirname(os.path.abspath(__file__))
    p = os.path.join(v4_dir, "chess_ranger_boards.fen")
    if os.path.isfile(p):
        return p
    v3_dir = os.path.dirname(v4_dir)
    p2 = os.path.join(v3_dir, "v3", "chess_ranger_boards.fen")
    p3 = os.path.join(v3_dir, "v2", "chess_ranger_boards.fen")
    return p2 if os.path.isfile(p2) else (p3 if os.path.isfile(p3) else p)


def draw_board(surface, font, current_fen=None, highlight_square=None):
    """Draw 8x8 board and pieces from FEN. Row 0 = top (rank 8). highlight_square = (r,c) or None."""
    ox, oy = BOARD_OX, BOARD_OY
    for r in range(8):
        for c in range(8):
            color = LIGHT if (r + c) % 2 == 0 else DARK
            if highlight_square == (r, c):
                color = HIGHLIGHT
            rect = pygame.Rect(ox + c * SQ, oy + r * SQ, SQ, SQ)
            pygame.draw.rect(surface, color, rect)
            pygame.draw.rect(surface, BLACK, rect, 1)
    if not current_fen:
        return
    # Parse FEN and draw pieces (rank 8 = row 0)
    placement = current_fen.strip().split()[0] if current_fen.strip() else current_fen
    ranks = placement.split("/")
    if len(ranks) != 8:
        return
    for row, rank in enumerate(ranks):
        col = 0
        for ch in rank:
            if ch.isdigit():
                col += int(ch)
            elif ch.upper() in "KQRBNP":
                name = {"K": "King", "Q": "Queen", "R": "Rook", "B": "Bishop", "N": "Knight", "P": "Pawn"}[ch.upper()]
                letter = NAME_TO_LETTER[name]
                cx = ox + col * SQ + SQ // 2
                cy = oy + row * SQ + SQ // 2
                text = font.render(letter, True, BLACK)
                tr = text.get_rect(center=(cx, cy))
                surface.blit(text, tr)
                col += 1
        if col != 8:
            break


def draw_ui(surface, font, buttons, step_index, total_steps, move_text):
    """Draw title, step label, move text, and buttons."""
    ox, oy = MARGIN, MARGIN
    title = font.render("Solitaire Chess v4 — reduce to one piece (captures only)", True, BLACK)
    surface.blit(title, (ox, oy + 8))
    y_buttons = MARGIN + TITLE_H + BOARD_SIZE + 8
    step_str = f"Step {step_index + 1}/{total_steps}" if total_steps else "Play (Solve uses initial position)"
    step_surf = font.render(step_str, True, BLACK)
    surface.blit(step_surf, (ox, y_buttons))
    if move_text:
        move_surf = font.render(move_text, True, BLACK)
        surface.blit(move_surf, (ox, y_buttons + 22))
    by = y_buttons + 52
    for key, rect in buttons.items():
        color = BUTTON_HOVER if rect.collidepoint(pygame.mouse.get_pos()) else BUTTON_BG
        pygame.draw.rect(surface, color, rect)
        pygame.draw.rect(surface, BLACK, rect, 1)
        label = font.render(key, True, WHITE)
        lr = label.get_rect(center=rect.center)
        surface.blit(label, lr)


def main():
    pygame.init()
    screen = pygame.display.set_mode((WIN_W, WIN_H), pygame.RESIZABLE)
    pygame.display.set_caption("Solitaire Chess v4")
    font = pygame.font.SysFont("arial", FONT_SIZE) or pygame.font.Font(None, FONT_SIZE)
    clock = pygame.time.Clock()

    solver = RangerSolver()
    initial_fen = None   # loaded position — Solve always uses this
    current_pieces = []  # current board (for interaction); when no solution we show this
    solution_path = []   # list of BoardState from solving initial_fen
    step_index = 0
    selected_square = None  # (r, c) when in play mode
    fen_lines = []

    def load_random():
        nonlocal initial_fen, current_pieces, solution_path, step_index, selected_square
        fen = rnd.choice(fen_lines)[0] if fen_lines else solver.random_puzzle()[1]
        try:
            pieces = fen_to_pieces(fen)
            initial_fen = fen
            current_pieces = [p.clone() for p in pieces]
            solution_path = []
            step_index = 0
            selected_square = None
            return True
        except Exception:
            return False

    def reset_to_initial():
        nonlocal current_pieces, solution_path, step_index, selected_square
        if initial_fen is None:
            return
        try:
            current_pieces = [p.clone() for p in fen_to_pieces(initial_fen)]
            solution_path = []
            step_index = 0
            selected_square = None
        except Exception:
            pass

    # Preload .fen file if present
    fen_path = _fen_path()
    if os.path.isfile(fen_path):
        with open(fen_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    fen = line.split("\t")[0].split("#")[0].strip()
                    if fen:
                        fen_lines.append((fen, None))
    if fen_lines and initial_fen is None:
        try:
            fen = fen_lines[0][0]
            current_pieces = [p.clone() for p in fen_to_pieces(fen)]
            initial_fen = fen
        except Exception:
            pass

    running = True
    while running:
        y_buttons = MARGIN + TITLE_H + BOARD_SIZE + 8
        by = y_buttons + 52
        bw = 95
        gap = 6
        buttons = {
            "New random": pygame.Rect(MARGIN, by, bw, BUTTON_H),
            "Reset": pygame.Rect(MARGIN + bw + gap, by, 56, BUTTON_H),
            "Solve by DFS": pygame.Rect(MARGIN + bw + gap + 56 + gap, by, bw, BUTTON_H),
            "Solve by A*": pygame.Rect(MARGIN + 2 * (bw + gap) + 56 + gap, by, bw, BUTTON_H),
            "Prev": pygame.Rect(MARGIN + 3 * (bw + gap) + 56 + 3 * gap, by, 48, BUTTON_H),
            "Next": pygame.Rect(MARGIN + 3 * (bw + gap) + 56 + 3 * gap + 48 + gap, by, 48, BUTTON_H),
        }

        total_steps = len(solution_path) if solution_path else 0
        move_text = None
        if solution_path and 0 <= step_index < total_steps and step_index > 0:
            san = move_description_to_san(solution_path[step_index].move_description)
            if san:
                move_text = san

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
                break
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                # Buttons
                hit_button = False
                for name, rect in buttons.items():
                    if rect.collidepoint(event.pos):
                        hit_button = True
                        if name == "Random":
                            load_random()
                        elif name == "Reset":
                            reset_to_initial()
                        elif name == "Solve DFS" and initial_fen:
                            try:
                                pieces = fen_to_pieces(initial_fen)
                                state = BoardState(pieces)
                                solution_path = solver.solve_dfs(state)
                                step_index = 0
                            except Exception:
                                solution_path = []
                        elif name == "Solve A*" and initial_fen:
                            try:
                                pieces = fen_to_pieces(initial_fen)
                                state = BoardState(pieces)
                                solution_path = solver.solve_astar(state)
                                step_index = 0
                            except Exception:
                                solution_path = []
                        elif name == "Prev" and solution_path:
                            step_index = max(0, step_index - 1)
                        elif name == "Next" and solution_path:
                            step_index = min(len(solution_path) - 1, step_index + 1)
                        break
                if hit_button:
                    continue
                # Board click (only when no solution showing = play mode)
                if not solution_path and current_pieces:
                    sq = pixel_to_square(*event.pos)
                    if sq is not None:
                        r, c = sq
                        state = BoardState(current_pieces)
                        piece_here = state.get_piece_at(r, c)
                        if selected_square is None:
                            if piece_here:
                                selected_square = (r, c)
                        else:
                            fr, fc = selected_square
                            if (r, c) == (fr, fc):
                                selected_square = None
                            elif piece_here:
                                child = find_move_child(state, fr, fc, r, c)
                                if child is not None:
                                    current_pieces = [p.clone() for p in child.pieces]
                                    selected_square = None
                                else:
                                    selected_square = (r, c)
                            else:
                                selected_square = None

        screen.fill((250, 248, 239))
        if solution_path and 0 <= step_index < len(solution_path):
            fen_to_show = pieces_to_fen(solution_path[step_index].pieces)
            highlight = None
        else:
            fen_to_show = pieces_to_fen(current_pieces) if current_pieces else None
            highlight = selected_square
        draw_board(screen, font, fen_to_show, highlight)
        draw_ui(screen, font, buttons, step_index, total_steps, move_text)
        pygame.display.flip()
        clock.tick(60)

    pygame.quit()


if __name__ == "__main__":
    main()
