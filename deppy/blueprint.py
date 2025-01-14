from typing import Any, Optional, Iterable, Callable, TypeVar, Type, ParamSpec
from functools import wraps

from .node import Node as DeppyNode
from .deppy import Deppy


T = TypeVar("T")

P = ParamSpec("P")
FT = TypeVar("FT")


class ObjectAccessor:
    def __init__(self, t):
        self.type = t
        self.accesses_methods = []
        self.curr_access = []
        self.name = None
        self.ignore = False

    def __getattr__(self, item):
        if self.ignore:
            if item == "$":
                self.ignore = False
            return self
        if item == "*":
            self.ignore = True
            self.accesses_methods.append(self.curr_access)
            self.curr_access = []
            return self
        self.curr_access.append(item)
        return self


def Object(t: Type[T]) -> T:
    return ObjectAccessor(t)


def wrapper(function: Callable[P, FT]) -> Callable[P, DeppyNode]:
    @wraps(function)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> DeppyNode:
        func = args[0]
        if isinstance(func, ObjectAccessor):
            func.__getattr__("*")
        obj = function(*args, **kwargs)
        if isinstance(func, ObjectAccessor):
            func.__getattr__("$")
        return obj
    return wrapper


Node = wrapper(DeppyNode)


class Output:
    def __init__(self, node: Node, extractor: Optional[Callable[[Any], Any]], loop: Optional[bool] = False, secret: Optional[bool] = None):
        self.node = node
        self.extractor = extractor
        self.loop = loop
        self.secret = secret


class Const:
    def __init__(self, value: Optional[Any] = None):
        self.value = value


class Secret:
    def __init__(self, value: Optional[Any] = None):
        self.value = value


class BlueprintMeta(type):
    def __new__(cls, name, bases, dct):
        nodes = {}
        outputs = {}
        consts = {}
        secrets = {}
        objects = {}
        edges = []

        for attr_name, attr_value in dct.items():
            if isinstance(attr_value, DeppyNode):
                nodes[attr_name] = attr_value
            elif isinstance(attr_value, Const):
                consts[attr_name] = attr_value
            elif isinstance(attr_value, Secret):
                secrets[attr_name] = attr_value
            elif isinstance(attr_value, Output):
                outputs[attr_name] = attr_value
            elif isinstance(attr_value, ObjectAccessor):
                objects[attr_name] = attr_value
                attr_value.name = attr_name
            elif attr_name == "edges" and isinstance(attr_value, Iterable):
                edges = attr_value

        dct["_nodes"] = nodes
        dct["_consts"] = consts
        dct["_secrets"] = secrets
        dct["_edges"] = edges
        dct["_outputs"] = outputs
        dct["_objects"] = objects

        return super().__new__(cls, name, bases, dct)


class Blueprint(Deppy, metaclass=BlueprintMeta):
    def __init__(self, **kwargs):
        super().__init__(name=self.__class__.__name__)

        object_map = {}
        self.bp_to_node_map = {}

        for name, obj in self._objects.items():
            input_ = kwargs.get(name, {})
            if isinstance(input_, dict):
                obj = obj.type(**input_)
            elif isinstance(input_, obj.type):
                obj = input_
            else:
                raise ValueError(f"Invalid input for object {name}")
            object_map[name] = obj
            setattr(self, name, obj)

        for name, node in self._nodes.items():
            if isinstance(node.func, ObjectAccessor):
                obj = object_map[node.func.name]
                accesses = node.func.accesses_methods.pop(0)
                for access in accesses:
                    obj = getattr(obj, access)
                node.func = obj
            node.name = name
            # these are always nodes and not blueprints
            self.bp_to_node_map[node] = node
            self.graph.add_node(node)

        for name, output in self._outputs.items():
            bp = output
            actual_node = self.bp_to_node_map[output.node]
            output = self.add_output(actual_node, name, output.extractor, output.loop, output.secret)
            self.bp_to_node_map[bp] = output
            setattr(self, name, output)

        for name, const in self._consts.items():
            bp = const
            const = self.add_const(const.value or kwargs.get(name), name)
            self.bp_to_node_map[bp] = const
            setattr(self, name, const)

        for name, secret in self._secrets.items():
            bp = secret
            secret = self.add_secret(secret.value or kwargs.get(name), name)
            self.bp_to_node_map[bp] = secret
            setattr(self, name, secret)

        for edge in self._edges:
            assert len(edge) == 3, "Edges must be tuples with min length of 3"

            u = self.bp_to_node_map[edge[0]]
            v = self.bp_to_node_map[edge[1]]

            self.add_edge(u, v, *(edge[2:]))

        async_context_mngr = False
        for obj in object_map.values():
            if hasattr(obj, "__aenter__") and hasattr(obj, "__aexit__"):
                async_context_mngr = True
                break

        if async_context_mngr:
            async def __aenter__(self):
                for obj in object_map.values():
                    if hasattr(obj, "__aenter__"):
                        await obj.__aenter__()
                    else:
                        await obj.__enter__()
                return self

            async def __aexit__(self, exc_type, exc_value, traceback):
                for obj in object_map.values():
                    if hasattr(obj, "__aexit__"):
                        await obj.__aexit__(exc_type, exc_value, traceback)
                    else:
                        await obj.__exit__(exc_type, exc_value, traceback)

            setattr(self.__class__, "__aenter__", __aenter__)
            setattr(self.__class__, "__aexit__", __aexit__)
        else:
            def __enter__(self):
                for obj in object_map.values():
                    if hasattr(obj, "__enter__"):
                        obj.__enter__()
                return self

            def __exit__(self, exc_type, exc_value, traceback):
                for obj in object_map.values():
                    if hasattr(obj, "__exit__"):
                        obj.__exit__(exc_type, exc_value, traceback)

            setattr(self.__class__, "__enter__", __enter__)
            setattr(self.__class__, "__exit__", __exit__)
