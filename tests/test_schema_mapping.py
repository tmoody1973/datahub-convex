# Copyright 2026 Radio Milwaukee / Liner Notes contributors
# SPDX-License-Identifier: Apache-2.0
"""Schema-mapping unit tests, using a fixture captured from a real
Convex /api/json_schemas response."""

from datahub.metadata.schema_classes import (
    NumberTypeClass,
    RecordTypeClass,
    StringTypeClass,
    UnionTypeClass,
)

from datahub_convex.source import schema_fields_from_json_schema

# Trimmed real response for a `plays` table (rm-playlist-v2).
PLAYS_SCHEMA = {
    "type": "object",
    "properties": {
        "_creationTime": {"type": "number"},
        "_id": {"$description": "Id(plays)", "type": "string"},
        "artistRaw": {"type": "string"},
        "canonicalArtistId": {"$description": "Id(artists)", "type": "string"},
        "playedAt": {"type": "number"},
        "raw": {
            "anyOf": [
                {"type": "string"},
                {
                    "type": "object",
                    "properties": {"StreamTitle": {"type": "string"}},
                    "required": ["StreamTitle"],
                },
            ]
        },
        "nested": {"type": "object", "properties": {"x": {"type": "number"}}},
        "_table": {"type": "string"},
        "_ts": {"type": "integer"},
        "_deleted": {"type": "boolean"},
    },
    "required": ["_creationTime", "_id", "artistRaw", "playedAt"],
}


def test_system_fields_excluded():
    names = {f.fieldPath for f in schema_fields_from_json_schema(PLAYS_SCHEMA)}
    assert names == {
        "_creationTime",
        "_id",
        "artistRaw",
        "canonicalArtistId",
        "playedAt",
        "raw",
        "nested",
    }


def test_type_mapping():
    fields = {f.fieldPath: f for f in schema_fields_from_json_schema(PLAYS_SCHEMA)}
    assert isinstance(fields["artistRaw"].type.type, StringTypeClass)
    assert isinstance(fields["playedAt"].type.type, NumberTypeClass)
    assert isinstance(fields["raw"].type.type, UnionTypeClass)
    assert isinstance(fields["nested"].type.type, RecordTypeClass)
    assert fields["raw"].nativeDataType == "anyOf(string, object)"


def test_reference_descriptions_and_nullability():
    fields = {f.fieldPath: f for f in schema_fields_from_json_schema(PLAYS_SCHEMA)}
    assert fields["canonicalArtistId"].description == "Id(artists)"
    assert fields["canonicalArtistId"].nullable is True  # not in required
    assert fields["artistRaw"].nullable is False
