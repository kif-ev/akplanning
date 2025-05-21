from pathlib import Path

import referencing.retrieval
from jsonschema import Draft202012Validator
from jsonschema.protocols import Validator
from referencing import Registry

from AKPlanning import settings


def _construct_schema_path(uri: str | Path) -> Path:
    """Construct a schema URI.

    This function also checks for unallowed directory traversals
    out of the 'schema' subfolder.
    """
    schema_base_path = Path(settings.BASE_DIR).resolve()
    uri_path = (schema_base_path / uri).resolve()
    if not uri_path.is_relative_to(schema_base_path / "schemas"):
        raise ValueError("Unallowed dictionary traversal")
    return uri_path


@referencing.retrieval.to_cached_resource()
def retrieve_schema_from_disk(uri: str) -> str:
    """Retrieve schemas from disk by URI."""
    uri_path = _construct_schema_path(uri)
    with uri_path.open("r") as ff:
        return ff.read()


def construct_schema_validator(schema: str | dict) -> Validator:
    """Construct a validator for a JSON schema.

    In particular, all schemas from the 'schemas' directory
    are loaded into the registry.
    """
    registry = Registry(retrieve=retrieve_schema_from_disk)

    if isinstance(schema, str):
        schema_uri = str(Path("schemas") / schema)
        schema = registry.get_or_retrieve(schema_uri).value.contents
    return Draft202012Validator(schema=schema, registry=registry)
