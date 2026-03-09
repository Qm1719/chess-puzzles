"""
Fetch a Chess Ranger / Solo Chess board from puzzle-chess.com and return FEN.

Differences from v3: specialize this fetcher for exporting Solo Chess boards into a dedicated
  `solo-chess-boards.fen` file, while keeping the Playwright-based extraction pipeline so the
  new multi-mode solver can load large Solo datasets directly.

Usage:
  pip install playwright
  python -m playwright install chromium   # or: firefox, webkit

  python fetch_puzzle_chess.py "https://www.puzzle-chess.com/solo-chess-4/"
  python fetch_puzzle_chess.py   # uses default 4-piece URL
  BROWSER=firefox python fetch_puzzle_chess.py   # use Firefox instead of Chromium

The site loads the board via JavaScript; we wait for it then extract piece
positions. Chromium is default; use Firefox/WebKit if the site behaves differently.
"""

import argparse
import os
import sys
import time

DEFAULT_DATAFILE = "solo-chess-boards.fen"

# Map Unicode piece symbols (white/black) to FEN letter
SYMBOL_TO_FEN = {
    '\u2654': 'K', '\u2655': 'Q', '\u2656': 'R', '\u2657': 'B', '\u2658': 'N', '\u2659': 'P',  # white
    '\u265a': 'K', '\u265b': 'Q', '\u265c': 'R', '\u265d': 'B', '\u265e': 'N', '\u265f': 'P',  # black
}

# Map common alt/src text to FEN
TEXT_TO_FEN = {
    'king': 'K', 'queen': 'Q', 'rook': 'R', 'bishop': 'B', 'knight': 'N', 'pawn': 'P',
    'k': 'K', 'q': 'Q', 'r': 'R', 'b': 'B', 'n': 'N', 'p': 'P',
}


def _get_task_fen_from_page(page):
    """Puzzle-chess.com embeds FEN in script as var task = '8/8/...'; Return that string or None."""
    script = """
    () => {
        if (typeof task !== 'undefined' && typeof task === 'string' && task.indexOf('/') >= 0)
            return task;
        const scripts = document.querySelectorAll('script');
        for (const s of scripts) {
            const m = (s.textContent || '').match(/var\\s+task\\s*=\\s*['"]([^'"]+)['"]/);
            if (m) return m[1];
        }
        return null;
    }
    """
    try:
        return page.evaluate(script)
    except Exception:
        return None


def _extract_via_js(page):
    """Extract board state by running JS in the page. Returns 8x8 grid (row 0 = rank 8)."""
    script = """
    () => {
        const grid = Array(8).fill(null).map(() => Array(8).fill(''));
        const symbols = {
            '\\u2654':'K','\\u2655':'Q','\\u2656':'R','\\u2657':'B','\\u2658':'N','\\u2659':'P',
            '\\u265a':'K','\\u265b':'Q','\\u265c':'R','\\u265d':'B','\\u265e':'N','\\u265f':'P'
        };
        const textToFen = { king:'K', queen:'Q', rook:'R', bishop:'B', knight:'N', pawn:'P' };

        // Strategy 0: puzzle-chess.com — .board-pieces divs with class icon-wp, icon-wr, etc.; position from style top/left
        const boardPieces = document.querySelector('.board-pieces');
        if (boardPieces) {
            const iconToFen = { wp:'P', wr:'R', wn:'N', wb:'B', wq:'Q', wk:'K', bp:'P', br:'R', bn:'N', bb:'B', bq:'Q', bk:'K' };
            for (const el of boardPieces.querySelectorAll('div[class^="icon-"]')) {
                const cls = (el.className || '').toLowerCase();
                const match = cls.match(/icon-(w[pnrbqk]|b[pnrbqk])/);
                if (!match) continue;
                const fen = iconToFen[match[1]];
                if (!fen) continue;
                const style = el.getAttribute('style') || '';
                const top = parseInt(style.match(/top:\\s*([-\d]+)/)?.[1], 10);
                const left = parseInt(style.match(/left:\\s*([-\d]+)/)?.[1], 10);
                if (isNaN(top) || isNaN(left)) continue;
                const r = Math.round((top - 5) / 30);
                const c = Math.round((left - 5) / 30);
                if (r >= 0 && r < 8 && c >= 0 && c < 8) grid[r][c] = fen;
            }
            let count = 0;
            for (let r = 0; r < 8; r++) for (let c = 0; c < 8; c++) if (grid[r][c]) count++;
            if (count >= 4) return grid;
        }

        // Strategy 1: data-square (e.g. "a8") and piece in child
        let squares = document.querySelectorAll('[data-square]');
        if (squares.length >= 4) {
            for (const el of squares) {
                const sq = el.getAttribute('data-square');
                if (!sq || sq.length < 2) continue;
                const col = sq.charCodeAt(0) - 97;
                const row = 8 - parseInt(sq[1], 10);
                if (row < 0 || row > 7 || col < 0 || col > 7) continue;
                const piece = el.querySelector('img, [class*="piece"], .piece');
                if (piece) {
                    const alt = (piece.alt || piece.src || piece.className || '').toLowerCase();
                    const text = (piece.textContent || '').trim();
                    let fen = symbols[text] || textToFen[alt.split(/[-\\s]/).find(w => textToFen[w])];
                    if (!fen && text.length === 1) fen = symbols[text];
                    if (fen) grid[row][col] = fen;
                }
            }
            return grid;
        }

        // Strategy 2: table tr/td (8x8; row 0 = rank 8)
        const table = document.querySelector('table');
        if (table) {
            const rows = table.querySelectorAll('tr');
            for (let r = 0; r < Math.min(8, rows.length); r++) {
                const cells = rows[r].querySelectorAll('td, th');
                for (let c = 0; c < Math.min(8, cells.length); c++) {
                    const cell = cells[c];
                    const piece = cell.querySelector('img, [class*="piece"], .piece') || cell;
                    const alt = (piece.alt || piece.src || piece.className || '').toLowerCase();
                    const text = (piece.textContent || '').trim();
                    let fen = symbols[text] || textToFen[alt.split(/[-\\s]/).find(w => textToFen[w])];
                    if (!fen && text.length === 1) fen = symbols[text];
                    if (fen) grid[r][c] = fen;
                }
            }
            return grid;
        }

        // Strategy 3: any 64 containers with piece content (unicode or img)
        const all = document.querySelectorAll('[class*="square"], [class*="cell"], [class*="board"] > *');
        if (all.length >= 32) {
            for (const el of all) {
                const text = (el.textContent || '').trim();
                const img = el.querySelector('img');
                let fen = '';
                if (text.length === 1 && symbols[text]) fen = symbols[text];
                else if (img) {
                    const a = (img.alt || img.src || '').toLowerCase();
                    for (const [k, v] of Object.entries(textToFen)) { if (a.includes(k)) { fen = v; break; } }
                }
                if (fen) {
                    const idx = [...all].indexOf(el);
                    const r = Math.floor(idx / 8);
                    const c = idx % 8;
                    if (r < 8 && c < 8) grid[r][c] = fen;
                }
            }
            return grid;
        }

        // Strategy 4: scan entire doc for nodes with a single piece character; infer position from 64-cell container
        const pieceChars = Object.keys(symbols).join('');
        const walk = (root) => {
            const found = [];
            const visit = (el) => {
                const t = (el.textContent || '').trim();
                if (t.length === 1 && pieceChars.includes(t)) {
                    let node = el;
                    while (node && node !== document.body) {
                        const par = node.parentElement;
                        if (par && par.children.length === 64) {
                            const idx = Array.from(par.children).indexOf(node);
                            if (idx >= 0) { found.push({ fen: symbols[t], r: Math.floor(idx/8), c: idx%8 }); return; }
                            const inChild = Array.from(par.children).findIndex(ch => ch.contains(node));
                            if (inChild >= 0) { found.push({ fen: symbols[t], r: Math.floor(inChild/8), c: inChild%8 }); return; }
                        }
                        if (par && par.children.length === 8) {
                            const rowIdx = Array.from(par.children).indexOf(node);
                            if (rowIdx >= 0) {
                                const cell = node.querySelector && node.querySelector('[class*="square"], [class*="cell"], td, th');
                                const colIdx = cell ? Array.from((cell.parentElement || node).children).indexOf(cell) : 0;
                                found.push({ fen: symbols[t], r: rowIdx, c: colIdx >= 0 ? colIdx : 0 });
                                return;
                            }
                        }
                        node = par;
                    }
                    found.push({ fen: symbols[t], r: -1, c: -1 });
                    return;
                }
                for (const ch of el.children || []) visit(ch);
            };
            visit(root);
            return found;
        };
        const boardRoot = document.querySelector('[class*="board"], [id*="board"], [class*="chess"]') || document.body;
        const found = walk(boardRoot);
        if (found.length >= 4) {
            const valid = found.filter(x => x.r >= 0 && x.r < 8 && x.c >= 0 && x.c < 8);
            if (valid.length >= 4) {
                for (const x of valid) grid[x.r][x.c] = x.fen;
                return grid;
            }
            const byOrder = found.filter(x => x.fen);
            for (let i = 0; i < byOrder.length && i < 64; i++) {
                const r = Math.floor(i / 8), c = i % 8;
                if (!grid[r][c]) grid[r][c] = byOrder[i].fen;
            }
            return grid;
        }

        return grid;
    }
    """
    return page.evaluate(script)


def _grid_to_fen(grid):
    """Turn 8x8 grid (row 0 = rank 8) into FEN placement string."""
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


def _fen_piece_count(fen):
    """Count pieces in FEN placement (letters only)."""
    n = 0
    for c in (fen or ""):
        if c.upper() in "KQRBNP":
            n += 1
    return n


def fetch_board_from_page(page, url, wait_sec=2.0):
    """
    Load URL in an existing Playwright page, extract board, return (fen, piece_count).
    Returns (None, 0) on failure. Use this when reusing a browser for many fetches.
    """
    try:
        bust = f"{'&' if '?' in url else '?'}_={int(time.time() * 1000)}"
        page.goto(url + bust, wait_until="domcontentloaded", timeout=20000)
        page.wait_for_timeout(int(wait_sec * 1000))
        # puzzle-chess.com: FEN is in script as var task = '8/8/...'
        task_fen = _get_task_fen_from_page(page)
        if task_fen and "/" in task_fen and _fen_piece_count(task_fen) >= 4:
            return task_fen.strip(), _fen_piece_count(task_fen)
        grid = _extract_via_js(page)
    except Exception as e:
        print(f"Error loading {url}: {e}", file=sys.stderr)
        return None, 0
    piece_count = sum(1 for r in range(8) for c in range(8) if grid[r][c])
    if piece_count == 0 and os.environ.get("DEBUG_FEN"):
        try:
            diag = page.evaluate("""() => {
                const sym = '♔♕♖♗♘♙♚♛♜♝♞♟';
                let withSquare = document.querySelectorAll('[data-square]').length;
                let withPiece = document.querySelectorAll('[class*="piece"], [class*="Piece"]').length;
                let tables = document.querySelectorAll('table').length;
                let withUnicode = 0;
                document.querySelectorAll('*').forEach(el => { if (el.childNodes.length===1 && sym.includes((el.textContent||'').trim())) withUnicode++; });
                let bodyClasses = (document.body.className || '') + ' ' + (document.body.id || '');
                let firstBoard = (document.querySelector('[class*="board"], [id*="board"]') || {}).className || 'none';
                return JSON.stringify({ withSquare, withPiece, tables, withUnicode, bodyClasses: bodyClasses.slice(0,80), boardClass: firstBoard.slice(0,80) });
            }""")
            print(f"DEBUG: {diag}", file=sys.stderr)
        except Exception:
            pass
    if piece_count < 4 or piece_count > 11:
        print(f"Warning: found {piece_count} pieces at {url}", file=sys.stderr)
    return _grid_to_fen(grid), piece_count


def _launch_browser(p, headless=True):
    """Launch browser: use BROWSER env (chromium|firefox|webkit), default chromium."""
    name = (os.environ.get("BROWSER") or "chromium").strip().lower()
    if name == "firefox":
        return p.firefox.launch(headless=headless)
    if name == "webkit":
        return p.webkit.launch(headless=headless)
    return p.chromium.launch(headless=headless)


def fetch_board_from_url(url, wait_sec=4.0):
    """
    Open URL in headless browser, wait for board, extract pieces, return FEN.
    Uses BROWSER env (chromium|firefox|webkit); default chromium.
    Returns (fen, piece_count) or (None, 0) on failure.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Install: pip install playwright && python -m playwright install chromium", file=sys.stderr)
        return None, 0

    with sync_playwright() as p:
        browser = _launch_browser(p)
        page = browser.new_page()
        try:
            fen, piece_count = fetch_board_from_page(page, url, wait_sec)
        finally:
            browser.close()
    return (fen, piece_count) if fen else (None, 0)


BASE_URL = "https://www.puzzle-chess.com/solo-chess-{size}/"


def crawl_boards(per_size=100, out_path=None, wait_sec=4.0, delay_between=1.0):
    """
    Crawl puzzle-chess.com: fetch per_size boards for each of 4–11 pieces (8 sizes).
    Save all FENs to a single file. Returns list of (fen, piece_count).
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Install Playwright: pip install playwright && python -m playwright install chromium", file=sys.stderr)
        return []

    sizes = list(range(4, 12))  # 4..11
    results = []
    delay_ms = int(delay_between * 1000)

    with sync_playwright() as p:
        browser = _launch_browser(p)
        page = browser.new_page()
        try:
            for size in sizes:
                url = BASE_URL.format(size=size)
                for i in range(per_size):
                    try:
                        fen, count = fetch_board_from_page(page, url, wait_sec)
                        if fen and 4 <= count <= 11:
                            results.append((fen, count))
                            print(f"  {len(results)}: {count} pieces (size {size}, fetch {i+1}/{per_size})", file=sys.stderr)
                        else:
                            print(f"  skip (got {count} pieces)", file=sys.stderr)
                    except Exception as e:
                        print(f"  error: {e}", file=sys.stderr)
                    if delay_ms > 0:
                        page.wait_for_timeout(delay_ms)
        finally:
            browser.close()

    if out_path:
        with open(out_path, "w", encoding="utf-8") as f:
            for fen, count in results:
                f.write(f"{fen}\t# {count} pieces\n")
        print(f"Wrote {len(results)} FENs to {out_path}", file=sys.stderr)
    return results


def _append_to_datafile(path, fen, piece_count):
    """Append one FEN line to the data file."""
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"{fen}\t# {piece_count} pieces\n")


def main():
    parser = argparse.ArgumentParser(
        description="Fetch Chess Ranger boards from puzzle-chess.com; print FEN and optionally append to a data file."
    )
    parser.add_argument("url", nargs="?", default="https://www.puzzle-chess.com/solo-chess-4/", help="Page URL to fetch")
    parser.add_argument("-o", "--out", metavar="FILE", default=None,
        help=f"Append FEN to this file (default: {DEFAULT_DATAFILE})")
    parser.add_argument("--no-file", action="store_true", help="Do not write to any data file")
    parser.add_argument("crawl_cmd", nargs="?", help="Use 'crawl' to fetch many boards")
    parser.add_argument("crawl_total", nargs="?", type=int, help="Number of boards to crawl (with crawl)")
    parser.add_argument("crawl_out", nargs="?", help="Output file for crawl (default: same as -o)")
    args, rest = parser.parse_known_args()
    # Handle "crawl [per_size] [out]" — 100 per n-pieces (4..11), one file
    if "crawl" in sys.argv[1:]:
        idx = sys.argv.index("crawl")
        per_size = 100
        out_path = DEFAULT_DATAFILE
        if idx + 1 < len(sys.argv) and sys.argv[idx + 1].isdigit():
            per_size = int(sys.argv[idx + 1])
            if idx + 2 < len(sys.argv):
                out_path = sys.argv[idx + 2]
        elif idx + 1 < len(sys.argv) and not sys.argv[idx + 1].isdigit():
            out_path = sys.argv[idx + 1]
        crawl_boards(per_size=per_size, out_path=out_path)
        return
    url = args.url
    out_path = None if args.no_file else (args.out or DEFAULT_DATAFILE)
    fen, count = fetch_board_from_url(url)
    if fen:
        print(fen)
        print(f"# {count} pieces", file=sys.stderr)
        if out_path:
            _append_to_datafile(out_path, fen, count)
            print(f"Appended to {out_path}", file=sys.stderr)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
