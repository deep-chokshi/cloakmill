"""Strong-anchor identity resolver with abstention and exception grouping.

Detection observations remain proposals. This module links mentions that share
stable anchors, keeps people/accounts/orgs distinct, abstains on weak-only
signals, and preserves contradictions instead of transitive wrong merges.

Serialized outputs carry opaque keyed refs only. Cleartext anchor values stay in
an in-process ``PrivateAnchorIndex`` that is never serialized.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from cloakmill.domain.enums import AnchorKind, DecisionOutcome, EntityKind
from cloakmill.domain.errors import DomainValidationError
from cloakmill.domain.fields import require_opaque_id
from cloakmill.identity.graph import (
    AcceptedEntity,
    AcceptedEntityGraph,
    ContradictionConstraint,
    ExceptionGroup,
    IdentityDecision,
    PrivateAnchorIndex,
    StrongAnchor,
    validate_accepted_entity_graph,
)
from cloakmill.identity.ids import (
    contradiction_opaque_id,
    decision_opaque_id,
    entity_opaque_id,
    exception_opaque_id,
    graph_opaque_id,
    opaque_anchor_ref,
    opaque_weak_signal_ref,
    require_namespace_secret,
)
from cloakmill.identity.mentions import (
    STRONG_ENTITY_TYPES,
    DirectoryAnchor,
    MentionEvidence,
    default_entity_kind_for_anchor,
    normalize_anchor_value,
    validate_directory_anchor,
    validate_mention_evidence,
)
from cloakmill.identity.metrics import ResolutionMetrics, build_resolution_metrics
from cloakmill.identity.policy import (
    POLICY_VERSION,
    REASON_CONFLICTING_ACCOUNT_ID,
    REASON_CONFLICTING_EMAIL,
    REASON_CONFLICTING_EMPLOYEE_ID,
    REASON_DIRECTORY_ENTITY,
    REASON_KIND_MISMATCH,
    REASON_NO_STRONG_ANCHOR,
    REASON_SHARED_MAILBOX,
    REASON_SINGLETON,
    REASON_STRONG_ANCHOR_MATCH,
    REASON_WEAK_FIRST_NAME,
    RULE_CONFLICTING_ANCHORS,
    RULE_DIRECTORY_BIND,
    RULE_KIND_SEPARATE,
    RULE_SHARED_ACCOUNT_SEPARATE,
    RULE_SINGLETON_ACCEPT,
    RULE_STRONG_ANCHOR_MERGE,
    RULE_WEAK_NAME_REVIEW,
)

_EXCLUSIVE_PERSON_ANCHORS = frozenset({AnchorKind.EMAIL, AnchorKind.EMPLOYEE_ID})
_EXCLUSIVE_ACCOUNT_ANCHORS = frozenset({AnchorKind.ACCOUNT_ID})


@dataclass(frozen=True, slots=True)
class ResolutionResult:
    """Outputs of one identity-resolution pass."""

    graph: AcceptedEntityGraph
    decisions: tuple[IdentityDecision, ...]
    exceptions: tuple[ExceptionGroup, ...]
    contradictions: tuple[ContradictionConstraint, ...]
    metrics: ResolutionMetrics
    private_anchor_index: PrivateAnchorIndex
    policy_version: str = POLICY_VERSION

    @property
    def requires_exception_review(self) -> bool:
        return len(self.exceptions) > 0 or len(self.contradictions) > 0


class _UnionFind:
    def __init__(self) -> None:
        self._parent: dict[str, str] = {}

    def add(self, item: str) -> None:
        self._parent.setdefault(item, item)

    def __contains__(self, item: object) -> bool:
        return isinstance(item, str) and item in self._parent

    def find(self, item: str) -> str:
        # Never auto-insert: weak-only observation ids must not enter the graph.
        if item not in self._parent:
            raise KeyError(item)
        parent = self._parent[item]
        if parent != item:
            self._parent[item] = self.find(parent)
        return self._parent[item]

    def union(self, left: str, right: str) -> str:
        root_left = self.find(left)
        root_right = self.find(right)
        if root_left == root_right:
            return root_left
        # Deterministic attachment: lexicographically smaller root wins.
        if root_left < root_right:
            self._parent[root_right] = root_left
            return root_left
        self._parent[root_left] = root_right
        return root_right

    def components(self) -> dict[str, set[str]]:
        groups: dict[str, set[str]] = defaultdict(set)
        for item in self._parent:
            groups[self.find(item)].add(item)
        return dict(groups)


class StrongAnchorIdentityResolver:
    """Link mentions via strong anchors; abstain on weak/ambiguous evidence."""

    def resolve(
        self,
        mentions: Sequence[MentionEvidence],
        *,
        namespace_id: str,
        namespace_secret: bytes,
        graph_version: str = "1",
        directory: Sequence[DirectoryAnchor] = (),
        expected_links: Sequence[Mapping[str, object]] | None = None,
    ) -> ResolutionResult:
        require_opaque_id(namespace_id, "namespace_id")
        secret = require_namespace_secret(namespace_secret)
        if not isinstance(graph_version, str) or graph_version.strip() == "":
            raise DomainValidationError("graph_version must be a non-empty string")

        validated = tuple(mentions)
        for mention in validated:
            validate_mention_evidence(mention)
        directory_entries = tuple(directory)
        for anchor in directory_entries:
            validate_directory_anchor(anchor)

        obs_ids = [mention.observation_id for mention in validated]
        if len(obs_ids) != len(set(obs_ids)):
            raise DomainValidationError("mention observation_id values must be unique")

        by_id = {mention.observation_id: mention for mention in validated}
        directory_index = _index_directory(directory_entries)
        private_values: dict[str, str] = {}

        strong_mentions: list[MentionEvidence] = []
        weak_only: list[MentionEvidence] = []
        for mention in validated:
            if mention.entity_type in STRONG_ENTITY_TYPES:
                strong_mentions.append(mention)
            else:
                weak_only.append(mention)

        decisions: list[IdentityDecision] = []
        exceptions: list[ExceptionGroup] = []
        contradictions: list[ContradictionConstraint] = []

        # Weak-only mentions (e.g. payment_card, or name-only stubs) never auto-merge.
        for mention in weak_only:
            weak_refs = _weak_signal_refs(mention, secret, private_values)
            exceptions.append(
                ExceptionGroup(
                    opaque_id=exception_opaque_id(
                        reason_code=REASON_NO_STRONG_ANCHOR,
                        observation_ids=(mention.observation_id,),
                    ),
                    reason_code=REASON_NO_STRONG_ANCHOR,
                    observation_ids=(mention.observation_id,),
                    weak_signal_refs=weak_refs,
                )
            )
            decisions.append(
                IdentityDecision(
                    opaque_id=decision_opaque_id(
                        outcome=DecisionOutcome.REVIEW.value,
                        rule_id=RULE_WEAK_NAME_REVIEW,
                        observation_ids=(mention.observation_id,),
                    ),
                    outcome=DecisionOutcome.REVIEW,
                    rule_id=RULE_WEAK_NAME_REVIEW,
                    rule_version=POLICY_VERSION,
                    observation_ids=(mention.observation_id,),
                    reason_code=REASON_NO_STRONG_ANCHOR,
                    evidence_refs=(mention.observation_id,),
                )
            )

        uf = _UnionFind()
        for mention in strong_mentions:
            uf.add(mention.observation_id)

        # Index strong mentions by (kind, value) — cleartext used only in-process.
        by_anchor: dict[tuple[AnchorKind, str], list[str]] = defaultdict(list)
        for mention in strong_mentions:
            anchor = mention.strong_anchor()
            if anchor is None:
                continue
            by_anchor[anchor].append(mention.observation_id)

        # Merge exact strong-anchor matches (same kind+value).
        for _anchor_key, obs_list in sorted(
            by_anchor.items(),
            key=lambda item: (item[0][0].value, item[0][1]),
        ):
            if len(obs_list) < 2:
                continue
            root = obs_list[0]
            for other in obs_list[1:]:
                if not _compatible_for_merge(by_id[root], by_id[other], directory_index):
                    continue
                blocked = _exclusive_conflict(by_id, uf, root, other)
                if blocked is not None:
                    contradictions.append(blocked)
                    decisions.append(
                        _separate_decision(
                            rule_id=RULE_CONFLICTING_ANCHORS,
                            observation_ids=tuple(sorted({root, other})),
                            reason_code=blocked.reason_code,
                        )
                    )
                    continue
                uf.union(root, other)

        # Co-located strong anchors on the same part (structured record) may bind
        # compatible kinds when no exclusive-anchor contradiction exists.
        by_part: dict[str, list[str]] = defaultdict(list)
        for mention in strong_mentions:
            by_part[mention.part_id].append(mention.observation_id)
        for _part_id, obs_list in sorted(by_part.items()):
            if len(obs_list) < 2:
                continue
            root = obs_list[0]
            for other in obs_list[1:]:
                if not _compatible_for_merge(by_id[root], by_id[other], directory_index):
                    continue
                blocked = _exclusive_conflict(by_id, uf, root, other)
                if blocked is not None:
                    contradictions.append(blocked)
                    decisions.append(
                        _separate_decision(
                            rule_id=RULE_CONFLICTING_ANCHORS,
                            observation_ids=tuple(sorted({root, other})),
                            reason_code=blocked.reason_code,
                        )
                    )
                    continue
                uf.union(root, other)

        # Directory multi-anchor binding within the same entity_key.
        by_entity_key: dict[str, list[DirectoryAnchor]] = defaultdict(list)
        for anchor in directory_entries:
            by_entity_key[anchor.entity_key].append(anchor)

        for entity_key, anchors in sorted(by_entity_key.items()):
            if len(anchors) < 2:
                continue
            if any(item.is_shared for item in anchors):
                # Shared accounts do not absorb operator person anchors.
                continue
            linked_obs: list[str] = []
            for anchor in anchors:
                key = (anchor.anchor_kind, anchor.indexed_value())
                linked_obs.extend(by_anchor.get(key, ()))
            linked_obs = sorted(set(linked_obs))
            if len(linked_obs) < 2:
                continue
            if not _directory_kinds_compatible(anchors):
                continue
            root = linked_obs[0]
            for other in linked_obs[1:]:
                if not _compatible_for_merge(by_id[root], by_id[other], directory_index):
                    continue
                blocked = _exclusive_conflict(by_id, uf, root, other)
                if blocked is not None:
                    contradictions.append(blocked)
                    decisions.append(
                        _separate_decision(
                            rule_id=RULE_CONFLICTING_ANCHORS,
                            observation_ids=tuple(sorted({root, other})),
                            reason_code=blocked.reason_code,
                        )
                    )
                    continue
                if uf.find(root) == uf.find(other):
                    continue
                uf.union(root, other)
                decisions.append(
                    IdentityDecision(
                        opaque_id=decision_opaque_id(
                            outcome=DecisionOutcome.ACCEPT.value,
                            rule_id=RULE_DIRECTORY_BIND,
                            observation_ids=tuple(sorted({root, other})),
                        ),
                        outcome=DecisionOutcome.ACCEPT,
                        rule_id=RULE_DIRECTORY_BIND,
                        rule_version=POLICY_VERSION,
                        observation_ids=tuple(sorted({root, other})),
                        reason_code=REASON_DIRECTORY_ENTITY,
                        evidence_refs=(entity_key, root, other),
                    )
                )

        # Shared mailbox: keep account separate from operator persons.
        for anchor in directory_entries:
            if not anchor.is_shared:
                continue
            mailbox_obs = by_anchor.get((anchor.anchor_kind, anchor.indexed_value()), [])
            operator_obs: list[str] = []
            for person_key in anchor.operator_person_keys:
                for other in directory_entries:
                    if other.entity_key != person_key:
                        continue
                    operator_obs.extend(
                        by_anchor.get((other.anchor_kind, other.indexed_value()), [])
                    )
            if mailbox_obs and operator_obs:
                decisions.append(
                    IdentityDecision(
                        opaque_id=decision_opaque_id(
                            outcome=DecisionOutcome.SEPARATE.value,
                            rule_id=RULE_SHARED_ACCOUNT_SEPARATE,
                            observation_ids=tuple(sorted({*mailbox_obs, *operator_obs})),
                        ),
                        outcome=DecisionOutcome.SEPARATE,
                        rule_id=RULE_SHARED_ACCOUNT_SEPARATE,
                        rule_version=POLICY_VERSION,
                        observation_ids=tuple(sorted({*mailbox_obs, *operator_obs})),
                        reason_code=REASON_SHARED_MAILBOX,
                        evidence_refs=(anchor.entity_key, *sorted(set(operator_obs))),
                    )
                )

        components = uf.components()
        entities: list[AcceptedEntity] = []
        obs_to_entity: dict[str, str] = {}

        for _root, members in sorted(components.items(), key=lambda item: min(item[1])):
            member_list = sorted(members)
            member_mentions = [by_id[obs_id] for obs_id in member_list]
            entity_kind = _resolve_entity_kind(member_mentions, directory_index)
            anchors, seed_pair = _collect_strong_anchors(member_mentions, secret, private_values)
            if seed_pair is None:
                # Strong-mention components always have at least one strong anchor.
                raise DomainValidationError(
                    "strong-anchor component missing seed anchor (internal invariant)"
                )
            seed_kind, seed_value = seed_pair
            directory_key = _directory_entity_key(member_mentions, directory_index)
            entity_id = entity_opaque_id(
                entity_kind=entity_kind,
                seed_anchor_kind=seed_kind,
                seed_value=seed_value,
                namespace_id=namespace_id,
                namespace_secret=secret,
            )
            entity = AcceptedEntity(
                opaque_id=entity_id,
                entity_kind=entity_kind,
                observation_ids=tuple(member_list),
                strong_anchors=tuple(anchors),
                directory_entity_key=directory_key,
            )
            entities.append(entity)
            for obs_id in member_list:
                obs_to_entity[obs_id] = entity_id

            if len(member_list) == 1:
                decisions.append(
                    IdentityDecision(
                        opaque_id=decision_opaque_id(
                            outcome=DecisionOutcome.ACCEPT.value,
                            rule_id=RULE_SINGLETON_ACCEPT,
                            observation_ids=tuple(member_list),
                        ),
                        outcome=DecisionOutcome.ACCEPT,
                        rule_id=RULE_SINGLETON_ACCEPT,
                        rule_version=POLICY_VERSION,
                        observation_ids=tuple(member_list),
                        reason_code=REASON_SINGLETON,
                        entity_id=entity_id,
                        evidence_refs=tuple(member_list),
                    )
                )
            else:
                decisions.append(
                    IdentityDecision(
                        opaque_id=decision_opaque_id(
                            outcome=DecisionOutcome.ACCEPT.value,
                            rule_id=RULE_STRONG_ANCHOR_MERGE,
                            observation_ids=tuple(member_list),
                        ),
                        outcome=DecisionOutcome.ACCEPT,
                        rule_id=RULE_STRONG_ANCHOR_MERGE,
                        rule_version=POLICY_VERSION,
                        observation_ids=tuple(member_list),
                        reason_code=REASON_STRONG_ANCHOR_MATCH,
                        entity_id=entity_id,
                        evidence_refs=tuple(member_list),
                    )
                )

        # Weak first-name ambiguity across distinct accepted person entities.
        first_name_groups: dict[str, list[str]] = defaultdict(list)
        for mention in strong_mentions:
            if mention.first_name is None:
                continue
            key = normalize_anchor_value(AnchorKind.FIRST_NAME, mention.first_name)
            entity_id = obs_to_entity.get(mention.observation_id)
            if entity_id is not None:
                first_name_groups[key].append(entity_id)

        for name, entity_ids in sorted(first_name_groups.items()):
            unique_entities = tuple(sorted(set(entity_ids)))
            if len(unique_entities) < 2:
                continue
            related_obs = sorted(
                {
                    mention.observation_id
                    for mention in strong_mentions
                    if mention.first_name is not None
                    and normalize_anchor_value(AnchorKind.FIRST_NAME, mention.first_name) == name
                }
            )
            if len({obs_to_entity[obs] for obs in related_obs if obs in obs_to_entity}) < 2:
                continue
            weak_ref = opaque_weak_signal_ref(
                kind=AnchorKind.FIRST_NAME,
                normalized_value=name,
                namespace_secret=secret,
            )
            private_values[weak_ref] = name
            exceptions.append(
                ExceptionGroup(
                    opaque_id=exception_opaque_id(
                        reason_code=REASON_WEAK_FIRST_NAME,
                        observation_ids=tuple(related_obs),
                    ),
                    reason_code=REASON_WEAK_FIRST_NAME,
                    observation_ids=tuple(related_obs),
                    candidate_entity_ids=unique_entities,
                    weak_signal_refs=(weak_ref,),
                )
            )
            decisions.append(
                IdentityDecision(
                    opaque_id=decision_opaque_id(
                        outcome=DecisionOutcome.REVIEW.value,
                        rule_id=RULE_WEAK_NAME_REVIEW,
                        observation_ids=tuple(related_obs),
                    ),
                    outcome=DecisionOutcome.REVIEW,
                    rule_id=RULE_WEAK_NAME_REVIEW,
                    rule_version=POLICY_VERSION,
                    observation_ids=tuple(related_obs),
                    reason_code=REASON_WEAK_FIRST_NAME,
                    evidence_refs=tuple(related_obs),
                )
            )

        # People, accounts, and organizations remain distinct entity kinds.
        kind_groups = {
            EntityKind.PERSON: [e for e in entities if e.entity_kind is EntityKind.PERSON],
            EntityKind.ACCOUNT: [e for e in entities if e.entity_kind is EntityKind.ACCOUNT],
            EntityKind.ORGANIZATION: [
                e for e in entities if e.entity_kind is EntityKind.ORGANIZATION
            ],
        }
        present_kinds = [kind for kind, group in kind_groups.items() if group]
        if len(present_kinds) >= 2:
            sample_obs: list[str] = []
            for kind in present_kinds:
                sample_obs.append(kind_groups[kind][0].observation_ids[0])
            decisions.append(
                _separate_decision(
                    rule_id=RULE_KIND_SEPARATE,
                    observation_ids=tuple(sample_obs),
                    reason_code=REASON_KIND_MISMATCH,
                )
            )

        entities_sorted = tuple(sorted(entities, key=lambda item: item.opaque_id))
        graph = AcceptedEntityGraph(
            opaque_id=graph_opaque_id(
                namespace_id=namespace_id,
                graph_version=graph_version,
                entity_ids=tuple(entity.opaque_id for entity in entities_sorted),
            ),
            graph_version=graph_version,
            namespace_id=namespace_id,
            entities=entities_sorted,
        )
        validate_accepted_entity_graph(graph)

        seen_decisions: set[str] = set()
        unique_decisions: list[IdentityDecision] = []
        for decision in decisions:
            if decision.opaque_id in seen_decisions:
                continue
            seen_decisions.add(decision.opaque_id)
            unique_decisions.append(decision)

        seen_exc: set[str] = set()
        unique_exceptions: list[ExceptionGroup] = []
        for group in exceptions:
            if group.opaque_id in seen_exc:
                continue
            seen_exc.add(group.opaque_id)
            unique_exceptions.append(group)

        metrics = build_resolution_metrics(
            graph=graph,
            decisions=tuple(unique_decisions),
            exceptions=tuple(unique_exceptions),
            total_mentions=len(validated),
            expected_links=expected_links,
        )
        return ResolutionResult(
            graph=graph,
            decisions=tuple(unique_decisions),
            exceptions=tuple(unique_exceptions),
            contradictions=tuple(contradictions),
            metrics=metrics,
            private_anchor_index=PrivateAnchorIndex(values=dict(private_values)),
        )


def _index_directory(
    directory: Sequence[DirectoryAnchor],
) -> dict[tuple[AnchorKind, str], DirectoryAnchor]:
    index: dict[tuple[AnchorKind, str], DirectoryAnchor] = {}
    for anchor in directory:
        key = (anchor.anchor_kind, anchor.indexed_value())
        if key in index and index[key].entity_key != anchor.entity_key:
            raise DomainValidationError(
                "directory conflict for anchor kind "
                f"{anchor.anchor_kind.value}: "
                f"{index[key].entity_key!r} vs {anchor.entity_key!r}"
            )
        index[key] = anchor
    return index


def _weak_signal_refs(
    mention: MentionEvidence,
    namespace_secret: bytes,
    private_values: dict[str, str],
) -> tuple[str, ...]:
    refs: list[str] = []
    if mention.first_name is not None:
        value = normalize_anchor_value(AnchorKind.FIRST_NAME, mention.first_name)
        ref = opaque_weak_signal_ref(
            kind=AnchorKind.FIRST_NAME,
            normalized_value=value,
            namespace_secret=namespace_secret,
        )
        private_values[ref] = value
        refs.append(ref)
    if mention.display_name is not None:
        value = normalize_anchor_value(AnchorKind.DISPLAY_NAME, mention.display_name)
        ref = opaque_weak_signal_ref(
            kind=AnchorKind.DISPLAY_NAME,
            normalized_value=value,
            namespace_secret=namespace_secret,
        )
        private_values[ref] = value
        refs.append(ref)
    return tuple(refs)


def _compatible_for_merge(
    left: MentionEvidence,
    right: MentionEvidence,
    directory_index: Mapping[tuple[AnchorKind, str], DirectoryAnchor],
) -> bool:
    left_kind = _mention_entity_kind(left, directory_index)
    right_kind = _mention_entity_kind(right, directory_index)
    return left_kind is right_kind


def _mention_entity_kind(
    mention: MentionEvidence,
    directory_index: Mapping[tuple[AnchorKind, str], DirectoryAnchor],
) -> EntityKind:
    anchor = mention.strong_anchor()
    if anchor is None:
        return EntityKind.PERSON
    directory = directory_index.get(anchor)
    if directory is not None:
        return directory.entity_kind
    return default_entity_kind_for_anchor(anchor[0])


def _directory_kinds_compatible(anchors: Sequence[DirectoryAnchor]) -> bool:
    kinds = {anchor.entity_kind for anchor in anchors}
    return len(kinds) == 1


def _resolve_entity_kind(
    mentions: Sequence[MentionEvidence],
    directory_index: Mapping[tuple[AnchorKind, str], DirectoryAnchor],
) -> EntityKind:
    kinds = {_mention_entity_kind(mention, directory_index) for mention in mentions}
    if len(kinds) == 1:
        return next(iter(kinds))
    if EntityKind.ACCOUNT in kinds:
        return EntityKind.ACCOUNT
    if EntityKind.ORGANIZATION in kinds:
        return EntityKind.ORGANIZATION
    return EntityKind.PERSON


def _collect_strong_anchors(
    mentions: Sequence[MentionEvidence],
    namespace_secret: bytes,
    private_values: dict[str, str],
) -> tuple[list[StrongAnchor], tuple[AnchorKind, str] | None]:
    anchors: dict[tuple[str, str], StrongAnchor] = {}
    seed: tuple[AnchorKind, str] | None = None
    for mention in mentions:
        pair = mention.strong_anchor()
        if pair is None:
            continue
        kind, value = pair
        if seed is None:
            seed = (kind, value)
        ref = opaque_anchor_ref(
            kind=kind,
            normalized_value=value,
            namespace_secret=namespace_secret,
        )
        private_values[ref] = value
        anchors[(kind.value, ref)] = StrongAnchor(kind=kind, opaque_ref=ref)
    return [anchors[key] for key in sorted(anchors)], seed


def _directory_entity_key(
    mentions: Sequence[MentionEvidence],
    directory_index: Mapping[tuple[AnchorKind, str], DirectoryAnchor],
) -> str | None:
    keys: set[str] = set()
    for mention in mentions:
        pair = mention.strong_anchor()
        if pair is None:
            continue
        entry = directory_index.get(pair)
        if entry is not None:
            keys.add(entry.entity_key)
    if len(keys) == 1:
        return next(iter(keys))
    return None


def _separate_decision(
    *,
    rule_id: str,
    observation_ids: tuple[str, ...],
    reason_code: str,
) -> IdentityDecision:
    return IdentityDecision(
        opaque_id=decision_opaque_id(
            outcome=DecisionOutcome.SEPARATE.value,
            rule_id=rule_id,
            observation_ids=observation_ids,
        ),
        outcome=DecisionOutcome.SEPARATE,
        rule_id=rule_id,
        rule_version=POLICY_VERSION,
        observation_ids=observation_ids,
        reason_code=reason_code,
        evidence_refs=observation_ids,
    )


def _exclusive_conflict(
    by_id: Mapping[str, MentionEvidence],
    uf: _UnionFind,
    left: str,
    right: str,
) -> ContradictionConstraint | None:
    """Block merges that would unify distinct exclusive anchors of the same kind."""
    left_members = {obs for obs in by_id if obs in uf and uf.find(obs) == uf.find(left)}
    right_members = {obs for obs in by_id if obs in uf and uf.find(obs) == uf.find(right)}
    left_members.add(left)
    right_members.add(right)
    left_vals = _exclusive_values(by_id, left_members)
    right_vals = _exclusive_values(by_id, right_members)

    for kind in _EXCLUSIVE_PERSON_ANCHORS | _EXCLUSIVE_ACCOUNT_ANCHORS:
        left_set = left_vals.get(kind, set())
        right_set = right_vals.get(kind, set())
        if not left_set or not right_set:
            continue
        if left_set != right_set and left_set.isdisjoint(right_set) is False:
            combined = left_set | right_set
            if len(combined) > 1:
                return _make_conflict(kind, left_members, right_members)
        elif left_set.isdisjoint(right_set) and left_set and right_set:
            return _make_conflict(kind, left_members, right_members)
    return None


def _exclusive_values(
    by_id: Mapping[str, MentionEvidence],
    members: set[str],
) -> dict[AnchorKind, set[str]]:
    values: dict[AnchorKind, set[str]] = defaultdict(set)
    for obs_id in members:
        pair = by_id[obs_id].strong_anchor()
        if pair is None:
            continue
        kind, value = pair
        if kind in _EXCLUSIVE_PERSON_ANCHORS or kind in _EXCLUSIVE_ACCOUNT_ANCHORS:
            values[kind].add(value)
    return values


def _make_conflict(
    kind: AnchorKind,
    left_members: set[str],
    right_members: set[str],
) -> ContradictionConstraint:
    if kind is AnchorKind.EMPLOYEE_ID:
        reason = REASON_CONFLICTING_EMPLOYEE_ID
    elif kind is AnchorKind.ACCOUNT_ID:
        reason = REASON_CONFLICTING_ACCOUNT_ID
    else:
        reason = REASON_CONFLICTING_EMAIL
    left_sorted = tuple(sorted(left_members))
    right_sorted = tuple(sorted(right_members))
    return ContradictionConstraint(
        opaque_id=contradiction_opaque_id(
            left_key=",".join(left_sorted),
            right_key=",".join(right_sorted),
            reason_code=reason,
        ),
        reason_code=reason,
        left_observation_ids=left_sorted,
        right_observation_ids=right_sorted,
        detail=f"refusing merge that would unify distinct {kind.value} anchors",
    )
