import copy

# Mapping coordinate
COL_MAP = {0: 'a', 1: 'b', 2: 'c', 3: 'd', 4: 'e', 5: 'f', 6: 'g', 7: 'h'}
ROW_MAP = {0: '8', 1: '7', 2: '6', 3: '5', 4: '4', 5: '3', 6: '2', 7: '1'}

# Icons for GUI Visualization
PIECE_ICONS = {
    'Rook': '♜', 'Knight': '♞', 'Bishop': '♝',
    'Queen': '♛', 'King': '♚', 'Pawn': '♟'
}


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
            knight_moves = [(2, 1), (2, -1), (-2, 1), (-2, -1), (1, 2), (1, -2), (-1, 2), (-1, -2)]
            for dr, dc in knight_moves:
                tr, tc = p.row + dr, p.col + dc
                t = self.get_piece_at(tr, tc)
                if t: targets.append(t)
            return targets

        if p.name == 'King':
            king_moves = [(0, 1), (0, -1), (1, 0), (-1, 0), (1, 1), (1, -1), (-1, 1), (-1, -1)]
            for dr, dc in king_moves:
                tr, tc = p.row + dr, p.col + dc
                t = self.get_piece_at(tr, tc)
                if t: targets.append(t)
            return targets

        if p.name == 'Pawn':
            # Assuming Pawn moves "Up" (row index decreases)
            pawn_attacks = [(-1, 1), (-1, -1)]
            for dr, dc in pawn_attacks:
                tr, tc = p.row + dr, p.col + dc
                t = self.get_piece_at(tr, tc)
                if t: targets.append(t)
            return targets

        # Sliding logic
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