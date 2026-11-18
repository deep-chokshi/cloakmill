"""Unit tests for replacement safety and patch overlap resolution."""

from __future__ import annotations

import pytest

from cloakmill.domain import EntityKind, NamespaceKeyRef, PolicyAction
from cloakmill.domain.enums import TextOffsetUnit
from cloakmill.domain.locators import FieldPathLocator, TextOffsetLocator
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
    ArtifactScope,
    PatchConflictError,
    PatchRequest,
    TransformError,
    UnsafeReplacementError,
    assert_safe_replacement,
    content_digest_sha256,
    plan_patches,
)

UNIT_NAMESPACE_SECRET = b"unit-transform-key!!"


def _frozen_bundle():
    scope = NamespaceScope("cust-t", "proj-t", "rcpt-t")
    key = NamespaceKeyMaterial(
        key_ref=NamespaceKeyRef(
            opaque_id="nkr-t-1",
            namespace_id=scope.namespace_id,
            key_version="nk.v1",
        ),
        key_bytes=UNIT_NAMESPACE_SECRET,
    )
    graph = AcceptedEntityGraph(
        opaque_id="graph-t-1",
        graph_version="graph.v1",
        namespace_id=scope.namespace_id,
        entities=(
            AcceptedEntity(
                opaque_id="ent-maya",
                entity_kind=EntityKind.PERSON,
                observation_ids=("obs-1",),
            ),
        ),
    )
    return freeze_mapping(
        NamespaceScopedProfileAssigner().assign(
            graph=graph,
            namespace=scope,
            key_material=key,
            snapshot_version="map.v1",
        )
    )


def _scope(artifact_id: str, payload: bytes = b"synthetic") -> ArtifactScope:
    return ArtifactScope(
        artifact_version_id=artifact_id,
        content_digest=content_digest_sha256(payload),
    )


def test_safe_replacement_rejects_formula_and_sql() -> None:
    assert_safe_replacement("Casey Alden")
    with pytest.raises(UnsafeReplacementError, match="formula"):
        assert_safe_replacement("=CMD('|calc')")
    with pytest.raises(UnsafeReplacementError, match="forbidden"):
        assert_safe_replacement("1; DROP TABLE users")
    with pytest.raises(UnsafeReplacementError, match="forbidden"):
        assert_safe_replacement("{{constructor.constructor('return this')()}}")
    with pytest.raises(UnsafeReplacementError, match="NUL"):
        assert_safe_replacement("ok\x00bad")
    with pytest.raises(UnsafeReplacementError, match="forbidden"):
        assert_safe_replacement("<img src=x onerror=alert(1)>")
    with pytest.raises(UnsafeReplacementError, match="forbidden"):
        assert_safe_replacement("<svg onload=alert(1)>")
    with pytest.raises(UnsafeReplacementError, match="forbidden"):
        assert_safe_replacement('<iframe src="https://attacker.example/"></iframe>')


def test_planner_prefers_longer_text_span_and_rejects_partial_overlap() -> None:
    frozen = _frozen_bundle()
    scopes = (_scope("art-note-1"),)
    longer = PatchRequest(
        request_id="req-long",
        artifact_version_id="art-note-1",
        part_id="part-body",
        locator=TextOffsetLocator(unit=TextOffsetUnit.CODEPOINTS, start=0, end=20),
        action=PolicyAction.REPLACE,
        entity_id="ent-maya",
        attribute_key=ATTRIBUTE_EMAIL,
    )
    contained = PatchRequest(
        request_id="req-short",
        artifact_version_id="art-note-1",
        part_id="part-body",
        locator=TextOffsetLocator(unit=TextOffsetUnit.CODEPOINTS, start=2, end=8),
        action=PolicyAction.REPLACE,
        entity_id="ent-maya",
        attribute_key=ATTRIBUTE_EMAIL,
    )
    plan = plan_patches(
        frozen=frozen,
        namespace_secret=UNIT_NAMESPACE_SECRET,
        requests=(longer, contained),
        artifact_scopes=scopes,
    )
    assert len(plan.entries) == 1
    assert plan.entries[0].locator == longer.locator

    partial_a = PatchRequest(
        request_id="req-a",
        artifact_version_id="art-note-1",
        part_id="part-body",
        locator=TextOffsetLocator(unit=TextOffsetUnit.CODEPOINTS, start=0, end=10),
        action=PolicyAction.REPLACE,
        entity_id="ent-maya",
        attribute_key=ATTRIBUTE_EMAIL,
    )
    partial_b = PatchRequest(
        request_id="req-b",
        artifact_version_id="art-note-1",
        part_id="part-body",
        locator=TextOffsetLocator(unit=TextOffsetUnit.CODEPOINTS, start=5, end=15),
        action=PolicyAction.REPLACE,
        entity_id="ent-maya",
        attribute_key=ATTRIBUTE_EMAIL,
    )
    with pytest.raises(PatchConflictError, match="partial text-offset overlap"):
        plan_patches(
            frozen=frozen,
            namespace_secret=UNIT_NAMESPACE_SECRET,
            requests=(partial_a, partial_b),
            artifact_scopes=scopes,
        )


def test_planner_rejects_exclude_contained_in_replace_span() -> None:
    """EXCLUDE inside a longer REPLACE must fail closed, not drop exclude intent."""
    frozen = _frozen_bundle()
    scopes = (_scope("art-note-1"),)
    longer = PatchRequest(
        request_id="req-replace-outer",
        artifact_version_id="art-note-1",
        part_id="part-body",
        locator=TextOffsetLocator(unit=TextOffsetUnit.CODEPOINTS, start=0, end=20),
        action=PolicyAction.REPLACE,
        entity_id="ent-maya",
        attribute_key=ATTRIBUTE_EMAIL,
    )
    exclude_inner = PatchRequest(
        request_id="req-exclude-inner",
        artifact_version_id="art-note-1",
        part_id="part-body",
        locator=TextOffsetLocator(unit=TextOffsetUnit.CODEPOINTS, start=5, end=10),
        action=PolicyAction.EXCLUDE,
    )
    with pytest.raises(PatchConflictError, match="contained text-offset patch conflicts"):
        plan_patches(
            frozen=frozen,
            namespace_secret=UNIT_NAMESPACE_SECRET,
            requests=(longer, exclude_inner),
            artifact_scopes=scopes,
        )


def test_planner_rejects_identical_text_span_conflicts() -> None:
    frozen = _frozen_bundle()
    scopes = (_scope("art-note-1"),)
    replace = PatchRequest(
        request_id="req-replace",
        artifact_version_id="art-note-1",
        part_id="part-body",
        locator=TextOffsetLocator(unit=TextOffsetUnit.CODEPOINTS, start=0, end=8),
        action=PolicyAction.REPLACE,
        entity_id="ent-maya",
        attribute_key=ATTRIBUTE_EMAIL,
    )
    remove = PatchRequest(
        request_id="req-remove",
        artifact_version_id="art-note-1",
        part_id="part-body",
        locator=TextOffsetLocator(unit=TextOffsetUnit.CODEPOINTS, start=0, end=8),
        action=PolicyAction.REMOVE,
    )
    with pytest.raises(PatchConflictError, match="conflicting patches for text span"):
        plan_patches(
            frozen=frozen,
            namespace_secret=UNIT_NAMESPACE_SECRET,
            requests=(replace, remove),
            artifact_scopes=scopes,
        )


def test_planner_rejects_conflicting_field_paths() -> None:
    frozen = _frozen_bundle()
    scopes = (_scope("art-json-1"),)
    left = PatchRequest(
        request_id="req-1",
        artifact_version_id="art-json-1",
        part_id="part-email",
        locator=FieldPathLocator(path=("owner", "email")),
        action=PolicyAction.REPLACE,
        entity_id="ent-maya",
        attribute_key=ATTRIBUTE_EMAIL,
    )
    right = PatchRequest(
        request_id="req-2",
        artifact_version_id="art-json-1",
        part_id="part-email",
        locator=FieldPathLocator(path=("owner", "email")),
        action=PolicyAction.REMOVE,
    )
    with pytest.raises(PatchConflictError, match="conflicting patches for field path"):
        plan_patches(
            frozen=frozen,
            namespace_secret=UNIT_NAMESPACE_SECRET,
            requests=(left, right),
            artifact_scopes=scopes,
        )


def test_inert_formula_token_rejected_during_planning() -> None:
    frozen = _frozen_bundle()
    request = PatchRequest(
        request_id="req-inert",
        artifact_version_id="art-note-1",
        part_id="part-body",
        locator=TextOffsetLocator(unit=TextOffsetUnit.CODEPOINTS, start=0, end=4),
        action=PolicyAction.INERT,
        inert_token="=1+1",
    )
    with pytest.raises(UnsafeReplacementError):
        plan_patches(
            frozen=frozen,
            namespace_secret=UNIT_NAMESPACE_SECRET,
            requests=(request,),
            artifact_scopes=(_scope("art-note-1"),),
        )


def test_planner_requires_artifact_scopes_for_requests() -> None:
    frozen = _frozen_bundle()
    request = PatchRequest(
        request_id="req-1",
        artifact_version_id="art-note-1",
        part_id="part-body",
        locator=TextOffsetLocator(unit=TextOffsetUnit.CODEPOINTS, start=0, end=4),
        action=PolicyAction.REMOVE,
    )
    with pytest.raises(TransformError, match="not listed in artifact_scopes"):
        plan_patches(
            frozen=frozen,
            namespace_secret=UNIT_NAMESPACE_SECRET,
            requests=(request,),
            artifact_scopes=(),
        )


def test_planner_rejects_forged_private_integrity_digest() -> None:
    """Structure-valid forged HMAC digests must not plan patches."""
    from dataclasses import replace

    from cloakmill.identity.freeze import FrozenMappingBundle

    frozen = _frozen_bundle()
    forged_snapshot = replace(
        frozen.snapshot,
        private_integrity_digest="hmac-sha256:" + ("ab" * 32),
    )
    forged = FrozenMappingBundle(
        snapshot=forged_snapshot,
        graph_version=frozen.graph_version,
        profiles=frozen.profiles,
    )
    with pytest.raises(TransformError, match="integrity authentication"):
        plan_patches(
            frozen=forged,
            namespace_secret=UNIT_NAMESPACE_SECRET,
            requests=(),
            artifact_scopes=(),
        )
