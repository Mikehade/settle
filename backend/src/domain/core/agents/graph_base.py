"""
Base graph agent (LangGraph).

A thin base for agents whose reasoning is a fixed, legible chain of
steps. The subclass supplies an ordered list of named async node
functions (each takes the working state dict and returns a partial
update); this base wires them into a LangGraph `StateGraph`, compiles it
once, and exposes `astream_nodes()` which yields `(node_name, state)`
after every node so the caller can turn each completed step into a
streamed UI event.

LangGraph is imported lazily inside `_compile()`, and if it is not
installed the base falls back to running the same nodes sequentially in
Python — so the engine works either way and the import never breaks a
project that hasn't added langgraph yet.
"""
from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator, Awaitable, Callable
from typing import Any

from src.shared.logging import get_logger

logger = get_logger(__name__)

Node = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


class BaseGraphAgent(ABC):
    def __init__(self, **kwargs: Any) -> None:
        self._compiled: Any = None
        self._use_langgraph: bool = True

    @abstractmethod
    def nodes(self) -> list[tuple[str, Node]]:
        """Ordered (name, async node fn). Each returns a partial state update."""
        ...

    def _compile(self) -> None:
        if self._compiled is not None:
            return
        try:
            from langgraph.graph import END, START, StateGraph

            graph = StateGraph(dict)
            steps = self.nodes()
            for name, fn in steps:
                graph.add_node(name, self._wrap(fn))
            graph.add_edge(START, steps[0][0])
            for (name, _), (nxt, _) in zip(steps, steps[1:], strict=False):
                graph.add_edge(name, nxt)
            graph.add_edge(steps[-1][0], END)
            self._compiled = graph.compile()
            self._use_langgraph = True
            logger.info("Graph compiled (langgraph)", extra={"event": "graph.compiled", "nodes": [n for n, _ in steps]})
        except Exception as e:  # noqa: BLE001  (ImportError or API drift)
            logger.warning("langgraph unavailable — sequential fallback", extra={"event": "graph.fallback", "error": str(e)})
            self._use_langgraph = False
            self._compiled = None

    @staticmethod
    def _wrap(fn: Node) -> Node:
        async def _node(state: dict[str, Any]) -> dict[str, Any]:
            update = await fn(state)
            return {**state, **(update or {})}
        return _node

    async def astream_nodes(self, initial_state: dict[str, Any]) -> AsyncGenerator[tuple[str, dict[str, Any]], None]:
        """Yield (node_name, full_state) after each node completes."""
        self._compile()
        if self._use_langgraph and self._compiled is not None:
            async for chunk in self._compiled.astream(initial_state, stream_mode="updates"):
                for node_name, update in chunk.items():
                    initial_state = {**initial_state, **(update or {})}
                    yield node_name, initial_state
            return
        # Sequential fallback — identical step semantics without langgraph.
        state = dict(initial_state)
        for name, fn in self.nodes():
            update = await fn(state)
            state = {**state, **(update or {})}
            yield name, state
