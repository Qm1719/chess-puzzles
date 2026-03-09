"""
Solitaire Chess Solver v5 — Pygame GUI.

Supports three puzzle types (Chess Ranger, Chess Melee, Solo Chess) sharing the same UI:
- New random from any of the 3 .fen files
- New puzzle per mode (Ranger / Melee / Solo)
- Jump to a specific FEN by global index 1–2400
- Solve by DFS or A* from the initial state
- Step through the solution with Prev/Next or arrow / A,D keys

Interaction (click-to-capture) is supported in Ranger mode; Solve always uses the initial loaded state.
"""
import os
import sys
import random as rnd

# Allow importing from project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from v5.solver import (
    RangerSolver,
    MeleeSolver,
    SoloSolver,
    fen_to_pieces,
    pieces_to_fen,
    BoardState,
    load_ranger_fen_file,
    load_melee_fen_file,
    load_solo_fen_file,
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
MOVE_PANEL_W = 120  # right side: solution steps, one move per line
WIN_W = BOARD_SIZE + 2 * MARGIN + MOVE_PANEL_W
WIN_H = BOARD_SIZE + 2 * MARGIN + TITLE_H + BUTTON_H * 3 + 24

LIGHT = (240, 217, 181) #F0D9B5, same as the site
DARK = (181, 136, 99) # B58863, same as the site
HIGHLIGHT = (255, 255, 100)
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
BUTTON_BG = (70, 130, 180)
BUTTON_HOVER = (100, 160, 210)
BOARD_OX = MARGIN
BOARD_OY = MARGIN + TITLE_H

# Unicode chess pieces (white/black) by type
WHITE_PIECE_CHAR = {
    "K": "♚", "Q": "♛", "R": "♜",
    "B": "♝", "N": "♞", "P": "♟",
}
BLACK_PIECE_CHAR = {
    "k": "♚", "q": "♛", "r": "♜",
    "b": "♝", "n": "♞", "p": "♟",
}

def pixel_to_square(px, py):
    """Return (row, col) 0-7 if (px,py) is on the board, else None."""
    c = (px - BOARD_OX) // SQ
    r = (py - BOARD_OY) // SQ
    if 0 <= r < 8 and 0 <= c < 8:
        return r, c
    return None

def find_move_child_ranger(parent_state, from_r, from_c, to_r, to_c):
    """If moving (from_r,from_c) -> (to_r,to_c) is a legal capture in Ranger mode, return that child BoardState else None."""
    if not parent_state.get_piece_at(from_r, from_c) or not parent_state.get_piece_at(to_r, to_c):
        return None
    for child in parent_state.get_ranger_legal_moves():
        if child.get_piece_at(from_r, from_c) is None and child.get_piece_at(to_r, to_c) is not None:
            if child.get_piece_at(to_r, to_c).name == parent_state.get_piece_at(from_r, from_c).name:
                return child
    return None


def draw_board(surface, piece_font, current_fen=None, highlight_square=None):
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
    # print(current_fen)
    placement = current_fen.strip().split()[0] if current_fen.strip() else current_fen
    ranks = placement.split("/")
    if len(ranks) != 8:
        return
    for row, rank in enumerate(ranks):
        col = 0
        for ch in rank:
            if ch.isdigit():
                col += int(ch)
            elif ch in "KQRBNPkqrbnp":
                # print(ch)
                piece_map = WHITE_PIECE_CHAR if ch.isupper() else BLACK_PIECE_CHAR
                glyph = piece_map[ch]
                fg = WHITE if ch.isupper() else BLACK
                cx = ox + col * SQ + SQ // 2
                cy = oy + row * SQ + SQ // 2
                # line color is black for glyph
                outline_color = BLACK if ch.isupper() else WHITE
                outline_width = 1
                for dx in (-outline_width, 0, outline_width):
                    for dy in (-outline_width, 0, outline_width):
                        if dx != 0 or dy != 0:
                            outline = piece_font.render(glyph, True, outline_color)
                            outline_rect = outline.get_rect(center=(cx + dx, cy + dy))
                            surface.blit(outline, outline_rect)
                text = piece_font.render(glyph, True, fg)
                tr = text.get_rect(center=(cx, cy))
                surface.blit(text, tr)
                col += 1
        if col != 8:
            break


def draw_move_list(surface, font, solution_path, step_index):
    """Draw solution steps on the right of the board: one move per line. Shows only moves 1..step_index (Prev removes the latest line)."""
    x = BOARD_OX + BOARD_SIZE + 12
    y = BOARD_OY
    line_h = font.get_height() + 2
    # Title
    title = font.render("Solution", True, BLACK)
    surface.blit(title, (x, y))
    y += line_h + 4
    if not solution_path or step_index < 1:
        return
    # Moves 1..step_index (so when user clicks Prev, step_index decreases and the last line disappears)
    for i in range(1, step_index + 1):
        if i >= len(solution_path):
            break
        san = move_description_to_san(solution_path[i].move_description)
        if san:
            line = font.render(f"{i}. {san}", True, BLACK)
            surface.blit(line, (x, y))
        y += line_h


def draw_ui(surface, font, buttons, step_index, total_steps, move_text, mode, current_fen_number):
    """Draw title, step label, move text, and buttons."""
    current_fen_number += 1
    ox, oy = MARGIN, MARGIN
    title = font.render("Solitaire Chess v5 — Ranger / Melee / Solo", True, BLACK)
    surface.blit(title, (ox, oy + 8))
    # Subtitle is the FEN of the current position, same line as the title and right aligned
    if mode == "ranger" and current_fen_number is not None:
        subtitle = font.render(f"Chess Ranger #{current_fen_number}", True, BLACK)
    elif mode == "melee" and current_fen_number is not None:
        subtitle = font.render(f"Melee Chess #{current_fen_number}", True, BLACK)
    elif mode == "solo" and current_fen_number is not None:
        subtitle = font.render(f"Solo Chess #{current_fen_number}", True, BLACK)
    else:
        subtitle = font.render(f"{mode} Chess #1", True, BLACK)
    subtitle_rect = subtitle.get_rect(topright=(ox + BOARD_SIZE, oy + 8))
    surface.blit(subtitle, subtitle_rect)
    # y_buttons = MARGIN + TITLE_H + BOARD_SIZE + 8
    # step_str = f"Step {step_index + 1}/{total_steps}" if total_steps else "Play (Solve uses initial position)"
    # step_surf = font.render(step_str, True, BLACK)
    # surface.blit(step_surf, (ox, y_buttons))
    # if move_text:
    #     move_surf = font.render(move_text, True, BLACK)
    #     surface.blit(move_surf, (ox, y_buttons + 22))
    # by = y_buttons + 52
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
    pygame.display.set_caption("Solitaire Chess v5")
    ui_font = pygame.font.SysFont("arial", FONT_SIZE) or pygame.font.Font(None, FONT_SIZE)
    piece_font = pygame.font.SysFont("segoe ui symbol", SQ - 20) or ui_font
    clock = pygame.time.Clock()

    ranger_solver = RangerSolver()
    melee_solver = MeleeSolver()
    solo_solver = SoloSolver()

    # Load all .fen sets (Ranger / Melee / Solo)
    ranger_rows = load_ranger_fen_file()
    melee_rows = load_melee_fen_file()
    solo_rows = load_solo_fen_file()

    initial_fen = None        # loaded position — Solve always uses this
    current_pieces = []       # current board (for interaction); when no solution we show this
    solution_path = []        # list of BoardState from solving initial_fen
    step_index = 0
    selected_square = None    # (r, c) when in play mode
    current_mode = "ranger"   # "ranger" | "melee" | "solo"
    current_fen_number = 0

    fen_input_text = ""       # text for global FEN # input (1–2400)
    fen_input_active = False

    def set_position_from_fen(mode, fen):
        nonlocal current_mode, initial_fen, current_pieces, solution_path, step_index, selected_square
        try:
            pieces = fen_to_pieces(fen)
        except Exception:
            return False
        current_mode = mode
        initial_fen = fen
        current_pieces = [p.clone() for p in pieces]
        solution_path = []
        step_index = 0
        selected_square = None
        return True

    def load_random_any():
        """Pick a random mode that has boards, then a random FEN from it."""
        modes = []
        if ranger_rows:
            modes.append("ranger")
        if melee_rows:
            modes.append("melee")
        if solo_rows:
            modes.append("solo")
        if not modes:
            return False
        mode = rnd.choice(modes)
        return load_random_mode(mode)

    def load_random_mode(mode):
        """Load a random puzzle for a specific mode."""
        if mode == "ranger":
            rows = ranger_rows
        elif mode == "melee":
            rows = melee_rows
        else:
            rows = solo_rows
        if not rows:
            return False
        nonlocal current_fen_number
        current_fen_number = rnd.randint(1, len(rows))
        fen = rows[current_fen_number - 1][0]
        return set_position_from_fen(mode, fen)

    def reset_to_initial():
        nonlocal current_pieces, solution_path, step_index, selected_square
        if initial_fen is None:
            return
        try:
            pieces = fen_to_pieces(initial_fen)
            current_pieces = [p.clone() for p in pieces]
            solution_path = []
            step_index = 0
            selected_square = None
        except Exception:
            pass

    def load_by_global_index(idx):
        """Global index 1–2400: 1–800 Ranger, 801–1600 Melee, 1601–2400 Solo."""
        nonlocal current_fen_number
        n_r = len(ranger_rows)
        n_m = len(melee_rows)
        n_s = len(solo_rows)
        total = n_r + n_m + n_s
        if idx < 1 or idx > total:
            return False
        if idx <= n_r:
            current_fen_number = idx - 1
            return set_position_from_fen("ranger", ranger_rows[idx - 1][0])
        if idx <= n_r + n_m:
            current_fen_number = idx - n_r - 1
            return set_position_from_fen("melee", melee_rows[idx - 1 - n_r][0])
        current_fen_number = idx - n_r - n_m - 1
        return set_position_from_fen("solo", solo_rows[idx - 1 - n_r - n_m][0])

    # Initialize with first Ranger board if available
    if ranger_rows and initial_fen is None:
        set_position_from_fen("ranger", ranger_rows[0][0])

    running = True
    while running:
        y_buttons = MARGIN + TITLE_H + BOARD_SIZE + 8
        bw = 120
        gap = 8

        # Row 1: "New random or Ranger / Melee / Solo"
        row1_y = y_buttons
        x = MARGIN
        buttons = {}
        buttons["New random"] = pygame.Rect(x, row1_y, bw, BUTTON_H)
        x += bw + gap
        # "or" text will be drawn between New random and mode buttons
        or_pos = (x, row1_y + BUTTON_H // 2)
        x += 20  # space for "or"
        buttons["Ranger"] = pygame.Rect(x, row1_y, 80, BUTTON_H)
        x += 80 + gap
        buttons["Melee"] = pygame.Rect(x, row1_y, 80, BUTTON_H)
        x += 80 + gap
        buttons["Solo"] = pygame.Rect(x, row1_y, 80, BUTTON_H)

        # Row 2: FEN input + solve / navigation
        row2_y = row1_y + BUTTON_H + 10
        x2 = MARGIN
        fen_input_rect = pygame.Rect(x2 + 156, row2_y, 60, BUTTON_H)
        
        # Row 3: Solve DFS / A* / Reset / Prev / Next
        row3_y = row2_y + BUTTON_H + 10
        x3 = MARGIN
        buttons["Solve DFS"] = pygame.Rect(x3, row3_y, bw, BUTTON_H)
        x3 += bw + gap
        buttons["Solve A*"] = pygame.Rect(x3, row3_y, bw, BUTTON_H)
        x3 += bw + gap
        buttons["Reset"] = pygame.Rect(x3, row3_y, 70, BUTTON_H)
        x3 += 70 + gap
        buttons["Prev"] = pygame.Rect(x3, row3_y, 60, BUTTON_H)
        x3 += 60 + gap
        buttons["Next"] = pygame.Rect(x3, row3_y, 60, BUTTON_H)

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
            if event.type == pygame.KEYDOWN:
                # Prev/Next via arrow keys and A/D
                if event.key in (pygame.K_LEFT, pygame.K_a) and solution_path:
                    step_index = max(0, step_index - 1)
                elif event.key in (pygame.K_RIGHT, pygame.K_d) and solution_path:
                    step_index = min(len(solution_path) - 1, step_index + 1)
                # FEN index input when active
                if fen_input_active:
                    if event.key == pygame.K_RETURN:
                        if fen_input_text.isdigit():
                            idx = int(fen_input_text)
                            load_by_global_index(idx)
                        fen_input_text = ""
                    elif event.key == pygame.K_BACKSPACE:
                        fen_input_text = fen_input_text[:-1]
                    elif event.unicode.isdigit() and len(fen_input_text) < 4:
                        fen_input_text += event.unicode
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                # Check buttons
                hit_button = False
                for name, rect in buttons.items():
                    if rect.collidepoint(event.pos):
                        hit_button = True
                        if name == "New random":
                            load_random_any()
                        elif name == "Ranger":
                            load_random_mode("ranger")
                        elif name == "Melee":
                            load_random_mode("melee")
                        elif name == "Solo":
                            load_random_mode("solo")
                        elif name == "Solve DFS" and initial_fen:
                            try:
                                pieces = fen_to_pieces(initial_fen)
                                state = BoardState(pieces)
                                if current_mode == "ranger":
                                    solution_path = ranger_solver.solve_dfs(state)
                                elif current_mode == "melee":
                                    solution_path = melee_solver.solve_dfs(state)
                                else:
                                    solution_path = solo_solver.solve_dfs(state)
                                step_index = 0
                            except Exception:
                                solution_path = []
                        elif name == "Solve A*" and initial_fen:
                            try:
                                pieces = fen_to_pieces(initial_fen)
                                state = BoardState(pieces)
                                if current_mode == "ranger":
                                    solution_path = ranger_solver.solve_astar(state)
                                elif current_mode == "melee":
                                    solution_path = melee_solver.solve_astar(state)
                                else:
                                    solution_path = solo_solver.solve_astar(state)
                                step_index = 0
                            except Exception:
                                solution_path = []
                        elif name == "Reset":
                            reset_to_initial()
                        elif name == "Prev" and solution_path:
                            step_index = max(0, step_index - 1)
                        elif name == "Next" and solution_path:
                            step_index = min(len(solution_path) - 1, step_index + 1)
                        break
                # FEN input focus
                if fen_input_rect.collidepoint(event.pos):
                    fen_input_active = True
                else:
                    if hit_button:
                        fen_input_active = False
                if hit_button:
                    continue
                # Board click (only when no solution showing = play mode) — Ranger mode only
                if not solution_path and current_pieces and current_mode == "ranger":
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
                                child = find_move_child_ranger(state, fr, fc, r, c)
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
        # print(fen_to_show)
        draw_board(screen, piece_font, fen_to_show, highlight)
        draw_move_list(screen, ui_font, solution_path, step_index)
        draw_ui(screen, ui_font, buttons, step_index, total_steps, move_text, current_mode, current_fen_number)

        # Draw "or" between New random and mode buttons (row 1)
        or_label = ui_font.render("or", True, BLACK)
        screen.blit(or_label, or_pos)

        # Draw FEN index input box (row 2)
        label = ui_font.render("FEN number (1 - 2400):", True, BLACK)
        screen.blit(label, (fen_input_rect.x - 156, fen_input_rect.y + 9))
        label2 = ui_font.render("(each mode has 800 puzzles from 4 to 11p)", True, BLACK)
        screen.blit(label2, (fen_input_rect.x + 65, fen_input_rect.y + 9))
        color = BUTTON_HOVER if fen_input_active else BUTTON_BG
        pygame.draw.rect(screen, color, fen_input_rect)
        pygame.draw.rect(screen, BLACK, fen_input_rect, 1)
        txt = fen_input_text or ""
        text_surf = ui_font.render(txt, True, WHITE)
        text_rect = text_surf.get_rect(center=fen_input_rect.center)
        screen.blit(text_surf, text_rect)

        pygame.display.flip()
        clock.tick(60)

    pygame.quit()


if __name__ == "__main__":
    main()
