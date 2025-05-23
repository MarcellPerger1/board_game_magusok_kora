from __future__ import annotations

import abc
from collections import Counter
from dataclasses import dataclass, fields
from typing import TYPE_CHECKING

from .common import Location, ResourceFilter
from .enums import CardType, Color, Area

if TYPE_CHECKING:
    from backend_v2.game import Player, Game


# Card types: CardTemplate should have frozen immutable attributes 'printed on
#  the physical card' and Card should have those attributes as frozen
#  but should have other non-frozen attributes. This is mainly po
# This is partially possible but not fully because:
#  - It doesn't let non-frozen dataclasses inherit from frozen ones
#  - It only lets frozen dataclasses inherit non-frozen ones if there's min.
#    1 frozen dataclass in the base classes in 3.11-3.12.
# Therefore, we can create a base _CommonCard class (non-frozen)
#  and have the Card (non-frozen) class inherit from it. Then, also have the
#  CardTemplate (frozen) class inherit from _CommonCard and an empty frozen
#  dataclass. However, in 3.13, they changed it so that for a dataclass to be
#  non-frozen, ALL its base classes must be non-frozen so this doesn't work.
# Therefore, we need a different approach. The main point of `frozen` is hashing
#  support. When I actually think about hashing, the CardTemplate should have
#  the standard 'all fields equal' hashing but for Card, it should be based on
#  id() because you can have 2 identical cards but they should be different
#  keys in a dict.
@dataclass(unsafe_hash=True)
class CardTemplate:  # Frozen-by-convention
    card_type: CardType
    effect: CardEffect
    cost: CardCost
    always_triggers: bool = False
    is_starting_card: bool = False


@dataclass(eq=False)
class Card(CardTemplate):
    location: Location = None
    markers: int = 0

    def detach(self, game: Game):
        """Detach ourself from `self.location`"""
        popped = self.location.clear(game)
        # If we're not at that location, something has gone very, very wrong.
        assert popped is self

    def attach(self, game: Game):
        """Attach to `self.location` in the `Game`"""
        prev = self.location.put(game, self)
        assert prev is None  # Hope we haven't overwritten anything,

    def attach_to(self, game: Game, location: Location):
        self.location = location
        self.attach(game)

    def move(self, game: Game, to: Location):
        self.detach(game)
        self.attach_to(game, to)

    def append_to(self, game: Game, area: Area, player_id: int = None):
        if player_id is None:
            player_id = self.location.player
        player = game.players[player_id]
        self.move(game, Location(player_id, area, player.area_next_key(area)))

    def discard(self, game: Game):
        self.append_to(game, Area.DISCARD)

    def __eq__(self, other):
        return object.__eq__(self, other)  # id()-bsed equality for consistency

    def equals(self, other):
        # Still have the field-based equality available, Java-style
        if type(self) is not type(other):
            # Don't use NotImplemented because Python is a STUPID and
            #  bool(NotImplemented) = TypeError. WTF Python?!!
            return False
        # Pycharm, once again doesn't understand dataclasses
        # noinspection PyTypeChecker
        return all(getattr(self, f.name) == getattr(other, f.name)
                   for f in fields(self))  # Not writing out all the fields

    def __hash__(self):
        return object.__hash__(self)  # id()-based hash


@dataclass
class CardCost:
    possibilities: dict[ResourceFilter, int]

    def matches_exact(self, resources: Counter[Color]):
        """Returns the first ColorFilter it matched"""
        for color_filter, n in self.possibilities.items():
            total_have = sum(resources.values())
            if n != total_have:
                continue  # Need exact
            # Fancy way of getting set of colors w/ amount>0 (`+counter` keeps >0 only)
            colors_have = {*(+resources)}
            if all(map(color_filter.is_allowed, colors_have)):
                return color_filter
        return None


@dataclass
class EffectExecInfo:
    card: Card
    player: Player

    @property
    def game(self):
        return self.player.game

    @property
    def frontend(self):
        return self.game.frontend


class CardEffect(abc.ABC):
    """An interface representing an executable effect of a card. Must be
    hashable to enable hashing of CardTemplate objects. Therefore, it
    must also be immutable. A @dataclass(frozen=True) class is recommended"""

    @abc.abstractmethod
    def execute(self, info: EffectExecInfo):
        ...


class CannotExecute(Exception):
    pass
