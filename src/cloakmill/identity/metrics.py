"""Resolution metrics, including wrong-merge rate against held-out links."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from itertools import combinations

from cloakmill.domain.enums import DecisionOutcome
from cloakmill.identity.graph import AcceptedEntityGraph, ExceptionGroup, IdentityDecision


@dataclass(frozen=True, slots=True)
class ResolutionMetrics:
    """Aggregate counters for one resolution pass.

    ``wrong_merge_rate`` is only populated when ``expected_links`` are supplied
    by an eval harness. Runtime resolution never loads held-out fixtures.
    """

    mention_count: int
    accepted_entity_count: int
    accepted_decision_count: int
    separate_decision_count: int
    review_group_count: int
    unresolved_rate: float
    wrong_merge_count: int | None = None
    wrong_merge_rate: float | None = None
    expected_pair_count: int | None = None

    def to_dict(self) -> dict[str, int | float | None]:
        return {
            "mention_count": self.mention_count,
            "accepted_entity_count": self.accepted_entity_count,
            "accepted_decision_count": self.accepted_decision_count,
            "separate_decision_count": self.separate_decision_count,
            "review_group_count": self.review_group_count,
            "unresolved_rate": self.unresolved_rate,
            "wrong_merge_count": self.wrong_merge_count,
            "wrong_merge_rate": self.wrong_merge_rate,
            "expected_pair_count": self.expected_pair_count,
        }


def build_resolution_metrics(
    *,
    graph: AcceptedEntityGraph,
    decisions: Sequence[IdentityDecision],
    exceptions: Sequence[ExceptionGroup],
    total_mentions: int,
    expected_links: Sequence[Mapping[str, object]] | None = None,
) -> ResolutionMetrics:
    accepted = sum(1 for item in decisions if item.outcome is DecisionOutcome.ACCEPT)
    separate = sum(1 for item in decisions if item.outcome is DecisionOutcome.SEPARATE)
    review_obs = {obs_id for group in exceptions for obs_id in group.observation_ids}
    unresolved_rate = 0.0 if total_mentions == 0 else len(review_obs) / total_mentions

    wrong_merge_count: int | None = None
    wrong_merge_rate: float | None = None
    expected_pair_count: int | None = None
    if expected_links is not None:
        wrong_merge_count, expected_pair_count = score_wrong_merges(graph, expected_links)
        if expected_pair_count == 0:
            wrong_merge_rate = 0.0
        else:
            wrong_merge_rate = wrong_merge_count / expected_pair_count

    return ResolutionMetrics(
        mention_count=total_mentions,
        accepted_entity_count=len(graph.entities),
        accepted_decision_count=accepted,
        separate_decision_count=separate,
        review_group_count=len(exceptions),
        unresolved_rate=unresolved_rate,
        wrong_merge_count=wrong_merge_count,
        wrong_merge_rate=wrong_merge_rate,
        expected_pair_count=expected_pair_count,
    )


def score_wrong_merges(
    graph: AcceptedEntityGraph,
    expected_links: Sequence[Mapping[str, object]],
) -> tuple[int, int]:
    """Count predicted co-membership pairs that violate held-out link partitions.

    Expected links use the F02 shape: ``observation_ids`` per entity plus
    ``expected_decision`` of ``accept`` / ``abstain_review`` / ``keep_separate``.
    Only ``accept`` partitions contribute positive same-entity pairs. A wrong
    merge is any predicted pair whose observations belong to different accept
    entities, or that includes an observation marked ``keep_separate`` /
    ``abstain_review`` relative to its pair partner.
    """
    accept_groups: list[set[str]] = []
    non_merge_obs: set[str] = set()
    for link in expected_links:
        raw_ids = link.get("observation_ids", [])
        if not isinstance(raw_ids, list):
            continue
        obs_ids = {str(item) for item in raw_ids}
        decision = str(link.get("expected_decision", ""))
        if decision == "accept":
            accept_groups.append(obs_ids)
        else:
            non_merge_obs.update(obs_ids)

    truth_entity: dict[str, int] = {}
    for index, group in enumerate(accept_groups):
        for obs_id in group:
            truth_entity[obs_id] = index

    predicted_pairs = _predicted_pairs(graph)
    expected_pair_count = sum(len(group) * (len(group) - 1) // 2 for group in accept_groups)

    wrong = 0
    for left, right in predicted_pairs:
        left_truth = truth_entity.get(left)
        right_truth = truth_entity.get(right)
        if left in non_merge_obs or right in non_merge_obs:
            wrong += 1
            continue
        if left_truth is None or right_truth is None:
            # Observation absent from held-out accept set: treat co-membership
            # as a wrong merge when the partner has a known accept entity.
            if left_truth is not None or right_truth is not None:
                wrong += 1
            continue
        if left_truth != right_truth:
            wrong += 1

    return wrong, expected_pair_count


def _predicted_pairs(graph: AcceptedEntityGraph) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for entity in graph.entities:
        for left, right in combinations(sorted(entity.observation_ids), 2):
            pairs.append((left, right))
    return pairs
