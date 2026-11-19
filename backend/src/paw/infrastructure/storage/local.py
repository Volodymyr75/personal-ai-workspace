import os
from pathlib import Path
from uuid import UUID


class LocalBlobStore:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)

    def put(self, file_id: UUID, data: bytes) -> None:
        temporary = self.root / f"{file_id}.part"
        target = self.root / f"{file_id}.csv"
        # All filenames are server-generated UUIDs; original names never reach the filesystem.
        with temporary.open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
        directory = os.open(self.root, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)

    def delete(self, file_id: UUID) -> None:
        (self.root / f"{file_id}.csv").unlink(missing_ok=True)
        (self.root / f"{file_id}.part").unlink(missing_ok=True)

    def ids(self) -> set[UUID]:
        result = set()
        for path in self.root.glob("*.csv"):
            try:
                identity = UUID(path.stem)
            except ValueError:
                continue
            if path.name == f"{identity}.csv":
                result.add(identity)
        return result

    def clear_temporary(self) -> None:
        for path in self.root.glob("*.part"):
            try:
                identity = UUID(path.stem)
            except ValueError:
                continue
            if path.name == f"{identity}.part":
                path.unlink(missing_ok=True)
