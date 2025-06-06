from __future__ import annotations

import abc
import operator
from dataclasses import dataclass, field

from .card import CardEffect, EffectExecInfo, Card, CANT_EXEC
from .common import (ResourceFilter, CardTypeFilter, AdjacenciesMappingT,
                     AdjacenciesFrozendictT)
from .enums import *
from ..util import FrozenDict

__all__ = [
    # Basic/atomic effects
    'NullEffect', 'GainResource', 'SpendResource', 'AddMarker', 'RemoveMarker',
    'DiscardThis',
    # Groups / misc. control flow
    '_AnyEffectGroup', 'EffectGroup', 'StrictEffectGroup', 'ConvertEffect',
    'SuppressFail',
    # Conditions
    'ConditionalEffect', 'ICondition', '_ComparisonCond', 'LessThanCond',
    'LessEqCond', 'GreaterThanCond', 'GreaterEqCond', 'EqualsCond',
    'NotEqualsCond', 'MostCardsOfType',
    # ForEach*
    '_EffectManyTimes', 'ForEachMarker', 'ForEachCardOfType', 'ForEachColorSet',
    'ForEachDiscard', 'ForEachPlacedMagic', 'ForEachEmptyColor',
    'ForEachDynChosenColor', 'ForEachM',
    # Measures
    'IMeasure', 'ConstMeasure', 'CardsOfType', 'DiscardedCards', 'NumMarkers',
    'ResourceCount',
    # Special one-off stuff (usually events)
    'ChooseFromDiscardOf', 'ExecOwnPlacedCard', 'ExecChosenColorNTimes',
    'ExecColorsNotBiggest', 'ExecChosenNTimesAndDiscard',
    'MoveChosenAndExecNewColor',
]


# region simple/atomic effects (non-compound)
@dataclass(frozen=True)
class NullEffect(CardEffect):
    def execute(self, info: EffectExecInfo):
        pass


@dataclass(frozen=True)
class GainResource(CardEffect):
    resource: AnyResource
    amount: int

    def execute(self, info: EffectExecInfo):
        info.player.resources[self.resource] += self.amount


@dataclass(frozen=True)
class SpendResource(CardEffect):
    colors: ResourceFilter
    amount: int

    def execute(self, info: EffectExecInfo):
        # Let frontend handle the unambiguous case itself
        spent = info.frontend.get_spend(info, self.colors, self.amount)
        if spent is None:
            return CANT_EXEC
        spent += {}  # Keep only positive values
        assert spent <= info.player.resources  # (Subset)
        assert spent.total() == self.amount
        assert all(map(self.colors.is_allowed, spent))
        info.player.resources -= spent


@dataclass(frozen=True)
class AddMarker(CardEffect):
    amount: int = 1

    def execute(self, info: EffectExecInfo):
        info.card.markers += 1


@dataclass(frozen=True)
class RemoveMarker(CardEffect):
    # Not actually used in the base game but seems like it could make for
    #  interesting gameplay (e.g. managing amount of markers on a card)
    amount: int = 1

    def execute(self, info: EffectExecInfo) -> object | None:
        if info.card.markers < self.amount:
            return CANT_EXEC
        info.card.markers -= self.amount


@dataclass(frozen=True)
class DiscardThis(CardEffect):
    def execute(self, info: EffectExecInfo):
        info.card.discard(info.game)
# endregion


# region compound effects (Group/Convert)
@dataclass(frozen=True, init=False)
class _AnyEffectGroup(CardEffect, abc.ABC):
    """Stores a group of effects without specifying or mandating any logic.
    Subclass must provide the .execute() method, this only handles the
    attributes/constructor."""

    effects: tuple[CardEffect, ...]

    def __init__(self, *effects: CardEffect):
        object.__setattr__(self, 'effects', effects)


@dataclass(frozen=True, init=False)
class EffectGroup(_AnyEffectGroup):
    """A group of effects that keeps going even if one of the effects fails"""

    def execute(self, info: EffectExecInfo):
        for e in self.effects:
            e.execute(info)


@dataclass(frozen=True, init=False)
class StrictEffectGroup(_AnyEffectGroup):
    """A group of effects that stops if one of the effects fails.
    If an inner StrictEffectGroup fails, the outer one fails too.
    This allows Convert(spend=StrictEffectGroup(...), ...) to work."""

    def execute(self, info: EffectExecInfo):
        for e in self.effects:
            if e.execute(info) is CANT_EXEC:
                return CANT_EXEC


@dataclass(frozen=True, init=False)
class ConvertEffect(EffectGroup):
    """Gives the player the option to spend a resource(negative action) to
    get a positive effect and possibly a side effect. Allow the rest of the
    card execution to continue even if 'spend' action can't be met."""

    def __init__(self, spend: CardEffect, gain: CardEffect, effect: CardEffect = None):
        if effect is None:
            effect = NullEffect()
        super().__init__(spend, gain, effect)

    @property
    def spend(self):
        return self.effects[0]

    @property
    def gain(self):
        return self.effects[1]

    @property
    def effect(self):
        return self.effects[2]

    def execute(self, info: EffectExecInfo):
        if self.spend.execute(info) is CANT_EXEC:
            return  # You don't get the gain effect
        self.gain.execute(info)
        self.effect.execute(info)


@dataclass(frozen=True)
class SuppressFail(CardEffect):
    effect: CardEffect

    def execute(self, info: EffectExecInfo) -> object | None:
        self.effect.execute(info)  # Deliberately not `return`
# endregion


# region Condition
@dataclass(frozen=True)
class ConditionalEffect(CardEffect):
    cond: ICondition
    if_true: CardEffect
    if_false: CardEffect = field(default_factory=NullEffect)

    def execute(self, info: EffectExecInfo):
        if self.cond.evaluate(info):
            return self.if_true.execute(info)
        return self.if_false.execute(info)


class ICondition(abc.ABC):
    @abc.abstractmethod
    def evaluate(self, info: EffectExecInfo) -> bool:
        pass


@dataclass(frozen=True)
class _ComparisonCond(ICondition, abc.ABC):
    left: IMeasure
    right: IMeasure

    @classmethod
    @abc.abstractmethod
    def cmp(cls, a: float, b: float) -> bool:
        pass

    def evaluate(self, info: EffectExecInfo) -> bool:
        return self.cmp(self.left.get(info), self.right.get(info))


@dataclass(frozen=True)
class LessThanCond(_ComparisonCond):
    cmp = operator.lt


@dataclass(frozen=True)
class LessEqCond(_ComparisonCond):
    cmp = operator.le


@dataclass(frozen=True)
class GreaterThanCond(_ComparisonCond):
    cmp = operator.gt


@dataclass(frozen=True)
class GreaterEqCond(_ComparisonCond):
    cmp = operator.gt


@dataclass(frozen=True)
class EqualsCond(_ComparisonCond):
    cmp = operator.eq


@dataclass(frozen=True)
class NotEqualsCond(_ComparisonCond):
    cmp = operator.ne


@dataclass(frozen=True)
class MostCardsOfType(ICondition):
    tp: Area
    include_tie: bool = False

    def evaluate(self, info: EffectExecInfo) -> bool:
        player_cards = info.player.num_cards_of_type(self.tp)
        for p in info.game.players:
            if p == info.player:
                continue  # (Check if other players have more cards)
            n_cards = p.num_cards_of_type(self.tp)
            # false if tie for 1st place
            if n_cards > player_cards:
                return False  # We've been beaten in any case
            if n_cards == player_cards and not self.include_tie:
                return False  # Ties don't count as wins here
        return True
# endregion


# region ForEach*
@dataclass(frozen=True)
class _EffectManyTimes(CardEffect, abc.ABC):
    effect: CardEffect

    @abc.abstractmethod
    def get_times(self, info: EffectExecInfo) -> int:
        ...

    def execute(self, info: EffectExecInfo):
        # No better way - cards may have varying (possibly Turing-complete) side effects.
        for _ in range(self.get_times(info)):
            self.effect.execute(info)


@dataclass(frozen=True)
class ForEachMarker(_EffectManyTimes):
    def get_times(self, info: EffectExecInfo) -> int:
        return info.card.markers


@dataclass(frozen=True)
class ForEachCardOfType(_EffectManyTimes):
    tp: Area

    def get_times(self, info: EffectExecInfo) -> int:
        return info.player.num_cards_of_type(self.tp)


@dataclass(frozen=True)
class ForEachColorSet(_EffectManyTimes):
    def get_times(self, info: EffectExecInfo) -> int:
        return min(info.player.num_cards_of_type(c) for c in Color.members())


@dataclass(frozen=True)
class ForEachDiscard(_EffectManyTimes):
    def get_times(self, info: EffectExecInfo) -> int:
        return info.player.num_cards_of_type(Area.DISCARD)


@dataclass(frozen=True)
class ForEachPlacedMagic(_EffectManyTimes):  # (NOT artifact!)
    def get_times(self, info: EffectExecInfo) -> int:
        return sum(info.player.num_cards_of_type(c) for c in Color.members())


@dataclass(frozen=True)
class ForEachEmptyColor(_EffectManyTimes):
    def get_times(self, info: EffectExecInfo) -> int:
        return len([c for c in Color.members() if info.player.num_cards_of_type(c) == 0])


@dataclass(frozen=True)
class ForEachDynChosenColor(_EffectManyTimes):
    # TODO: maybe filter possible card types - artifacts?!
    def get_times(self, info: EffectExecInfo) -> int:
        c = info.frontend.get_foreach_color(info)
        return info.player.num_cards_of_type(c)


@dataclass(frozen=True)
class ForEachM(_EffectManyTimes):
    measure: IMeasure

    def get_times(self, info: EffectExecInfo) -> int:
        return self.measure.get(info)
# endregion


# region Measure (as in measure theory or whatever)
class IMeasure(abc.ABC):
    @abc.abstractmethod
    def get(self, info: EffectExecInfo) -> float | int:
        pass


@dataclass(frozen=True)
class ConstMeasure(IMeasure):
    value: float | int

    def get(self, info: EffectExecInfo) -> float | int:
        return self.value


@dataclass(frozen=True)
class CardsOfType(IMeasure):
    tp: Area

    def get(self, info: EffectExecInfo) -> float | int:
        return info.player.num_cards_of_type(self.tp)


@dataclass(frozen=True)
class DiscardedCards(IMeasure):
    def get(self, info: EffectExecInfo) -> float | int:
        return info.player.num_cards_of_type(Area.DISCARD)


@dataclass(frozen=True)
class NumMarkers(IMeasure):
    def get(self, info: EffectExecInfo) -> float | int:
        return info.card.markers


@dataclass(frozen=True)
class ResourceCount(IMeasure):
    resource: AnyResource

    def get(self, info: EffectExecInfo) -> float | int:
        return info.player.resources[self.resource]
# endregion


# region special effects (one-off, for specific cards)
@dataclass(frozen=True)
class ChooseFromDiscardOf(CardEffect):
    # player_offset:
    # +1 = to left of (i.e. net player to go)
    # 0 = this player
    # -1 = to right of
    player_offset: int
    filters: CardTypeFilter = None

    def __post_init__(self):
        if self.filters is None:
            # Just the regular 'color' cards as the default
            object.__setattr__(self, 'filters', CardTypeFilter(Color.members()))

    def execute(self, info: EffectExecInfo) -> None:
        target = info.player.nth_next_player(self.player_offset)
        if len(target.discard) == 0:
            return CANT_EXEC
        card: Card = info.frontend.choose_from_discard(info, target, self.filters)
        if card is None:
            return CANT_EXEC
        assert self.filters.is_allowed(card.card_type)
        if card.card_type == CardType.EVENT:
            card.execute(info.player)  # Cannot be placed so sensible default: execute it
            # Don't forget to move it into **OUR** discard
            return card.discard(info.game, info.player)
        return info.player.place_card(card)


@dataclass(frozen=True)
class ExecOwnPlacedCard(CardEffect):
    n_times: int = 1

    def execute(self, info: EffectExecInfo):
        card: Card = info.frontend.choose_card_exec(info, self.n_times, False)
        assert PlaceableCardType.has_instance(card.location.area)
        assert card.location.player == info.player.idx
        for i in range(self.n_times):
            if not card.is_placed():
                return
            card.execute(info.player)


@dataclass(frozen=True)
class ExecChosenColorNTimes(CardEffect):
    amount: int = 2
    evergreen_amount: int = 0  # e, Should really be 0-n but we won't check

    def execute(self, info: EffectExecInfo) -> object | None:
        chosen: Color = info.frontend.choose_color_exec(info, self.amount)
        # Can't execute artifacts, events aren't placed down, so must be color
        assert Color.has_instance(chosen)
        for i in range(self.amount):
            for c in Color.members():
                if c == chosen:
                    info.player.exec_color(c)
                elif i <= self.evergreen_amount - 1:  # First e iterations
                    info.player.exec_color_evergreens(c)


@dataclass(frozen=True)
class ExecColorsNotBiggest(CardEffect):
    do_evergreens: bool = True

    def execute(self, info: EffectExecInfo) -> object | None:
        max_count = 0
        top_colors = []
        for c in Color.members():
            n = info.player.num_cards_of_type(c)
            if n > max_count:
                top_colors = [c]
                max_count = n
            elif n == max_count:
                top_colors.append(c)
        if len(top_colors) <= 1:
            excl_color = top_colors[0]
        else:
            excl_color = info.frontend.choose_excl_color(info, top_colors)
        for c in Color.members():
            if c != excl_color:
                info.player.exec_color(c)
            elif self.do_evergreens:
                info.player.exec_color_evergreens(c)


@dataclass(frozen=True)
class ExecChosenNTimesAndDiscard(CardEffect):
    n: int = 3

    def execute(self, info: EffectExecInfo) -> object | None:
        card = info.frontend.choose_card_exec(info, self.n, True)
        assert card.is_dyn_executable()
        for _ in range(self.n):
            if not card.is_placed():
                return
            card.execute(info.player)
        card.discard(info.game)


@dataclass(frozen=True, init=False)
class MoveChosenAndExecNewColor(CardEffect):
    adjacencies: AdjacenciesFrozendictT | None

    def __init__(self, adjacencies: AdjacenciesMappingT = None):
        if adjacencies is not None:
            adjacencies = FrozenDict(adjacencies)
        object.__setattr__(self, 'adjacencies', adjacencies)

    def execute(self, info: EffectExecInfo) -> object | None:
        # Choose card to move
        if (card := self._choose_card(info)) is None:
            return CANT_EXEC
        if (dest_color := self._get_dest_color(info, card)) is None:
            return CANT_EXEC
        card.append_to(info.game, dest_color)
        # Exec new color
        info.player.exec_color(dest_color)

    def _choose_card(self, info: EffectExecInfo):
        card = info.frontend.choose_card_move(info, self.get_adjacencies(info))
        if card is None:
            return None
        assert not card.is_starting_card
        return card

    def _get_dest_color(self, info: EffectExecInfo, card: Card):
        orig_color = card.location.area
        assert PlaceableCardType.has_instance(orig_color)
        dest_color = info.frontend.choose_move_where(
            info, card, self.get_adjacencies(info).get(orig_color, ()))
        if dest_color is None:
            return None
        assert PlaceableCardType.has_instance(dest_color)
        assert dest_color in self.get_adjacencies(info).get(orig_color, ())
        return dest_color

    def get_adjacencies(self, info: EffectExecInfo):
        return (self.adjacencies if self.adjacencies is not None
                else info.ruleset.get_adjacencies())
# endregion
