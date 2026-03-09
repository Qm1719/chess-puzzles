import heapq
import time
import tracemalloc  # For memory tracking


class Solver:
    def get_solution_path(self, end_state):
        path = []
        current = end_state
        while current:
            path.append(current)
            current = current.parent
        return path[::-1]

    def heuristic(self, state):
        # Base heuristic: Số quân còn lại
        h = len(state.pieces) - 1

        # Tie-breaker: Ưu tiên trạng thái mà các quân cờ nằm gần trung tâm hơn
        # (Giúp A* chọn nước đi "ngon" hơn thay vì duyệt ngang bằng nhau)
        center_bonus = 0
        for p in state.pieces:
            # Tính khoảng cách tới tâm (row 3.5, col 3.5)
            dist_to_center = abs(p.row - 3.5) + abs(p.col - 3.5)
            center_bonus += dist_to_center

        # Chia nhỏ bonus để không ảnh hưởng tới admissible của h chính
        return h + (center_bonus * 0.01)

    def solve_dfs(self, initial_state):
        """Blind Search: Depth First Search"""
        stack = [initial_state]

        print("--- Starting DFS ---")
        nodes_explored = 0

        while stack:
            current_state = stack.pop()
            nodes_explored += 1

            if current_state.is_goal():
                print(f"DFS found solution! Explored {nodes_explored} nodes.")
                return self.get_solution_path(current_state)

            # Sinh các trạng thái con
            successors = current_state.get_legal_moves()
            for child in successors:
                stack.append(child)

        print("DFS failed to find a solution.")
        return None

    def solve_astar(self, initial_state):
        """Heuristic Search: A*"""
        # Priority Queue lưu tuple: (f_score, state)
        # f(n) = g(n) + h(n)
        start_h = self.heuristic(initial_state)
        open_set = [(start_h, initial_state)]

        print("--- Starting A* ---")
        nodes_explored = 0

        while open_set:
            current_f, current_state = heapq.heappop(open_set)
            nodes_explored += 1

            if current_state.is_goal():
                print(f"A* found solution! Explored {nodes_explored} nodes.")
                return self.get_solution_path(current_state)

            successors = current_state.get_legal_moves()
            for child in successors:
                h = self.heuristic(child)
                g = child.g
                f = g + h
                heapq.heappush(open_set, (f, child))

        print("A* failed to find a solution.")
        return None
    # ==========================
    # GENERATOR METHODS FOR GUI
    # ==========================

    def solve_dfs_generator(self, initial_state):
        """Yields (current_state, event_type) for visualization"""
        stack = [initial_state]
        visited_count = 0

        while stack:
            current_state = stack.pop()
            visited_count += 1

            # Yield 'visit' event to update GUI
            yield current_state, 'visit', visited_count

            if current_state.is_goal():
                path = self.get_solution_path(current_state)
                yield path, 'found', visited_count
                return

            successors = current_state.get_legal_moves()
            for child in successors:
                stack.append(child)

        yield None, 'failed', visited_count

    def solve_astar_generator(self, initial_state):
        start_h = self.heuristic(initial_state)
        # Queue stores: (f_score, tie_breaker_id, state)
        # id is used to prevent comparison errors if f_scores are equal
        open_set = [(start_h, id(initial_state), initial_state)]
        visited_count = 0

        while open_set:
            _, _, current_state = heapq.heappop(open_set)
            visited_count += 1

            yield current_state, 'visit', visited_count

            if current_state.is_goal():
                path = self.get_solution_path(current_state)
                yield path, 'found', visited_count
                return

            successors = current_state.get_legal_moves()
            for child in successors:
                h = self.heuristic(child)
                g = child.g
                f = g + h
                heapq.heappush(open_set, (f, id(child), child))

        yield None, 'failed', visited_count

    # ==========================
    # STANDARD METHODS FOR BENCHMARKING
    # ==========================

    def solve_with_metrics(self, initial_state, algorithm='dfs'):
        tracemalloc.start()
        start_time = time.perf_counter()

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
                stack.extend(curr.get_legal_moves())

        elif algorithm == 'astar':
            open_set = [(self.heuristic(initial_state), id(initial_state), initial_state)]
            while open_set:
                _, _, curr = heapq.heappop(open_set)
                nodes_explored += 1
                if curr.is_goal():
                    solution_found = True
                    path_length = len(self.get_solution_path(curr)) - 1
                    break
                for child in curr.get_legal_moves():
                    f = child.g + self.heuristic(child)
                    heapq.heappush(open_set, (f, id(child), child))

        end_time = time.perf_counter()
        current_mem, peak_mem = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        return {
            'algorithm': algorithm,
            'success': solution_found,
            'time_sec': end_time - start_time,
            'memory_peak_mb': peak_mem / (1024 * 1024),
            'nodes_explored': nodes_explored,
            'path_length': path_length
        }