"""
Parsing, validation and import of room data in CSV format

The import is split into two steps: :func:`parse_rooms_csv` checks the data without changing the database and
returns a :class:`RoomImportResult` that can be shown as preview,
:func:`import_rooms` then creates all valid rooms of such a result.
"""

import csv
import io
from collections.abc import Sequence
from dataclasses import dataclass, field
from django.apps import apps
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.db import transaction
from django.utils.translation import gettext as _

from AKModel.availability.models import Availability
from AKModel.models import AKRequirement, Event, Room

# Cell values marking that a room fulfills a requirement (compared case-insensitively)
REQUIREMENT_TRUE_VALUES = {"x", "y", "yes", "j", "ja", "1", "true", "wahr", "✓", "✔", "✅"}
# Cell values explicitly marking that a room does not fulfill a requirement (besides an empty cell)
REQUIREMENT_FALSE_VALUES = {"n", "no", "nein", "0", "false", "falsch", "-"}


@dataclass
class ParsedRoom:
    """
    A single valid room parsed from the CSV data
    """
    line: int
    name: str
    location: str
    capacity: int
    url: str = ""
    requirements: list[AKRequirement] = field(default_factory=list)


@dataclass
class RoomImportResult:
    """
    Result of parsing CSV room data

    Errors are tied to a line of the input, rows with errors are not contained in ``rooms``.
    Warnings do not prevent the import of a row.
    """
    rooms: list[ParsedRoom] = field(default_factory=list)
    errors: list[tuple[int, str]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    columns: list[str] = field(default_factory=list)
    virtual_rooms_support: bool = False


def decode_csv_bytes(raw: bytes) -> str:
    """
    Decode an uploaded CSV file

    Uses UTF-8 (with or without byte order mark) and falls back to Windows-1252,
    which is still used by some spreadsheet programs when exporting CSV files

    :param raw: raw file content
    :return: decoded content
    """
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("cp1252", errors="replace")


def detect_delimiter(header_line: str) -> str:
    """
    Detect the delimiter used in the CSV data based on its header line

    Semicolon (the documented delimiter) is preferred, tab and comma are supported as alternatives.
    Delimiters inside quoted column names are ignored.

    :param header_line: first line of the CSV data
    :return: delimiter
    """
    unquoted = "".join(part for i, part in enumerate(header_line.split('"')) if i % 2 == 0)
    for delimiter in (";", "\t", ","):
        if delimiter in unquoted:
            return delimiter
    return ";"


def _cell(raw_row: dict, key: str | None) -> str:
    """
    Get the cleaned content of a cell, missing cells (row shorter than header) are treated as empty
    """
    if key is None:
        return ""
    value = raw_row.get(key)
    return value.strip() if isinstance(value, str) else ""


def _format_validation_error(error: ValidationError) -> str:
    """
    Turn a validation error of a room into a human-readable string
    """
    if not hasattr(error, "error_dict"):
        return " ".join(error.messages)
    parts = []
    for field_name, field_errors in error.message_dict.items():
        messages = " ".join(field_errors)
        if field_name == "__all__":
            parts.append(messages)
        else:
            label = getattr(Room._meta.get_field(field_name), "verbose_name", field_name)
            parts.append(f"{label}: {messages}")
    return " ".join(parts)


@dataclass
class _ColumnMapping:
    """
    Mapping of the columns of the CSV data to room fields and requirements
    """
    fields: dict[str, str] = field(default_factory=dict)
    requirements: list[tuple[str, AKRequirement]] = field(default_factory=list)


def _map_columns(fieldnames: Sequence[str], event: Event, result: RoomImportResult) -> _ColumnMapping:
    """
    Map known fields and requirements to the (possibly differently written) column names of the data

    Unknown columns are reported as warnings in the given result

    :raises ValidationError: if a column appears more than once or there is no name column
    """
    known_fields = ["name", "location", "capacity"] + (["url"] if result.virtual_rooms_support else [])
    requirements_by_name = {r.name.strip().casefold(): r for r in event.akrequirement_set.all()}
    mapping = _ColumnMapping()
    seen_columns = set()
    for column in fieldnames:
        normalized = column.strip().casefold()
        if normalized == "":
            continue
        if normalized in seen_columns:
            raise ValidationError(_("Column '{column}' appears more than once").format(column=column.strip()))
        seen_columns.add(normalized)
        if normalized in known_fields:
            mapping.fields[normalized] = column
        elif normalized in requirements_by_name:
            mapping.requirements.append((column, requirements_by_name[normalized]))
        else:
            result.warnings.append(
                    _("Column '{column}' is neither a room field nor a requirement of this event and will be ignored")
                    .format(column=column.strip()))

    if "name" not in mapping.fields:
        raise ValidationError(_("CSV must contain a name column"))
    result.columns = [c for c in known_fields if c in mapping.fields] + [r.name for _c, r in mapping.requirements]
    return mapping


def _parse_capacity(value: str) -> tuple[int, list[str]]:
    """
    Parse the capacity of a room, empty means unlimited (-1)

    :return: capacity and list of errors
    """
    if value == "":
        return -1, []
    try:
        capacity = int(value)
    except ValueError:
        return -1, [_("Capacity '{capacity}' is not a whole number").format(capacity=value)]
    if capacity < -1:
        return capacity, [_("Capacity must be a positive number or -1 (unlimited)")]
    return capacity, []


def _parse_requirements(raw_row: dict, columns: _ColumnMapping) -> tuple[list[AKRequirement], list[str]]:
    """
    Get the requirements marked as fulfilled in a row

    :return: list of fulfilled requirements and list of errors
    """
    requirements = []
    errors = []
    for column, requirement in columns.requirements:
        value = _cell(raw_row, column)
        if value.casefold() in REQUIREMENT_TRUE_VALUES:
            requirements.append(requirement)
        elif value != "" and value.casefold() not in REQUIREMENT_FALSE_VALUES:
            errors.append(
                    _("Value '{value}' for requirement '{requirement}' not understood, use 'x' or leave empty")
                    .format(value=value, requirement=requirement.name))
    return requirements, errors


def _parse_row(raw_row: dict, line: int, columns: _ColumnMapping, event: Event,
               seen_rooms: set[tuple[str, str]]) -> tuple[ParsedRoom | None, list[str]]:
    """
    Parse and validate a single row of the CSV data

    :param raw_row: row as returned by the CSV reader
    :param line: line of the row in the data
    :param columns: mapping of columns to fields and requirements
    :param event: event the room should be created for
    :param seen_rooms: keys of rooms in previous rows (to detect duplicates), will be updated
    :return: the parsed room (or None if the row contains errors) and the list of errors
    """
    row_errors = []
    name = _cell(raw_row, columns.fields.get("name"))
    location = _cell(raw_row, columns.fields.get("location"))
    url = _cell(raw_row, columns.fields.get("url"))

    if name == "":
        row_errors.append(_("Name must not be empty"))

    capacity, capacity_errors = _parse_capacity(_cell(raw_row, columns.fields.get("capacity")))
    row_errors.extend(capacity_errors)

    if url != "":
        try:
            URLValidator()(url)
        except ValidationError:
            row_errors.append(_("'{url}' is not a valid URL").format(url=url))

    requirements, requirement_errors = _parse_requirements(raw_row, columns)
    row_errors.extend(requirement_errors)

    if name != "":
        # Check for duplicates within the data, comparison is case-insensitive like in most database setups
        key = (name.casefold(), location.casefold())
        if key in seen_rooms:
            row_errors.append(_("Room appears more than once in the data"))
        seen_rooms.add(key)

        # Check model constraints (e.g., maximum lengths, room already existing in the database)
        try:
            Room(name=name, location=location, capacity=capacity, event=event).full_clean()
        except ValidationError as e:
            row_errors.append(_format_validation_error(e))

    if row_errors:
        return None, row_errors
    return ParsedRoom(line=line, name=name, location=location, capacity=capacity, url=url,
                      requirements=requirements), []


def parse_rooms_csv(text: str, event: Event) -> RoomImportResult:
    """
    Parse and validate CSV room data for the given event without changing the database

    :param text: CSV data, first line has to contain the column names
    :param event: event the rooms should be created for
    :return: parsing result containing valid rooms, errors per line and general warnings
    :raises ValidationError: if the data cannot be imported at all (e.g., no name column)
    """
    result = RoomImportResult(virtual_rooms_support=apps.is_installed("AKOnline"))
    text = text.lstrip("\ufeff")
    if not text.strip():
        raise ValidationError(_("No data entered. Please enter data as a file or via text."))

    reader = csv.DictReader(io.StringIO(text), delimiter=detect_delimiter(text.splitlines()[0]))
    columns = _map_columns(reader.fieldnames or [], event, result)

    seen_rooms: set[tuple[str, str]] = set()
    for raw_row in reader:
        line = reader.line_num
        surplus_cells = [v for v in raw_row.pop(None, []) if isinstance(v, str) and v.strip()]
        # Skip completely empty rows (e.g., left over from editing in a spreadsheet program)
        if not surplus_cells and not any(_cell(raw_row, key) for key in raw_row):
            continue
        if surplus_cells:
            result.warnings.append(
                    _("Line {line} contains more cells than there are columns, additional cells will be ignored")
                    .format(line=line))

        room, row_errors = _parse_row(raw_row, line, columns, event, seen_rooms)
        if room is not None:
            result.rooms.append(room)
        result.errors.extend((line, error) for error in row_errors)

    return result


def import_rooms(result: RoomImportResult, event: Event, create_default_availabilities: bool) -> int:
    """
    Create all valid rooms of a parsing result

    The import happens in a single transaction, i.e., either all rooms are created or none

    :param result: result of :func:`parse_rooms_csv`
    :param event: event to create the rooms for
    :param create_default_availabilities: create an availability spanning the whole event for each room?
    :return: number of created rooms
    """
    with transaction.atomic():
        for parsed in result.rooms:
            room = Room.objects.create(name=parsed.name, location=parsed.location, capacity=parsed.capacity,
                                       event=event)
            if result.virtual_rooms_support and parsed.url != "":
                # pylint: disable=import-outside-toplevel
                from AKOnline.models import VirtualRoom
                VirtualRoom.objects.create(room=room, url=parsed.url)
            if create_default_availabilities:
                Availability.with_event_length(event=event, room=room).save()
            room.properties.add(*parsed.requirements)
    return len(result.rooms)
