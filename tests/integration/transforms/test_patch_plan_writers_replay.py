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
from cloakmill.formats import (
    EMPTY_KEY_SEGMENT,
    LITERAL_KEY_PREFIX,
    ROOT_SEGMENT,
    extract_csv_parts,
    extract_json_parts,
    extract_jsonl_parts,
    extract_parts_for_media_type,
    write_artifact,
)
from cloakmill.formats.json_writer import write_jsonl_document
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
    ArtifactScope,
    PatchRequest,
    ReferentialKeyRewrite,
    UnsafeReplacementError,
    WriterError,
    content_digest_sha256,
    plan_patches,
)
from cloakmill.transforms.replacements import build_replacement_vault

INT_NAMESPACE_SECRET = b"integration-transform-key!"


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
        key_bytes=INT_NAMESPACE_SECRET,
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


def _scopes_for(originals: dict[str, tuple[bytes, str]]) -> tuple[ArtifactScope, ...]:
    return tuple(
        ArtifactScope(
            artifact_version_id=art,
            content_digest=content_digest_sha256(payload),
        )
        for art, (payload, _media) in originals.items()
    )


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

    originals = {
        json_art: (json_original, "application/json"),
        csv_art: (csv_original, "text/csv"),
        text_art: (text_original, "text/plain"),
    }
    scopes = _scopes_for(originals)

    plan_a = plan_patches(
        frozen=frozen,
        namespace_secret=INT_NAMESPACE_SECRET,
        requests=requests,
        referential_rewrites=referential,
        artifact_scopes=scopes,
        writer_version=WRITER_VERSION,
    )
    plan_b = plan_patches(
        frozen=frozen,
        namespace_secret=INT_NAMESPACE_SECRET,
        requests=requests,
        referential_rewrites=referential,
        artifact_scopes=scopes,
        writer_version=WRITER_VERSION,
    )
    assert plan_a.entries == plan_b.entries
    assert dict(plan_a.vault.values) == dict(plan_b.vault.values)
    assert plan_a.writer_version == WRITER_VERSION

    original_digests = {art: _sha256(payload) for art, (payload, _) in originals.items()}

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

    for art, path in source_files.items():
        assert _sha256(path.read_bytes()) == original_digests[art]
    for art, (payload, _) in originals.items():
        assert _sha256(payload) == original_digests[art]

    doc = json.loads(written_a[json_art].decode("utf-8"))
    assert doc["ticket"]["owner_email"] == maya.email
    assert doc["assignee_email"] == jordan.email
    assert doc["ticket"]["owner_id"] == maya.employee_id
    assert doc["ticket"]["watcher_id"] == maya.employee_id
    assert doc["ticket"]["owner_id"] == doc["ticket"]["watcher_id"]

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

    for entry in plan_a.entries:
        payload = entry.to_dict()
        assert maya.email not in json.dumps(payload)
        assert "maya@acme.example" not in json.dumps(payload)


def test_exclude_artifact_is_not_copied_to_output() -> None:
    frozen = _freeze_two_people()
    payload = b'{"blob":"secret"}\n'
    plan = plan_patches(
        frozen=frozen,
        namespace_secret=INT_NAMESPACE_SECRET,
        requests=(
            PatchRequest(
                request_id="exclude-bin",
                artifact_version_id="art-bin-1",
                part_id="part-unsupported",
                locator=FieldPathLocator(path=("blob",)),
                action=PolicyAction.EXCLUDE,
            ),
        ),
        artifact_scopes=(
            ArtifactScope(
                artifact_version_id="art-bin-1",
                content_digest=content_digest_sha256(payload),
            ),
        ),
    )
    result = write_artifact(
        media_type="application/json",
        original_payload=payload,
        artifact_version_id="art-bin-1",
        plan=plan,
    )
    assert result.excluded
    assert result.payload == b""


def test_write_artifact_default_denies_unscoped_and_digest_mismatch() -> None:
    frozen = _freeze_two_people()
    payload = b'{"owner_email":"maya@acme.example"}\n'
    plan = plan_patches(
        frozen=frozen,
        namespace_secret=INT_NAMESPACE_SECRET,
        requests=(),
        artifact_scopes=(
            ArtifactScope(
                artifact_version_id="art-json-1",
                content_digest=content_digest_sha256(payload),
            ),
        ),
    )
    # Affirmative no-op for scoped artifact.
    ok = write_artifact(
        media_type="application/json",
        original_payload=payload,
        artifact_version_id="art-json-1",
        plan=plan,
    )
    assert not ok.excluded
    assert json.loads(ok.payload.decode("utf-8")) == json.loads(payload.decode("utf-8"))

    with pytest.raises(WriterError, match="not in the patch plan"):
        write_artifact(
            media_type="application/json",
            original_payload=payload,
            artifact_version_id="art-missing",
            plan=plan,
        )
    with pytest.raises(WriterError, match="content digest mismatch"):
        write_artifact(
            media_type="application/json",
            original_payload=b'{"owner_email":"other@acme.example"}\n',
            artifact_version_id="art-json-1",
            plan=plan,
        )


def test_json_root_sentinel_does_not_collide_with_value_key() -> None:
    frozen = _freeze_two_people()
    maya = frozen.profile_for_entity("ent-maya")
    assert maya.email is not None

    # Object with a real top-level "value" key must extract/write as that key.
    object_payload = b'{"value":"maya@acme.example","id":"keep-me"}\n'
    extracted = extract_json_parts(artifact_version_id="art-obj", payload=object_payload)
    assert extracted.parse_error is None
    paths = {tuple(part.original_locator.path) for part in extracted.parts}  # type: ignore[union-attr]
    assert ("value",) in paths
    assert (ROOT_SEGMENT,) not in paths

    plan = plan_patches(
        frozen=frozen,
        namespace_secret=INT_NAMESPACE_SECRET,
        requests=(
            PatchRequest(
                request_id="obj-value",
                artifact_version_id="art-obj",
                part_id="part-value",
                locator=FieldPathLocator(path=("value",)),
                action=PolicyAction.REPLACE,
                entity_id="ent-maya",
                attribute_key=ATTRIBUTE_EMAIL,
            ),
        ),
        artifact_scopes=(
            ArtifactScope(
                artifact_version_id="art-obj",
                content_digest=content_digest_sha256(object_payload),
            ),
        ),
    )
    out = write_artifact(
        media_type="application/json",
        original_payload=object_payload,
        artifact_version_id="art-obj",
        plan=plan,
    ).payload
    doc = json.loads(out.decode("utf-8"))
    assert doc["value"] == maya.email
    assert doc["id"] == "keep-me"

    # Bare string document uses $root and round-trips as a string.
    scalar_payload = b'"maya@acme.example"\n'
    scalar_parts = extract_json_parts(artifact_version_id="art-scalar", payload=scalar_payload)
    assert scalar_parts.parse_error is None
    assert tuple(scalar_parts.parts[0].original_locator.path) == (ROOT_SEGMENT,)  # type: ignore[union-attr]

    # NDJSON object with "value" key must not replace the whole line.
    ndjson_payload = b'{"value":"maya@acme.example","id":1}\n'
    ndjson_parts = extract_jsonl_parts(artifact_version_id="art-nd", payload=ndjson_payload)
    assert ndjson_parts.parse_error is None
    nd_paths = {tuple(part.original_locator.path) for part in ndjson_parts.parts}  # type: ignore[union-attr]
    assert (0, "value") in nd_paths
    assert (0, ROOT_SEGMENT) not in nd_paths

    vault = build_replacement_vault({"attr-test-1": maya.email})
    from cloakmill.domain.mapping import PatchPlanEntry

    patched = write_jsonl_document(
        original_payload=ndjson_payload,
        patches=(
            PatchPlanEntry(
                opaque_id="patch-nd-1",
                mapping_snapshot_id=frozen.snapshot.opaque_id,
                artifact_version_id="art-nd",
                part_id="part-nd-value",
                locator=FieldPathLocator(path=(0, "value")),
                action=PolicyAction.REPLACE,
                entity_id="ent-maya",
                replacement_ref="attr-test-1",
            ),
        ),
        vault=vault,
    )
    line = json.loads(patched.decode("utf-8").splitlines()[0])
    assert line == {"value": maya.email, "id": 1}

    # Bare JSONL scalars (number/bool/null/string) all use (line, $root).
    for raw in (b"12345\n", b"true\n", b"null\n", b'"maya@acme.example"\n'):
        bare_parts = extract_jsonl_parts(artifact_version_id="art-bare", payload=raw)
        assert bare_parts.parse_error is None
        assert len(bare_parts.parts) == 1
        assert tuple(bare_parts.parts[0].original_locator.path) == (0, ROOT_SEGMENT)
        bare_out = write_jsonl_document(
            original_payload=raw,
            patches=(
                PatchPlanEntry(
                    opaque_id="patch-bare-1",
                    mapping_snapshot_id=frozen.snapshot.opaque_id,
                    artifact_version_id="art-bare",
                    part_id=bare_parts.parts[0].opaque_id,
                    locator=FieldPathLocator(path=(0, ROOT_SEGMENT)),
                    action=PolicyAction.REPLACE,
                    entity_id="ent-maya",
                    replacement_ref="attr-test-1",
                ),
            ),
            vault=vault,
        )
        assert json.loads(bare_out.decode("utf-8").splitlines()[0]) == maya.email


def test_non_schema_and_person_keyed_surfaces_fail_closed() -> None:
    # Empty / $-prefixed / email-shaped keys are key-position content F08 cannot rewrite.
    dollar_payload = json.dumps({"": "a", "$empty_key": "b", "ok": "d"}).encode()
    dollar_result = extract_json_parts(artifact_version_id="art-keys", payload=dollar_payload)
    assert dollar_result.parts == ()
    assert dollar_result.parse_error == "UncoveredKeys"

    person_json = b'{"maya@acme.example":{"tickets":12},"jordan@acme.example":{"tickets":3}}\n'
    person_result = extract_json_parts(artifact_version_id="art-person", payload=person_json)
    assert person_result.parts == ()
    assert person_result.parse_error == "UncoveredKeys"

    # Bare usernames / TitleCase names / separator-free IDs are not schema keys.
    username_json = b'{"jsmith":{"tickets":1},"mchen":{"tickets":2},"Maya":1,"E12345":2}\n'
    username_result = extract_json_parts(artifact_version_id="art-users", payload=username_json)
    assert username_result.parts == ()
    assert username_result.parse_error == "UncoveredKeys"

    person_csv = b"maya@acme.example,jordan@acme.example\n1,2\n"
    csv_result = extract_csv_parts(artifact_version_id="art-person-csv", payload=person_csv)
    assert csv_result.parts == ()
    assert csv_result.parse_error == "UncoveredKeys"

    username_csv = b"jsmith,Maya,E12345\n1,2,3\n"
    username_csv_result = extract_csv_parts(
        artifact_version_id="art-user-csv", payload=username_csv
    )
    assert username_csv_result.parts == ()
    assert username_csv_result.parse_error == "UncoveredKeys"

    # Schema-safe keys still round-trip; sentinel constants remain exported for writers.
    assert EMPTY_KEY_SEGMENT.startswith("$")
    assert LITERAL_KEY_PREFIX.startswith("$")
    assert ROOT_SEGMENT.startswith("$")


def test_json_writers_reject_person_keyed_documents() -> None:
    """Writer-side key guard mirrors CSV header checks (extraction ok=False is not enough)."""
    frozen = _freeze_two_people()
    plan = plan_patches(
        frozen=frozen,
        namespace_secret=INT_NAMESPACE_SECRET,
        requests=(),
        artifact_scopes=(
            ArtifactScope(
                artifact_version_id="art-json-keys",
                content_digest=content_digest_sha256(b'{"maya@acme.example":{"salary":120000}}\n'),
            ),
            ArtifactScope(
                artifact_version_id="art-json-users",
                content_digest=content_digest_sha256(b'{"jsmith":{"tickets":1}}\n'),
            ),
            ArtifactScope(
                artifact_version_id="art-jsonl-keys",
                content_digest=content_digest_sha256(b'{"maya@acme.example":{"salary":120000}}\n'),
            ),
        ),
    )

    with pytest.raises(WriterError, match="uncovered key-position content"):
        write_artifact(
            media_type="application/json",
            original_payload=b'{"maya@acme.example":{"salary":120000}}\n',
            artifact_version_id="art-json-keys",
            plan=plan,
        )

    with pytest.raises(WriterError, match="uncovered key-position content"):
        write_artifact(
            media_type="application/json",
            original_payload=b'{"jsmith":{"tickets":1}}\n',
            artifact_version_id="art-json-users",
            plan=plan,
        )

    with pytest.raises(WriterError, match="uncovered key-position content"):
        write_artifact(
            media_type="application/x-ndjson",
            original_payload=b'{"maya@acme.example":{"salary":120000}}\n',
            artifact_version_id="art-jsonl-keys",
            plan=plan,
        )


def test_duplicate_csv_headers_fail_closed() -> None:
    payload = b"email,email\na@acme.example,b@acme.example\n"
    extracted = extract_csv_parts(artifact_version_id="art-dup", payload=payload)
    assert extracted.parts == ()
    assert extracted.parse_error == "InvalidHeader"

    frozen = _freeze_two_people()
    plan = plan_patches(
        frozen=frozen,
        namespace_secret=INT_NAMESPACE_SECRET,
        requests=(
            PatchRequest(
                request_id="dup-email",
                artifact_version_id="art-dup",
                part_id="part-dup",
                locator=FieldPathLocator(path=("rows", 0, "email")),
                action=PolicyAction.REPLACE,
                entity_id="ent-maya",
                attribute_key=ATTRIBUTE_EMAIL,
            ),
        ),
        artifact_scopes=(
            ArtifactScope(
                artifact_version_id="art-dup",
                content_digest=content_digest_sha256(payload),
            ),
        ),
    )
    with pytest.raises(WriterError, match="CSV header is invalid"):
        write_artifact(
            media_type="text/csv",
            original_payload=payload,
            artifact_version_id="art-dup",
            plan=plan,
        )


def test_writer_refuses_injected_vault_mutation() -> None:
    frozen = _freeze_two_people()
    payload = b"owner_email\nmaya@acme.example\n"
    plan = plan_patches(
        frozen=frozen,
        namespace_secret=INT_NAMESPACE_SECRET,
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
        artifact_scopes=(
            ArtifactScope(
                artifact_version_id="art-csv-1",
                content_digest=content_digest_sha256(payload),
            ),
        ),
    )
    with pytest.raises((TypeError, AttributeError)):
        plan.vault.values["attr-evil"] = "=1+2"  # type: ignore[index]

    with pytest.raises(UnsafeReplacementError):
        build_replacement_vault({"attr-evil-1": "=CMD('calc')"})
