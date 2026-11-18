"""Deterministic patch planning with overlap resolution and referential rewrites.

The planner emits conflict-checked ``PatchPlanEntry`` records plus a private
``ReplacementVault``. Writers apply those patches only; they never invent
identities or resolve policy.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from cloakmill.domain.artifacts import validate_private_integrity_digest
from cloakmill.domain.enums import PolicyAction
from cloakmill.domain.errors import DomainValidationError
from cloakmill.domain.fields import require_opaque_id
from cloakmill.domain.locators import FieldPathLocator, OriginalLocator, TextOffsetLocator
from cloakmill.domain.mapping import (
    MappingSnapshot,
    PatchPlanEntry,
    validate_mapping_snapshot,
    validate_patch_plan_entry,
)
from cloakmill.identity.freeze import FrozenMappingBundle
from cloakmill.identity.profiles import SyntheticProfile
from cloakmill.transforms.errors import PatchConflictError, TransformError
from cloakmill.transforms.replacements import (
    ReplacementVault,
    build_replacement_vault,
    mint_replacement_ref,
    profile_attribute_value,
)
from cloakmill.transforms.safety import assert_safe_replacement

WRITER_VERSION = "structured-writers-v1"


@dataclass(frozen=True, slots=True)
class PatchRequest:
    """Caller intent before conflict checking and opaque replacement minting."""

    request_id: str
    artifact_version_id: str
    part_id: str
    locator: OriginalLocator
    action: PolicyAction
    entity_id: str | None = None
    attribute_key: str | None = None
    inert_token: str | None = None


@dataclass(frozen=True, slots=True)
class ReferentialKeyRewrite:
    """Structured field that must receive the same synthetic attribute as an entity.

    Used to preserve joins/foreign keys across supported JSON/CSV surfaces.
    """

    request_id: str
    artifact_version_id: str
    part_id: str
    locator: FieldPathLocator
    entity_id: str
    attribute_key: str


@dataclass(frozen=True, slots=True)
class ArtifactScope:
    """Explicit allowlist entry for an artifact covered by a patch plan.

    Writers default-deny artifacts that are not listed here. ``content_digest``
    must be ``sha256:<64 lowercase hex>`` of the immutable original bytes.
    An artifact may appear with zero patch entries as an affirmative no-op.
    """

    artifact_version_id: str
    content_digest: str


@dataclass(frozen=True, slots=True)
class PatchPlan:
    """Conflict-checked patches pinned to a frozen mapping and writer version."""

    mapping_snapshot_id: str
    policy_version: str
    writer_version: str
    entries: tuple[PatchPlanEntry, ...]
    vault: ReplacementVault
    artifact_scopes: tuple[ArtifactScope, ...] = ()

    @property
    def excluded_artifact_ids(self) -> frozenset[str]:
        return frozenset(
            entry.artifact_version_id
            for entry in self.entries
            if entry.action is PolicyAction.EXCLUDE
        )

    def scope_for(self, artifact_version_id: str) -> ArtifactScope | None:
        for scope in self.artifact_scopes:
            if scope.artifact_version_id == artifact_version_id:
                return scope
        return None


def content_digest_sha256(payload: bytes) -> str:
    """Return a private integrity digest for original artifact bytes."""
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def plan_patches(
    *,
    frozen: FrozenMappingBundle,
    requests: Sequence[PatchRequest],
    namespace_secret: bytes,
    referential_rewrites: Sequence[ReferentialKeyRewrite] = (),
    artifact_scopes: Sequence[ArtifactScope] = (),
    writer_version: str = WRITER_VERSION,
) -> PatchPlan:
    """Build a deterministic patch plan from policy intents and frozen profiles.

    Requires ``namespace_secret`` and authenticates the frozen mapping snapshot
    HMAC (same boundary as ``freeze_mapping`` / ``FrozenMappingStore.put``).
    """
    if not isinstance(frozen, FrozenMappingBundle):
        raise TransformError("plan_patches requires a FrozenMappingBundle")
    if not isinstance(namespace_secret, bytes):
        raise TransformError("plan_patches requires namespace_secret as bytes")
    snapshot = frozen.snapshot
    try:
        validate_mapping_snapshot(snapshot, namespace_secret=namespace_secret)
    except DomainValidationError as exc:
        raise TransformError(
            f"frozen snapshot {snapshot.opaque_id!r} failed integrity authentication"
        ) from exc
    if writer_version.strip() == "":
        raise TransformError("writer_version must be non-empty")

    scopes = _validate_artifact_scopes(artifact_scopes)
    scope_ids = {scope.artifact_version_id for scope in scopes}

    profiles = frozen.profile_by_id()
    entity_to_profile = {
        assignment.entity_id: profiles[assignment.profile_id] for assignment in snapshot.assignments
    }

    expanded = list(requests) + [
        PatchRequest(
            request_id=item.request_id,
            artifact_version_id=item.artifact_version_id,
            part_id=item.part_id,
            locator=item.locator,
            action=PolicyAction.REPLACE,
            entity_id=item.entity_id,
            attribute_key=item.attribute_key,
        )
        for item in referential_rewrites
    ]
    for request in expanded:
        if request.artifact_version_id not in scope_ids:
            raise TransformError(
                f"patch request artifact {request.artifact_version_id!r} "
                "is not listed in artifact_scopes"
            )
    if not expanded:
        return PatchPlan(
            mapping_snapshot_id=snapshot.opaque_id,
            policy_version=snapshot.policy_version,
            writer_version=writer_version,
            entries=(),
            vault=build_replacement_vault({}),
            artifact_scopes=scopes,
        )

    # Stable ordering before conflict resolution for deterministic opaque ids.
    expanded.sort(key=_request_sort_key)
    resolved = _resolve_overlaps(expanded)

    vault_entries: dict[str, str] = {}
    plan_entries: list[PatchPlanEntry] = []
    for request in resolved:
        entry, vault_item = _materialize_entry(
            request=request,
            snapshot=snapshot,
            entity_to_profile=entity_to_profile,
        )
        validate_patch_plan_entry(entry)
        if vault_item is not None:
            ref, value = vault_item
            existing = vault_entries.get(ref)
            if existing is not None and existing != value:
                raise PatchConflictError(f"replacement_ref {ref!r} resolved to conflicting values")
            vault_entries[ref] = value
        plan_entries.append(entry)

    plan_entries.sort(key=_entry_sort_key)
    return PatchPlan(
        mapping_snapshot_id=snapshot.opaque_id,
        policy_version=snapshot.policy_version,
        writer_version=writer_version,
        entries=tuple(plan_entries),
        vault=build_replacement_vault(vault_entries),
        artifact_scopes=scopes,
    )


def patches_for_artifact(
    plan: PatchPlan,
    artifact_version_id: str,
) -> tuple[PatchPlanEntry, ...]:
    """Return non-exclude patches for one artifact in writer application order."""
    if artifact_version_id in plan.excluded_artifact_ids:
        raise TransformError(f"artifact {artifact_version_id!r} is excluded by the patch plan")
    selected = [
        entry
        for entry in plan.entries
        if entry.artifact_version_id == artifact_version_id
        and entry.action is not PolicyAction.EXCLUDE
    ]
    selected.sort(key=_entry_sort_key)
    return tuple(selected)


def _validate_artifact_scopes(scopes: Sequence[ArtifactScope]) -> tuple[ArtifactScope, ...]:
    seen: set[str] = set()
    validated: list[ArtifactScope] = []
    for scope in scopes:
        if not isinstance(scope, ArtifactScope):
            raise TransformError("artifact_scopes entries must be ArtifactScope")
        require_opaque_id(scope.artifact_version_id, "artifact_version_id")
        validate_private_integrity_digest(scope.content_digest)
        if scope.artifact_version_id in seen:
            raise TransformError(
                f"duplicate artifact_scopes entry for {scope.artifact_version_id!r}"
            )
        seen.add(scope.artifact_version_id)
        validated.append(scope)
    validated.sort(key=lambda item: item.artifact_version_id)
    return tuple(validated)


def _materialize_entry(
    *,
    request: PatchRequest,
    snapshot: MappingSnapshot,
    entity_to_profile: Mapping[str, SyntheticProfile],
) -> tuple[PatchPlanEntry, tuple[str, str] | None]:
    action = request.action
    if not isinstance(action, PolicyAction):
        raise TransformError("action must be a PolicyAction")

    entity_id = request.entity_id
    replacement_ref: str | None = None
    vault_item: tuple[str, str] | None = None

    if action is PolicyAction.REPLACE:
        if entity_id is None or request.attribute_key is None:
            raise TransformError("replace requests require entity_id and attribute_key")
        try:
            profile = entity_to_profile[entity_id]
        except KeyError as exc:
            raise TransformError(f"no frozen assignment for entity {entity_id!r}") from exc
        value = profile_attribute_value(profile, request.attribute_key)
        replacement_ref = mint_replacement_ref(
            mapping_snapshot_id=snapshot.opaque_id,
            entity_id=entity_id,
            attribute_key=request.attribute_key,
            action=action.value,
        )
        vault_item = (replacement_ref, value)
    elif action is PolicyAction.INERT:
        if request.inert_token is None:
            raise TransformError("inert requests require inert_token")
        if entity_id is not None:
            raise TransformError("inert requests must not set entity_id")
        value = assert_safe_replacement(request.inert_token, field_name="inert_token")
        replacement_ref = mint_replacement_ref(
            mapping_snapshot_id=snapshot.opaque_id,
            entity_id=None,
            attribute_key=None,
            action=action.value,
            inert_token=value,
        )
        vault_item = (replacement_ref, value)
    elif action is PolicyAction.REMOVE:
        if request.inert_token is not None or request.attribute_key is not None:
            raise TransformError("remove requests must not set replacement material")
    elif action is PolicyAction.EXCLUDE:
        if request.inert_token is not None or request.attribute_key is not None:
            raise TransformError("exclude requests must not set replacement material")
    else:
        raise TransformError(f"unsupported policy action: {action!r}")

    opaque_id = _patch_opaque_id(
        mapping_snapshot_id=snapshot.opaque_id,
        request=request,
        replacement_ref=replacement_ref,
    )
    entry = PatchPlanEntry(
        opaque_id=opaque_id,
        mapping_snapshot_id=snapshot.opaque_id,
        artifact_version_id=request.artifact_version_id,
        part_id=request.part_id,
        locator=request.locator,
        action=action,
        entity_id=entity_id,
        replacement_ref=replacement_ref,
    )
    return entry, vault_item


def _resolve_overlaps(requests: Sequence[PatchRequest]) -> list[PatchRequest]:
    """Resolve overlaps per (artifact, part). Prefer longer text spans; reject conflicts."""
    by_part: dict[tuple[str, str], list[PatchRequest]] = {}
    for request in requests:
        key = (request.artifact_version_id, request.part_id)
        by_part.setdefault(key, []).append(request)

    accepted: list[PatchRequest] = []
    for part_requests in by_part.values():
        accepted.extend(_resolve_part_overlaps(part_requests))
    accepted.sort(key=_request_sort_key)
    return accepted


def _resolve_part_overlaps(requests: Sequence[PatchRequest]) -> list[PatchRequest]:
    field_requests = [item for item in requests if isinstance(item.locator, FieldPathLocator)]
    text_requests = [item for item in requests if isinstance(item.locator, TextOffsetLocator)]
    if len(field_requests) + len(text_requests) != len(requests):
        raise TransformError("unsupported locator kind in patch request")

    accepted_fields = _dedupe_field_requests(field_requests)
    if accepted_fields and text_requests:
        # A whole-field structured patch conflicts with any text span on the same part.
        raise PatchConflictError(
            "structured field patch conflicts with text-offset patches on the same part"
        )
    if accepted_fields:
        return accepted_fields
    return _resolve_text_overlaps(text_requests)


def _dedupe_field_requests(requests: Sequence[PatchRequest]) -> list[PatchRequest]:
    by_path: dict[tuple[str | int, ...], PatchRequest] = {}
    for request in sorted(requests, key=_request_sort_key):
        assert isinstance(request.locator, FieldPathLocator)
        path = request.locator.path
        existing = by_path.get(path)
        if existing is None:
            by_path[path] = request
            continue
        if not _requests_semantically_equal(existing, request):
            raise PatchConflictError(
                f"conflicting patches for field path "
                f"(requests {existing.request_id!r} vs {request.request_id!r})"
            )
    return list(by_path.values())


def _resolve_text_overlaps(requests: Sequence[PatchRequest]) -> list[PatchRequest]:
    # Longer spans first at the same start so contained shorter spans are dropped.
    ordered = sorted(
        requests,
        key=lambda item: (
            item.locator.start,  # type: ignore[union-attr]
            -(item.locator.end - item.locator.start),  # type: ignore[union-attr]
            item.request_id,
        ),
    )
    accepted: list[PatchRequest] = []
    accepted_spans: list[TextOffsetLocator] = []
    for request in ordered:
        locator = request.locator
        assert isinstance(locator, TextOffsetLocator)
        conflict = False
        skip_duplicate = False
        for prior_request, prior in zip(accepted, accepted_spans, strict=True):
            if prior.unit != locator.unit:
                raise PatchConflictError("text patches must share the same offset unit")
            if not _text_offsets_overlap(prior, locator):
                continue
            # Identical spans: conflict if semantics differ; otherwise dedupe.
            if (
                prior.start == locator.start
                and prior.end == locator.end
                and prior.unit == locator.unit
            ):
                if not _requests_semantically_equal(prior_request, request):
                    raise PatchConflictError(
                        f"conflicting patches for text span [{locator.start}, {locator.end})"
                    )
                skip_duplicate = True
                break
            if _span_strictly_contains(prior, locator):
                # Longer span already accepted. Drop a contained request only when
                # the action intent matches (e.g. nested REPLACE of the same entity);
                # differing actions (EXCLUDE inside REPLACE) must fail closed.
                if not _requests_same_action_intent(prior_request, request):
                    raise PatchConflictError(
                        "contained text-offset patch conflicts with longer span "
                        f"(requests {prior_request.request_id!r} vs {request.request_id!r})"
                    )
                skip_duplicate = True
                break
            if _span_strictly_contains(locator, prior):
                # Should not happen because longer spans are considered first.
                raise PatchConflictError("internal overlap order error")
            conflict = True
            break
        if skip_duplicate:
            continue
        if conflict:
            raise PatchConflictError(
                f"partial text-offset overlap at [{locator.start}, {locator.end})"
            )
        accepted.append(request)
        accepted_spans.append(locator)
    return accepted


def _requests_same_action_intent(left: PatchRequest, right: PatchRequest) -> bool:
    """True when both requests express the same transform intent (ignore locator)."""
    return (
        left.action == right.action
        and left.entity_id == right.entity_id
        and left.attribute_key == right.attribute_key
        and left.inert_token == right.inert_token
    )


def _requests_semantically_equal(left: PatchRequest, right: PatchRequest) -> bool:
    return (
        _requests_same_action_intent(left, right)
        and left.artifact_version_id == right.artifact_version_id
        and left.part_id == right.part_id
        and left.locator == right.locator
    )


def _text_offsets_overlap(left: TextOffsetLocator, right: TextOffsetLocator) -> bool:
    return left.start < right.end and right.start < left.end


def _span_strictly_contains(outer: TextOffsetLocator, inner: TextOffsetLocator) -> bool:
    """Return True when ``outer`` covers ``inner`` and is strictly larger."""
    if not (outer.start <= inner.start and inner.end <= outer.end):
        return False
    return outer.start < inner.start or inner.end < outer.end


def _request_sort_key(request: PatchRequest) -> tuple[object, ...]:
    locator_key = _locator_sort_key(request.locator)
    return (
        request.artifact_version_id,
        request.part_id,
        locator_key,
        request.action.value,
        request.request_id,
    )


def _entry_sort_key(entry: PatchPlanEntry) -> tuple[object, ...]:
    return (
        entry.artifact_version_id,
        entry.part_id,
        _locator_sort_key(entry.locator),
        entry.action.value,
        entry.opaque_id,
    )


def _locator_sort_key(locator: OriginalLocator) -> tuple[object, ...]:
    if isinstance(locator, TextOffsetLocator):
        return ("text_offset", locator.unit.value, locator.start, locator.end)
    if isinstance(locator, FieldPathLocator):
        return ("field_path", tuple(locator.path))
    raise TransformError(f"unsupported locator type: {type(locator).__name__}")


def _patch_opaque_id(
    *,
    mapping_snapshot_id: str,
    request: PatchRequest,
    replacement_ref: str | None,
) -> str:
    locator = request.locator
    if isinstance(locator, TextOffsetLocator):
        locator_material = f"text_offset:{locator.unit.value}:{locator.start}:{locator.end}"
    else:
        assert isinstance(locator, FieldPathLocator)
        path = "/".join(str(segment) for segment in locator.path)
        locator_material = f"field_path:{path}"
    material = "\0".join(
        [
            mapping_snapshot_id,
            request.artifact_version_id,
            request.part_id,
            locator_material,
            request.action.value,
            request.entity_id or "",
            request.attribute_key or "",
            replacement_ref or "",
            request.request_id,
        ]
    )
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:20]
    return f"patch-{digest}"


def iter_replace_targets(plan: PatchPlan) -> Iterable[PatchPlanEntry]:
    """Yield REPLACE entries only (useful for referential integrity checks)."""
    for entry in plan.entries:
        if entry.action is PolicyAction.REPLACE:
            yield entry
