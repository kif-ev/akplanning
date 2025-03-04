import json
from pathlib import Path

from jsonschema import Draft202012Validator
from jsonschema.protocols import Validator
from referencing import Registry, Resource

from AKPlanning import settings

def construct_schema_validator(schema: str | dict) -> Validator:
    """Construct a validator for a JSON schema.

    In particular, all schemas from the 'schemas' directory
    are loaded into the registry.
    """
    schema_base_path = Path(settings.BASE_DIR) / "schemas"
    resources = []
    for schema_path in schema_base_path.glob("**/*.schema.json"):
        with schema_path.open("r") as ff:
            res = Resource.from_contents(json.load(ff))
        resources.append((res.id(), res))
    registry = Registry().with_resources(resources)
    if isinstance(schema, str):
        with (schema_base_path / schema).open("r") as ff:
            schema = json.load(ff)
    return Draft202012Validator(
        schema=schema, registry=registry
    )
