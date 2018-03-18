#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# This script is a solver for the well-known game "Lights Out".
# https://en.wikipedia.org/wiki/Lights_Out_(game)
#
# Lights Out is a puzzle game that is present in Heroes of Hammerwatch.
# In Hammerwatch, the puzzle is solved when all lights are on. In this
# script, the game is referred to as "Lights On".
#
# Given the current puzzle, this script returns the solution requiring
# the fewest number of steps.

import sys
from typing import Generator, List, Optional, Tuple


Coordinates = Tuple[int, int]
CoordinatesList = List[Coordinates]


class NoSolutionError:
    """
    Error raised when there is no solution for a given Lights On board.
    """


class BoardState:
    """
    Represents the state of the game board. The convention for selecting
    coordinates is as follows:

        (0, 0)   (1, 0)   (2, 0)
        (0, 1)   (1, 1)   (2, 1)
        (0, 2)   (1, 2)   (2, 2)
    """
    def __init__(self, width: int, height: int) -> None:
        self.width = width
        self.height = height

        #: How many steps this BoardState is from being solved. If that value has
        #: not yet been computed, this is ``None``.
        self.steps_from_solution: int = None

        #: The coordinate that must be clicked to get to the next_solution_board.
        #: If the value has not yet been computed, this is ``None``.
        self.next_solution_coordinates: Coordinates = None

        #: The next BoardState object that we have computed in our solution chain.
        #: Moving to this BoardState gets us closer to solving the lights on problem.
        #: If this value has not yet been computed, this is ``None``.
        self.next_solution_board: "BoardState" = None

        #: The board is represented by a binary-encoded integer. The least-significant
        #: bit is the cell at (0, 0). The next most significant bit is the cell at
        #: (0, 1), then (0, 2), (1, 0), and so on.
        self._board: int = 0

    def __eq__(self, other):
        return all([
            self._board == getattr(other, "_board", None),
            self.width == getattr(other, "width", None),
            self.height == getattr(other, "height", None),
        ])

    def __hash__(self):
        return self._board

    @classmethod
    def solution_board(cls, width: int, height: int) -> "BoardState":
        """
        Produces a BoardState with all lights on.
        """
        bs = BoardState(width, height)
        bs._board = int("0b" + ("1" * width * height), base=2)
        bs.steps_from_solution = 0
        bs.next_solution_coordinates = None
        bs.next_solution_board = None
        return bs

    def _coordinates_bit(self, coordinates: Coordinates) -> int:
        """
        Calculates the relevant bit for the _board parameter given coordinates.
        """
        x, y = coordinates
        return 1 << ((self.width * y) + x)

    def _invert_mask(self, coordinates_list: CoordinatesList) -> int:
        """
        Produces a bitmask suitable for inverting coordinates in the given ``coordinates_list``.
        """
        mask: int = 0
        for coordinates in coordinates_list:
            x, y = coordinates
            bit = self._coordinates_bit(coordinates)
            mask |= bit
        return mask

    def coordinates(self) -> Generator[Coordinates, None, None]:
        """
        Generator that yields all valid coordinates for this BoardState.
        """
        for x in range(self.width):
            for y in range(self.height):
                yield (x, y)

    def invert(self, coordinates_list: CoordinatesList) -> "BoardState":
        """
        Inverts the cells at the given ``coordinates_list``, returning a new BoardState.

        This method *does not toggle adjacent cells according to Lights Out rules* - see
        the BoardClicker for that.
        """
        bs = type(self)(self.width, self.height)
        bs._board = self._board
        invert_mask = self._invert_mask(coordinates_list)
        bs._board ^= invert_mask
        return bs

    def is_set(self, coordinates: Coordinates) -> bool:
        """
        Returns ``True`` if the coordinates are on, ``False`` otherwise.
        """
        bit = self._coordinates_bit(coordinates)
        return bool(self._board & bit)

    @property
    def key(self) -> str:
        """
        Returns a string suitable for use as a unique identifier of this BoardState.
        """
        return f"{self.width}:{self.height}:{self._board}"

    def valid_coordinates(self, coordinates: Coordinates) -> bool:
        """
        Returns ``True`` if the given ``coordinates`` are valid, ``False`` otherwise.
        """
        x, y = coordinates
        return (0 <= x < self.width) and (0 <= y < self.height)


class BoardClicker:
    """
    "Clicks" the cells on the board to produce a new BoardState.
    """
    def click(self, board_state: BoardState, coordinates: Coordinates) -> BoardState:
        """
        Clicks at ``coordinates``, producing the next BoardState consistent with the
        rules of Lights Out.
        """
        x, y = coordinates
        invert_coordinates = list(filter(
            lambda c: board_state.valid_coordinates(c),
            [(x - 1, y), (x, y), (x + 1, y), (x, y - 1), (x, y + 1)]
        ))
        return board_state.invert(invert_coordinates)


class BoardStateTextRenderer:
    """
    Renders BoardState objects in text.
    """
    def _determine_cell_characters(self, board_state: BoardState) -> dict:
        cell_characters = dict()
        nsc = board_state.next_solution_coordinates
        if nsc is not None and board_state.is_set(nsc):
            char = "-"
        else:
            char = "+"
        cell_characters[board_state.next_solution_coordinates] = char

        for coord in board_state.coordinates():
            if board_state.is_set(coord):
                char = "o"
            else:
                char = " "
            cell_characters.setdefault(coord, char)
        return cell_characters

    def render(self, board_state: BoardState) -> str:
        """
        Renders the BoardState in text. Each cell is represented by square brackets
        with a character between them. The representations are given below:

            [ ] = cell is off
            [o] = cell is on
            [+] = cell is off; the solution requires it to be clicked
            [-] = cell is on; the solution requires it to be clicked
        """
        chars = self._determine_cell_characters(board_state)
        all_rows = list()
        for y in range(board_state.height):
            row = list()
            for x in range(board_state.width):
                c = chars[(x, y)]
                row.append(f"[{c}]")
            all_rows.append(" ".join(row))
        return "\n".join(all_rows)


class LightsOnSolutionAlgorithm:
    """
    Calculates a solution to the lights on problem.
    """
    def __init__(self) -> None:
        self.clicker = BoardClicker()

        #: A dictionary of all boards which have been discovered so far.
        #: This contains boards that are in the processing queue and those
        #: which have already been processed.
        self.discovered_boards = dict()

        #: A queue containing boards that need to be processed.
        self.board_processing_queue = list()

    def _find_board_solution(self, board_state: BoardState) -> Optional[BoardState]:
        existing_solution: BoardState = self.discovered_boards.get(board_state.key, None)
        if existing_solution is not None:
            return existing_solution
        solution_board = BoardState.solution_board(board_state.width, board_state.height)
        if self.discovered_boards.get(solution_board.key, None) is not None:
            # We have already computed all solutions for this size board. The given BoardState
            # is unsolvable.
            return None

        self.board_processing_queue.append(solution_board)

        while len(self.board_processing_queue) > 0:
            current_board = self.board_processing_queue.pop(0)
            self._process_board_state(current_board)

        return self.discovered_boards.get(board_state.key, None)

    def find_solution(self, board_state: BoardState) -> Optional[List[BoardState]]:
        # This gives us the BoardState that we start with. We can walk the BoardState objects
        # to provide a nifty list.
        current_bs = self._find_board_solution(board_state)
        solution_list = list()

        while current_bs is not None:
            solution_list.append(current_bs)
            current_bs = current_bs.next_solution_board
        return solution_list or None

    def _process_board_state(self, board_state: BoardState) -> None:
        for c in board_state.coordinates():
            potential_new_board: BoardState = self.clicker.click(board_state, c)
            potential_new_board.steps_from_solution = board_state.steps_from_solution + 1
            potential_new_board.next_solution_coordinates = c
            potential_new_board.next_solution_board = board_state

            # If this board state has not yet been discovered, record it.
            # Otherwise, only replace it if we have found a better solution (i.e. fewer steps).
            existing_discovered_board = self.discovered_boards.get(potential_new_board.key, None)
            if existing_discovered_board is None:
                self.board_processing_queue.append(potential_new_board)
                self.discovered_boards[potential_new_board.key] = potential_new_board
            elif existing_discovered_board.steps_from_solution > potential_new_board.steps_from_solution:
                self.discovered_boards[potential_new_board.key] = potential_new_board


if __name__ == "__main__":
    bs = BoardState(3, 3)
    # This is an example board:
    # [ ] [o] [ ]
    # [o] [ ] [o]
    # [o] [ ] [ ]
    #
    # TODO: Implement passing board via command line.
    bs._board = 0b001_101_010
    renderer = BoardStateTextRenderer()
    algorithm = LightsOnSolutionAlgorithm()
    solution = algorithm.find_solution(bs)
    if solution:
        print("\n\n".join(renderer.render(b) for b in solution))
    else:
        print("No solution", file=sys.stderr)
