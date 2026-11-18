"""Integration: plan → write JSON/CSV/text → replay equivalence + schema integrity."""

from __future__ import annotations

import csv
import hashlib
import io
import json
from pathlib import Path

import pytest

from cloakmill.domain import EntityKind, NamespaceKeyRef, PolicyAction
from cloakmill.domain.enums import TextOffsetUnit
from cloakmill.domain.locators import FieldPathLocator, TextOffsetLocator
from cloakmill.formats import extract_parts_for_media_type, write_artifact
from cloakmill.identity import (
    AcceptedEntity,
    AcceptedEntityGraph,
    NamespaceKeyMaterial,
    NamespaceScope,
    NamespaceScopedProfileAssigner,
    freeze_mapping,
)
from cloakmill.transforms import (
    ATTRIBUTE_EMAIL,
    ATTRIBUTE_EMPLOYEE_ID,
    WRITER_VERSION,
    PatchRequest,
    ReferentialKeyRewrite,
    UnsafeReplacementError,
    plan_patches,
)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _freeze_two_people():
    scope = NamespaceScope("cust-int", "proj-xform", "rcpt-train")
    key = NamespaceKeyMaterial(
        key_ref=NamespaceKeyRef(
            opaque_id="nkr-int-xform-1",
            namespace_id=scope.namespace_id,
            key_version="nk.v1",
        ),
        key_bytes=b"integration-transform-key!",
    )
    graph = AcceptedEntityGraph(
        opaque_id="graph-int-xform-1",
        graph_version="graph.v1",
        namespace_id=scope.namespace_id,
        entities=(
            AcceptedEntity(
                opaque_id="ent-maya",
                entity_kind=EntityKind.PERSON,
                observation_ids=("obs-maya-email", "obs-maya-emp"),
            ),
            AcceptedEntity(
                opaque_id="ent-jordan",
                entity_kind=EntityKind.PERSON,
                observation_ids=("obs-jordan-email",),
            ),
        ),
    )
    bundle = freeze_mapping(
        NamespaceScopedProfileAssigner().assign(
            graph=graph,
            namespace=scope,
            key_material=key,
            snapshot_version="map.v1",
        )
    )
    return bundle


def test_json_csv_text_replay_preserves_relationships_and_schema(
    tmp_path: Path,
) -> None:
    frozen = _freeze_two_people()
    maya = frozen.profile_for_entity("ent-maya")
    jordan = frozen.profile_for_entity("ent-jordan")
    assert maya.email is not None and maya.employee_id is not None
    assert jordan.email is not None

    json_original = (
        b'{"ticket":{"owner_email":"maya@acme.example",'
        b'"owner_id":"E-AB12CD","watcher_id":"E-AB12CD"},'
        b'"assignee_email":"jordan@acme.example"}\n'
    )
    csv_original = (
        b"owner_email,owner_id,assignee_email\nmaya@acme.example,E-AB12CD,jordan@acme.example\n"
    )
    text_original = b"Contact maya@acme.example about ticket T-1.\n"

    json_art = "art-json-1"
    csv_art = "art-csv-1"
    text_art = "art-text-1"

    # Prove extractors still emit the F04 field-path model.
    json_parts = extract_parts_for_media_type(
        artifact_version_id=json_art,
        media_type="application/json",
        payload=json_original,
    )
    assert json_parts.ok
    csv_parts = extract_parts_for_media_type(
        artifact_version_id=csv_art,
        media_type="text/csv",
        payload=csv_original,
    )
    assert csv_parts.ok

    requests = (
        PatchRequest(
            request_id="json-owner-email",
            artifact_version_id=json_art,
            part_id="part-json-owner-email",
            locator=FieldPathLocator(path=("ticket", "owner_email")),
            action=PolicyAction.REPLACE,
            entity_id="ent-maya",
            attribute_key=ATTRIBUTE_EMAIL,
        ),
        PatchRequest(
            request_id="json-assignee-email",
            artifact_version_id=json_art,
            part_id="part-json-assignee-email",
            locator=FieldPathLocator(path=("assignee_email",)),
            action=PolicyAction.REPLACE,
            entity_id="ent-jordan",
            attribute_key=ATTRIBUTE_EMAIL,
        ),
        PatchRequest(
            request_id="csv-owner-email",
            artifact_version_id=csv_art,
            part_id="part-csv-owner-email",
            locator=FieldPathLocator(path=("rows", 0, "owner_email")),
            action=PolicyAction.REPLACE,
            entity_id="ent-maya",
            attribute_key=ATTRIBUTE_EMAIL,
        ),
        PatchRequest(
            request_id="csv-assignee-email",
            artifact_version_id=csv_art,
            part_id="part-csv-assignee-email",
            locator=FieldPathLocator(path=("rows", 0, "assignee_email")),
            action=PolicyAction.REPLACE,
            entity_id="ent-jordan",
            attribute_key=ATTRIBUTE_EMAIL,
        ),
        PatchRequest(
            request_id="text-email",
            artifact_version_id=text_art,
            part_id="part-text-body",
            locator=TextOffsetLocator(unit=TextOffsetUnit.CODEPOINTS, start=8, end=24),
            action=PolicyAction.REPLACE,
            entity_id="ent-maya",
            attribute_key=ATTRIBUTE_EMAIL,
        ),
    )
    referential = (
        ReferentialKeyRewrite(
            request_id="json-owner-id",
            artifact_version_id=json_art,
            part_id="part-json-owner-id",
            locator=FieldPathLocator(path=("ticket", "owner_id")),
            entity_id="ent-maya",
            attribute_key=ATTRIBUTE_EMPLOYEE_ID,
        ),
        ReferentialKeyRewrite(
            request_id="json-watcher-id",
            artifact_version_id=json_art,
            part_id="part-json-watcher-id",
            locator=FieldPathLocator(path=("ticket", "watcher_id")),
            entity_id="ent-maya",
            attribute_key=ATTRIBUTE_EMPLOYEE_ID,
        ),
        ReferentialKeyRewrite(
            request_id="csv-owner-id",
            artifact_version_id=csv_art,
            part_id="part-csv-owner-id",
            locator=FieldPathLocator(path=("rows", 0, "owner_id")),
            entity_id="ent-maya",
            attribute_key=ATTRIBUTE_EMPLOYEE_ID,
        ),
    )

    plan_a = plan_patches(
        frozen=frozen,
        requests=requests,
        referential_rewrites=referential,
        writer_version=WRITER_VERSION,
    )
    plan_b = plan_patches(
        frozen=frozen,
        requests=requests,
        referential_rewrites=referential,
        writer_version=WRITER_VERSION,
    )
    assert plan_a.entries == plan_b.entries
    assert dict(plan_a.vault.values) == dict(plan_b.vault.values)
    assert plan_a.writer_version == WRITER_VERSION

    originals = {
        json_art: (json_original, "application/json"),
        csv_art: (csv_original, "text/csv"),
        text_art: (text_original, "text/plain"),
    }
    original_digests = {art: _sha256(payload) for art, (payload, _) in originals.items()}

    # Write to separate paths; keep originals on disk untouched.
    source_dir = tmp_path / "source"
    out_dir = tmp_path / "out"
    source_dir.mkdir()
    out_dir.mkdir()
    source_files = {}
    for art, (payload, _media_type) in originals.items():
        path = source_dir / f"{art}.bin"
        path.write_bytes(payload)
        source_files[art] = path

    written_a = {}
    for art, (payload, media_type) in originals.items():
        result = write_artifact(
            media_type=media_type,
            original_payload=payload,
            artifact_version_id=art,
            plan=plan_a,
        )
        assert not result.excluded
        out_path = out_dir / f"{art}.out"
        out_path.write_bytes(result.payload)
        written_a[art] = result.payload

    written_b = {
        art: write_artifact(
            media_type=media_type,
            original_payload=payload,
            artifact_version_id=art,
            plan=plan_b,
        ).payload
        for art, (payload, media_type) in originals.items()
    }
    assert written_a == written_b

    # Originals untouched on disk and in memory digests.
    for art, path in source_files.items():
        assert _sha256(path.read_bytes()) == original_digests[art]
    for art, (payload, _) in originals.items():
        assert _sha256(payload) == original_digests[art]

    # Normalized JSON content + referential join preserved.
    doc = json.loads(written_a[json_art].decode("utf-8"))
    assert doc["ticket"]["owner_email"] == maya.email
    assert doc["assignee_email"] == jordan.email
    assert doc["ticket"]["owner_id"] == maya.employee_id
    assert doc["ticket"]["watcher_id"] == maya.employee_id
    assert doc["ticket"]["owner_id"] == doc["ticket"]["watcher_id"]

    # Schema integrity: re-extract transformed JSON/CSV; same field paths exist.
    re_json = extract_parts_for_media_type(
        artifact_version_id=json_art,
        media_type="application/json",
        payload=written_a[json_art],
    )
    assert re_json.ok
    original_paths = {
        tuple(part.original_locator.path)  # type: ignore[union-attr]
        for part in json_parts.parts
    }
    rewritten_paths = {
        tuple(part.original_locator.path)  # type: ignore[union-attr]
        for part in re_json.parts
    }
    assert original_paths == rewritten_paths

    rows = list(csv.reader(io.StringIO(written_a[csv_art].decode("utf-8"))))
    assert rows[0] == ["owner_email", "owner_id", "assignee_email"]
    assert rows[1][0] == maya.email
    assert rows[1][1] == maya.employee_id
    assert rows[1][2] == jordan.email
    re_csv = extract_parts_for_media_type(
        artifact_version_id=csv_art,
        media_type="text/csv",
        payload=written_a[csv_art],
    )
    assert re_csv.ok
    assert {tuple(p.original_locator.path) for p in csv_parts.parts} == {  # type: ignore[union-attr]
        tuple(p.original_locator.path)  # type: ignore[union-attr]
        for p in re_csv.parts
    }

    text_out = written_a[text_art].decode("utf-8")
    assert maya.email in text_out
    assert "maya@acme.example" not in text_out
    assert text_out.startswith("Contact ")
    assert text_out.endswith(" about ticket T-1.\n")

    # Opaque plan artifacts must not embed synthetic cleartext values.
    for entry in plan_a.entries:
        payload = entry.to_dict()
        assert maya.email not in json.dumps(payload)
        assert "maya@acme.example" not in json.dumps(payload)


def test_exclude_artifact_is_not_copied_to_output() -> None:
    frozen = _freeze_two_people()
    plan = plan_patches(
        frozen=frozen,
        requests=(
            PatchRequest(
                request_id="exclude-bin",
                artifact_version_id="art-bin-1",
                part_id="part-unsupported",
                locator=FieldPathLocator(path=("blob",)),
                action=PolicyAction.EXCLUDE,
            ),
        ),
    )
    result = write_artifact(
        media_type="application/json",
        original_payload=b'{"blob":"secret"}\n',
        artifact_version_id="art-bin-1",
        plan=plan,
    )
    assert result.excluded
    assert result.payload == b""


def test_writer_refuses_injected_vault_mutation() -> None:
    frozen = _freeze_two_people()
    plan = plan_patches(
        frozen=frozen,
        requests=(
            PatchRequest(
                request_id="csv-owner-email",
                artifact_version_id="art-csv-1",
                part_id="part-csv-owner-email",
                locator=FieldPathLocator(path=("rows", 0, "owner_email")),
                action=PolicyAction.REPLACE,
                entity_id="ent-maya",
                attribute_key=ATTRIBUTE_EMAIL,
            ),
        ),
    )
    # MappingProxyType vault values are immutable; ensure unsafe strings cannot be staged.
    with pytest.raises((TypeError, AttributeError)):
        plan.vault.values["attr-evil"] = "=1+2"  # type: ignore[index]

    with pytest.raises(UnsafeReplacementError):
        from cloakmill.transforms import build_replacement_vault

        build_replacement_vault({"attr-evil-1": "=CMD('calc')"})
