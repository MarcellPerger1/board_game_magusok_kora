from __future__ import annotations

from typing import Generic, TypeVar


T = TypeVar('T')
lookup_member = object()


def _is_descriptor_or_func(a: object):
    # Functions also have the descriptor stuff
    return (hasattr(a, '__get__') or
            hasattr(a, '__set__') or
            hasattr(a, '__delete__'))


class ExtendableEnumMeta(type, Generic[T]):
    _name_to_inst_: dict[str, ExtendableEnum[T]]
    _value_to_inst_: dict[T, ExtendableEnum[T]]
    _instances_: set[ExtendableEnum[T]]  # Fast containment check

    def __init__(cls, name: str, bases: tuple[type, ...], ns: dict[str, ...], **kwargs):
        super().__init__(name, bases, ns, **kwargs)
        cls._name_to_inst_ = {}
        for k, v in ns.items():
            if k.startswith('_') and k.endswith('_'):
                continue
            if _is_descriptor_or_func(v):
                continue
            if (inst := cls._value_to_inst_.get(v)) is not None:
                cls._name_to_inst_[k] = inst  # Alias
            else:
                cls._value_to_inst_[v] = cls._name_to_inst_[k] = ExtendableEnum(k, v)
        cls._instances_ = set(cls._name_to_inst_.values())

    def __contains__(self, item):
        if isinstance(item, ExtendableEnum):
            return item in self._instances_
        return item in self._name_to_inst_ or item in self._value_to_inst_

    def __getitem__(self, item):
        if isinstance(item, ExtendableEnum):
            return item
        try:
            return self._name_to_inst_[item]
        except KeyError:
            return self._value_to_inst_[item]

    def __iter__(self):
        yield from self._instances_

    def _copy_attrs(cls):
        cls._name_to_inst_ = cls._name_to_inst_.copy()
        cls._value_to_inst_ = cls._value_to_inst_.copy()
        cls._instances_ = cls._instances_.copy()


class ExtendableEnum(Generic[T], metaclass=ExtendableEnumMeta[T]):
    name: str
    value: T

    _init_ran_: bool = False

    def __new__(cls, name: str, value: T = lookup_member):
        if value is lookup_member:
            return cls[name]
        return super().__new__(cls)

    def __init__(self, name: str, value: T = lookup_member):
        if self._init_ran_:
            return
        self._init_ran_ = True
        self.name = name
        self.value = value

    def __hash__(self):
        return hash((type(self), self.name))

    def __init_subclass__(cls, **kwargs):
        cls._copy_attrs()  # So additions to subclass don't affect base class


class Color(ExtendableEnum):
    PURPLE = 1
    GREEN = 2
    RED = 3
    BLUE = 4
    YELLOW = 5


class CardType(Color):
    ARTIFACT = 6
    EVENT = 7


class MoonPhase(Color):
    LAST_TURN = 8


# TODO: keep track of location of each card?
class Player:
    ...
