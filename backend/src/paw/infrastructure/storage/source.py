from uuid import UUID

from paw.domain.analysis import AnalysisFailure
from paw.domain.files import MAX_FILE_BYTES, BlobStore, Catalog, NotFound


class StoredSource:
    def __init__(self, catalog: Catalog, blobs: BlobStore):
        self.catalog = catalog
        self.blobs = blobs

    def read(self, file_id: UUID) -> tuple[bytes, str, str]:
        try:
            metadata = self.catalog.get_file(file_id)
            data = self.blobs.read(file_id, MAX_FILE_BYTES)
        except (OSError, NotFound):
            raise AnalysisFailure("source_unavailable") from None
        return data, metadata.delimiter, metadata.sha256
