import asyncio
from itertools import product
from typing import Any, Tuple, Callable, Iterable, Sequence, Union, Type, Optional

LoopStrategy = Union[Callable[[Sequence[Any]], Iterable[Tuple[Any]]], Type[zip]]


class Node:
    def __init__(
            self,
            func: Callable[..., Any],
            loop_strategy: Optional[LoopStrategy] = product,
            to_thread: Optional[bool] = False,
            team_race: Optional[bool] = True,
            name: Optional[str] = None,
            secret: Optional[bool] = False
    ):
        self.func = func
        self.loop_vars = []
        self.loop_strategy = loop_strategy
        self.to_thread = to_thread
        self.team_race = team_race
        self.name = name or func.__name__
        self.secret = secret

    async def __call__(self, **kwargs):
        if asyncio.iscoroutinefunction(self.func):
            return await self.func(**kwargs)
        elif self.to_thread:
            return await asyncio.to_thread(self.func, **kwargs)
        return self.func(**kwargs)

    def __repr__(self):
        return f"<Node {self.name}>"

    def __str__(self):
        return self.name
