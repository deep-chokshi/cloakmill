"""Acceptance: independent validation gates pass clean synthetic and block failures."""

from __future__ import annotations

import json

from cloakmill.domain import EntityKind, NamespaceKeyRef, PolicyAction
from cloakmill.domain.enums import CoverageState, TextOffsetUnit
from cloakmill.domain.locators import FieldPathLocator, TextOffsetLocator
from cloakmill.formats import write_artifact
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
    content_digest_sha256,
    plan_patches,
)
from cloakmill.validation import (
    CODE_COVERAGE_GAP,
    CODE_PRIVACY_CANARY_DETECTED,
    CODE_PRIVACY_RESIDUAL_KNOWN_SOURCE,
    CODE_STRUCTURE_JOIN_MISMATCH,
    CODE_STRUCTURE_REPARSE_FAILED,
    CODE_STRUCTURE_SCHEMA_MISMATCH,
    VALIDATOR_VERSION,
    CandidateArtifact,
    CoverageLedger,
    CoverageSurfaceRef,
    JoinExpectation,
    KnownSourceIdentifier,
    PrivacyContext,
    ReleaseCandidate,
    SchemaExpectation,
    SeededCanary,
    StructureContext,
    ValidationDecision,
    assert_report_has_no_sensitive_leak,
    sensitive_values_for_leak_checks,
    validate_release_candidate,
)


def _freeze_two_people():
    scope = NamespaceScope("cust-val", "proj-val", "rcpt-train")
    key = NamespaceKeyMaterial(
        key_ref=NamespaceKeyRef(
            opaque_id="nkr-val-1",
            namespace_id=scope.namespace_id,
            key_version="nk.v1",
        ),
        key_bytes=b"validation-acceptance-key!",
    )
    graph = AcceptedEntityGraph(
        opaque_id="graph-val-1",
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
    return freeze_mapping(
        NamespaceScopedProfileAssigner().assign(
            graph=graph,
            namespace=scope,
            key_material=key,
            snapshot_version="map.v1",
        )
    )


def _write_clean_candidates(frozen):
    maya = frozen.profile_for_entity("ent-maya")
    jordan = frozen.profile_for_entity("ent-jordan")
    assert maya.email is not None and maya.employee_id is not None
    assert jordan.email is not None

    json_art = "art-json-1"
    csv_art = "art-csv-1"
    text_art = "art-text-1"

    json_original = (
        b'{"ticket":{"owner_email":"maya@acme.example",'
        b'"owner_id":"E-AB12CD","watcher_id":"E-AB12CD"},'
        b'"assignee_email":"jordan@acme.example"}\n'
    )
    csv_original = (
        b"owner_email,owner_id,assignee_email\nmaya@acme.example,E-AB12CD,jordan@acme.example\n"
    )
    text_original = b"Contact maya@acme.example about ticket T-1.\n"

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
            # "Contact " = 8; "maya@acme.example" = 17 codepoints → [8, 25).
            locator=TextOffsetLocator(unit=TextOffsetUnit.CODEPOINTS, start=8, end=25),
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
    scopes = tuple(
        ArtifactScope(
            artifact_version_id=art,
            content_digest=content_digest_sha256(payload),
        )
        for art, (payload, _media) in originals.items()
    )
    plan = plan_patches(
        frozen=frozen,
        requests=requests,
        referential_rewrites=referential,
        artifact_scopes=scopes,
        writer_version=WRITER_VERSION,
    )

    written: dict[str, CandidateArtifact] = {}
    for art, (payload, media_type) in originals.items():
        result = write_artifact(
            media_type=media_type,
            original_payload=payload,
            artifact_version_id=art,
            plan=plan,
        )
        assert not result.excluded
        written[art] = CandidateArtifact(
            artifact_version_id=art,
            media_type=media_type,
            payload=result.payload,
        )
    return written, maya, jordan


def _expected_coverage() -> CoverageLedger:
    return CoverageLedger(
        entries=(
            CoverageSurfaceRef(
                opaque_id="cov-json",
                artifact_version_id="art-json-1",
                surface_key="document",
                state=CoverageState.PROCESSED,
            ),
            CoverageSurfaceRef(
                opaque_id="cov-csv",
                artifact_version_id="art-csv-1",
                surface_key="table",
                state=CoverageState.PROCESSED,
            ),
            CoverageSurfaceRef(
                opaque_id="cov-text",
                artifact_version_id="art-text-1",
                surface_key="body",
                state=CoverageState.PROCESSED,
            ),
        )
    )


def _structure_for_clean(written: dict[str, CandidateArtifact]) -> StructureContext:
    from cloakmill.validation.surfaces import field_paths_for_artifact

    json_paths = field_paths_for_artifact(written["art-json-1"])
    csv_paths = field_paths_for_artifact(written["art-csv-1"])
    return StructureContext(
        schemas=(
            SchemaExpectation(artifact_version_id="art-json-1", field_paths=json_paths),
            SchemaExpectation(artifact_version_id="art-csv-1", field_paths=csv_paths),
        ),
        joins=(
            JoinExpectation(
                opaque_id="join-owner-watcher",
                left_artifact_version_id="art-json-1",
                left_path=("ticket", "owner_id"),
                right_artifact_version_id="art-json-1",
                right_path=("ticket", "watcher_id"),
            ),
            JoinExpectation(
                opaque_id="join-json-csv-owner",
                left_artifact_version_id="art-json-1",
                left_path=("ticket", "owner_id"),
                right_artifact_version_id="art-csv-1",
                right_path=("rows", 0, "owner_id"),
            ),
        ),
    )


def _privacy_for_clean(maya, jordan) -> PrivacyContext:
    return PrivacyContext(
        known_sources=(
            KnownSourceIdentifier(
                opaque_id="ks-maya-email",
                normalized_value="maya@acme.example",
                kind="email_address",
            ),
            KnownSourceIdentifier(
                opaque_id="ks-jordan-email",
                normalized_value="jordan@acme.example",
                kind="email_address",
            ),
            KnownSourceIdentifier(
                opaque_id="ks-maya-emp",
                normalized_value="E-AB12CD",
                kind="employee_id",
            ),
        ),
        canaries=(SeededCanary(opaque_id="canary-1", token="CANARY-TOKEN-7f3a"),),
        allowed_synthetics=frozenset(
            value
            for value in (
                maya.email,
                maya.employee_id,
                maya.account_id,
                jordan.email,
                jordan.employee_id,
                jordan.account_id,
            )
            if value
        ),
    )


def test_clean_synthetic_candidate_passes_all_gates() -> None:
    frozen = _freeze_two_people()
    written, maya, jordan = _write_clean_candidates(frozen)
    privacy = _privacy_for_clean(maya, jordan)
    report = validate_release_candidate(
        candidate=ReleaseCandidate(
            artifacts=tuple(written.values()),
            expected_coverage=_expected_coverage(),
        ),
        privacy=privacy,
        structure=_structure_for_clean(written),
    )
    assert report.decision is ValidationDecision.PASS
    assert report.validator_version == VALIDATOR_VERSION
    assert report.findings == ()
    for gate in report.gates:
        assert gate.decision is ValidationDecision.PASS

    sensitive = sensitive_values_for_leak_checks(
        privacy=privacy,
        extra=("maya@acme.example", "jordan@acme.example", "E-AB12CD", "CANARY-TOKEN-7f3a"),
    )
    assert_report_has_no_sensitive_leak(report, sensitive)
    log_blob = json.dumps(report.to_log_record())
    assert "maya@acme.example" not in log_blob
    assert "E-AB12CD" not in log_blob
    assert "CANARY-TOKEN-7f3a" not in log_blob


def test_seeded_residual_known_source_blocks_privacy_gate() -> None:
    frozen = _freeze_two_people()
    written, maya, jordan = _write_clean_candidates(frozen)
    # Inject a residual source email into the transformed JSON candidate.
    doc = json.loads(written["art-json-1"].payload.decode("utf-8"))
    doc["ticket"]["owner_email"] = "maya@acme.example"
    contaminated = CandidateArtifact(
        artifact_version_id="art-json-1",
        media_type="application/json",
        payload=(json.dumps(doc, separators=(",", ":")) + "\n").encode("utf-8"),
    )
    artifacts = (
        contaminated,
        written["art-csv-1"],
        written["art-text-1"],
    )
    privacy = _privacy_for_clean(maya, jordan)
    report = validate_release_candidate(
        candidate=ReleaseCandidate(
            artifacts=artifacts,
            expected_coverage=_expected_coverage(),
        ),
        privacy=privacy,
        structure=_structure_for_clean(
            {
                "art-json-1": contaminated,
                "art-csv-1": written["art-csv-1"],
                "art-text-1": written["art-text-1"],
            }
        ),
    )
    assert report.decision is ValidationDecision.BLOCK
    privacy_gate = next(gate for gate in report.gates if gate.gate.value == "privacy")
    assert privacy_gate.decision is ValidationDecision.BLOCK
    codes = {finding.code for finding in report.findings}
    assert CODE_PRIVACY_RESIDUAL_KNOWN_SOURCE in codes
    assert_report_has_no_sensitive_leak(
        report,
        sensitive_values_for_leak_checks(privacy=privacy),
    )
    for finding in report.findings:
        assert "maya@acme.example" not in finding.opaque_id
        assert "maya@acme.example" not in finding.detail_ref
        assert "maya@acme.example" not in json.dumps(finding.to_log_record())


def test_seeded_canary_blocks_privacy_gate() -> None:
    frozen = _freeze_two_people()
    written, maya, jordan = _write_clean_candidates(frozen)
    contaminated = CandidateArtifact(
        artifact_version_id="art-text-1",
        media_type="text/plain",
        payload=b"Contact placeholder about CANARY-TOKEN-7f3a ticket.\n",
    )
    privacy = _privacy_for_clean(maya, jordan)
    report = validate_release_candidate(
        candidate=ReleaseCandidate(
            artifacts=(written["art-json-1"], written["art-csv-1"], contaminated),
            expected_coverage=_expected_coverage(),
        ),
        privacy=privacy,
        structure=StructureContext(
            schemas=_structure_for_clean(written).schemas,
            joins=(),
        ),
    )
    assert report.decision is ValidationDecision.BLOCK
    assert CODE_PRIVACY_CANARY_DETECTED in {finding.code for finding in report.findings}
    assert_report_has_no_sensitive_leak(
        report,
        sensitive_values_for_leak_checks(privacy=privacy),
    )


def test_broken_join_blocks_structure_gate() -> None:
    frozen = _freeze_two_people()
    written, maya, jordan = _write_clean_candidates(frozen)
    doc = json.loads(written["art-json-1"].payload.decode("utf-8"))
    doc["ticket"]["watcher_id"] = "E-BROKEN1"
    broken = CandidateArtifact(
        artifact_version_id="art-json-1",
        media_type="application/json",
        payload=(json.dumps(doc, separators=(",", ":")) + "\n").encode("utf-8"),
    )
    # Allow the broken employee-looking id so privacy does not preempt structure.
    privacy = PrivacyContext(
        known_sources=_privacy_for_clean(maya, jordan).known_sources,
        canaries=_privacy_for_clean(maya, jordan).canaries,
        allowed_synthetics=_privacy_for_clean(maya, jordan).allowed_synthetics
        | frozenset({"E-BROKEN1"}),
    )
    report = validate_release_candidate(
        candidate=ReleaseCandidate(
            artifacts=(broken, written["art-csv-1"], written["art-text-1"]),
            expected_coverage=_expected_coverage(),
        ),
        privacy=privacy,
        structure=StructureContext(
            schemas=(
                SchemaExpectation(
                    artifact_version_id="art-json-1",
                    field_paths=_structure_for_clean(
                        {
                            "art-json-1": broken,
                            "art-csv-1": written["art-csv-1"],
                            "art-text-1": written["art-text-1"],
                        }
                    )
                    .schemas[0]
                    .field_paths,
                ),
            ),
            joins=(
                JoinExpectation(
                    opaque_id="join-owner-watcher",
                    left_artifact_version_id="art-json-1",
                    left_path=("ticket", "owner_id"),
                    right_artifact_version_id="art-json-1",
                    right_path=("ticket", "watcher_id"),
                ),
            ),
        ),
    )
    assert report.decision is ValidationDecision.BLOCK
    assert CODE_STRUCTURE_JOIN_MISMATCH in {finding.code for finding in report.findings}
    assert_report_has_no_sensitive_leak(
        report,
        sensitive_values_for_leak_checks(
            privacy=privacy,
            extra=("maya@acme.example", "E-AB12CD"),
        ),
    )


def test_coverage_gap_blocks_coverage_gate() -> None:
    frozen = _freeze_two_people()
    written, maya, jordan = _write_clean_candidates(frozen)
    # Omit the text artifact from the candidate set.
    report = validate_release_candidate(
        candidate=ReleaseCandidate(
            artifacts=(written["art-json-1"], written["art-csv-1"]),
            expected_coverage=_expected_coverage(),
        ),
        privacy=_privacy_for_clean(maya, jordan),
        structure=StructureContext(
            schemas=_structure_for_clean(written).schemas,
            joins=(),
        ),
    )
    assert report.decision is ValidationDecision.BLOCK
    assert CODE_COVERAGE_GAP in {finding.code for finding in report.findings}


def test_schema_mismatch_blocks_structure_gate() -> None:
    frozen = _freeze_two_people()
    written, maya, jordan = _write_clean_candidates(frozen)
    # Expect an extra field path that the candidate does not have.
    expected_paths = frozenset({("ticket", "owner_email"), ("missing", "field")})
    report = validate_release_candidate(
        candidate=ReleaseCandidate(
            artifacts=tuple(written.values()),
            expected_coverage=_expected_coverage(),
        ),
        privacy=_privacy_for_clean(maya, jordan),
        structure=StructureContext(
            schemas=(
                SchemaExpectation(
                    artifact_version_id="art-json-1",
                    field_paths=expected_paths,
                ),
            ),
            joins=(),
        ),
    )
    assert report.decision is ValidationDecision.BLOCK
    assert CODE_STRUCTURE_SCHEMA_MISMATCH in {finding.code for finding in report.findings}


def test_malformed_json_candidate_blocks_with_reparse_failed() -> None:
    """Corrupt writer output must BLOCK, not raise ValidationInputError."""
    coverage = CoverageLedger(
        entries=(
            CoverageSurfaceRef(
                opaque_id="cov-bad-json",
                artifact_version_id="art-bad-json",
                surface_key="document",
                state=CoverageState.PROCESSED,
            ),
        )
    )
    privacy = PrivacyContext(
        known_sources=(
            KnownSourceIdentifier(
                opaque_id="ks-unused",
                normalized_value="maya@acme.example",
                kind="email_address",
            ),
        ),
        canaries=(SeededCanary(opaque_id="canary-unused", token="CANARY-TOKEN-7f3a"),),
        allowed_synthetics=frozenset(),
    )
    report = validate_release_candidate(
        candidate=ReleaseCandidate(
            artifacts=(
                CandidateArtifact(
                    artifact_version_id="art-bad-json",
                    media_type="application/json",
                    payload=b"{bad",
                ),
            ),
            expected_coverage=coverage,
        ),
        privacy=privacy,
        structure=StructureContext(
            schemas=(
                SchemaExpectation(
                    artifact_version_id="art-bad-json",
                    field_paths=frozenset({("ticket", "owner_email")}),
                ),
            ),
            joins=(),
        ),
    )
    assert report.decision is ValidationDecision.BLOCK
    assert CODE_STRUCTURE_REPARSE_FAILED in {finding.code for finding in report.findings}
    assert_report_has_no_sensitive_leak(
        report,
        sensitive_values_for_leak_checks(privacy=privacy),
    )
