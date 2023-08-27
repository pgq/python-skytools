"""Database tools.
"""

import abc
import io
import typing
import types

from typing import (
    IO, Any, Mapping, Optional, Sequence, Tuple, Type, Union,
    KeysView, ValuesView, ItemsView, Iterator,
)

try:
    from typing import Protocol
except ImportError:
    Protocol = object   # type: ignore

__all__ = (
    "ExecuteParams", "DictRow",
    "Cursor", "Connection",
    "Runnable",
    "HasFileno", "FileDescriptor", "FileDescriptorLike",
    "Buffer",
)

ExecuteParams = Union[Sequence[Any], Mapping[str, Any]]


class DictRow(Protocol):
    """Allow both key and index-based access.

    Both Psycopg2 DictRow and PL/Python rows support this.
    """
    def keys(self) -> KeysView[str]: raise NotImplementedError
    def values(self) -> ValuesView[Any]: raise NotImplementedError
    def items(self) -> ItemsView[str, Any]: raise NotImplementedError
    def get(self, key: str, default: Any = None) -> Any: raise NotImplementedError
    def __getitem__(self, key: Union[str, int]) -> Any: raise NotImplementedError
    def __iter__(self) -> Iterator[str]: raise NotImplementedError
    def __len__(self) -> int: raise NotImplementedError
    def __contains__(self, key: object) -> bool: raise NotImplementedError


class Cursor(Protocol):
    @property
    def rowcount(self) -> int: raise NotImplementedError
    @property
    def statusmessage(self) -> Optional[str]: raise NotImplementedError
    def execute(self, sql: str, params: Optional[ExecuteParams] = None) -> None: raise NotImplementedError
    def fetchall(self) -> Sequence[DictRow]: raise NotImplementedError
    def fetchone(self) -> DictRow: raise NotImplementedError
    def __enter__(self) -> "Cursor": raise NotImplementedError
    def __exit__(self, typ: Optional[Type[BaseException]], exc: Optional[BaseException], tb: Optional[types.TracebackType]) -> None:
        raise NotImplementedError
    def copy_expert(
        self, sql: str,
        f: Union[IO[str], IO[bytes], io.TextIOBase, io.RawIOBase],
        size: int = 8192
    ) -> None:
        raise NotImplementedError
    def fileno(self) -> int: raise NotImplementedError
    @property
    def description(self) -> Sequence[Tuple[str, int, int, int, Optional[int], Optional[int], None]]: raise NotImplementedError
    @property
    def connection(self) -> "Connection": raise NotImplementedError


class Connection(Protocol):
    def cursor(self) -> Cursor: raise NotImplementedError
    def rollback(self) -> None: raise NotImplementedError
    def commit(self) -> None: raise NotImplementedError
    def close(self) -> None: raise NotImplementedError
    @property
    def isolation_level(self) -> int: raise NotImplementedError
    def set_isolation_level(self, level: int) -> None: raise NotImplementedError
    @property
    def encoding(self) -> str: raise NotImplementedError
    def set_client_encoding(self, encoding: str) -> None: raise NotImplementedError
    @property
    def server_version(self) -> int: raise NotImplementedError
    def __enter__(self) -> "Connection": raise NotImplementedError
    def __exit__(self, typ: Optional[Type[BaseException]], exc: Optional[BaseException], tb: Optional[types.TracebackType]) -> None:
        raise NotImplementedError

class Runnable(Protocol):
    def run(self) -> None: raise NotImplementedError


class HasFileno(Protocol):
    def fileno(self) -> int: raise NotImplementedError


FileDescriptor = int
FileDescriptorLike = Union[int, HasFileno]

try:
    from typing_extensions import Buffer
except ImportError:
    if typing.TYPE_CHECKING:
        from _typeshed import Buffer    # type: ignore
    else:
        try:
            from collections.abc import Buffer  # type: ignore
        except ImportError:
            class Buffer(abc.ABC):
                pass
            Buffer.register(memoryview)
            Buffer.register(bytearray)
            Buffer.register(bytes)

