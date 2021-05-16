"""Database tools.
"""

import io
from typing import Sequence, Mapping, List, Any, Optional, Union, IO


try:
    from typing import Protocol
except ImportError:
    Protocol = object   # type: ignore

RowType = Sequence[Any]


class Cursor(Protocol):
    def execute(self, sql: str, params: Optional[Union[Sequence[Any], Mapping[str, Any]]] = None) -> None: ...
    def fetchall(self) -> List[RowType]: ...
    def fetchone(self) -> RowType: ...
    def copy_from(self, buf: IO[str], hdr: str) -> None: ...
    def copy_expert(self, sql: str, f: Union[IO[str], io.TextIOBase]) -> None: ...


class Connection(Protocol):
    def cursor(self) -> Cursor: ...


class Runnable(Protocol):
    def run(self) -> None: ...


class HasFileno(Protocol):
    def fileno(self) -> int: ...


FileDescriptor = int
FileDescriptorLike = Union[int, HasFileno]

