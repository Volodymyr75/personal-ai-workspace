from uuid import UUID

from paw.domain.files import Catalog, StoredFile, inspect_csv, validate_name


def upload_csv(
    catalog: Catalog, project_id: UUID, name: str, data: bytes, delimiter: str
) -> StoredFile:
    validate_name(name)
    catalog.get_project(project_id)
    info = inspect_csv(data, delimiter)
    return catalog.save_file(project_id, name, data, info)
