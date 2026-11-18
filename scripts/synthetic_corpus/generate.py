"""Generate raw corpora and held-out expected observations / identity links."""

from __future__ import annotations

import csv
import hashlib
import json
import random
from dataclasses import dataclass
from datetime import date, timedelta
from io import StringIO
from pathlib import Path
from typing import Any

from .constants import (
    CORPUS_SERIES,
    GENERATOR_VERSION,
    MASTER_SEED,
    ORGANIZATION_NAMES,
    RESERVED_EMAIL_DOMAINS,
    SIZES,
)
from .roster import OwnershipPeriod, Person, Roster, build_roster
from .schema import (
    SCHEMA_VERSION,
    field_path_locator,
    make_identity_link,
    make_observation,
    text_offset_locator,
    validate_identity_link,
    validate_observation,
)

ENGINE_INACCESSIBLE_MARKER = (
    "ENGINE_INACCESSIBLE\n"
    "Held-out evaluation expectations live here.\n"
    "Detection, identity, transforms, and pipeline runtime code must never import\n"
    "or load files from this directory.\n"
)


@dataclass(frozen=True, slots=True)
class CorpusSpec:
    size_key: str
    record_count: int
    seed: int
    source_version: str

    @classmethod
    def for_size(cls, size_key: str) -> CorpusSpec:
        if size_key not in SIZES:
            msg = f"unknown corpus size {size_key!r}; choose from {sorted(SIZES)}"
            raise ValueError(msg)
        return cls(
            size_key=size_key,
            record_count=SIZES[size_key],
            seed=MASTER_SEED + SIZES[size_key],
            source_version=f"{CORPUS_SERIES}-{size_key}",
        )


@dataclass(slots=True)
class _GenerationState:
    rng: random.Random
    roster: Roster
    spec: CorpusSpec
    observations: list[dict[str, Any]]
    obs_by_entity: dict[str, list[str]]
    next_obs: int
    next_part: int

    def observation_id(self) -> str:
        value = f"obs_{self.spec.size_key}_{self.next_obs:06d}"
        self.next_obs += 1
        return value

    def part_id(self, artifact: str, index: int) -> str:
        return f"part_{artifact}_{index:06d}"

    def track(self, obs: dict[str, Any]) -> None:
        validate_observation(obs)
        self.observations.append(obs)
        entity = obs["underlying_entity_ref"]
        self.obs_by_entity.setdefault(entity, []).append(obs["observation_id"])


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_text(text: str) -> str:
    return _sha256_bytes(text.encode("utf-8"))


def _person_full_name(person: Person) -> str:
    return f"{person.first_name} {person.last_name}"


def _period_covering(as_of: str, periods: tuple[OwnershipPeriod, ...]) -> OwnershipPeriod:
    """Return the ownership period whose inclusive date range contains ``as_of``."""
    for period in periods:
        if period.valid_from <= as_of and (period.valid_to is None or as_of <= period.valid_to):
            return period
    msg = f"no ownership period covers as_of={as_of!r}"
    raise ValueError(msg)


def _distinct_mention(author: Person, people: tuple[Person, ...], index: int) -> Person:
    """Pick a cross-mention person that is never the author (avoids collapsed spans)."""
    mention = people[(index * 5) % len(people)]
    if mention.entity_id == author.entity_id:
        mention = people[(index * 5 + 1) % len(people)]
    if index % 11 == 0:
        same_first = [p for p in people[:12] if p.first_name == author.first_name]
        if len(same_first) >= 2:
            mention = same_first[(index // 11) % len(same_first)]
            if mention.entity_id == author.entity_id:
                mention = same_first[(index // 11 + 1) % len(same_first)]
    if mention.entity_id == author.entity_id:
        msg = f"failed to select distinct mention for author {author.entity_id}"
        raise RuntimeError(msg)
    return mention


def _span_in_region(haystack: str, needle: str, *, region_start: int) -> tuple[int, int]:
    """Locate ``needle`` at or after ``region_start`` (codepoint offsets)."""
    local = haystack.index(needle, region_start)
    return local, local + len(needle)


def _assert_reserved_domains(text: str) -> None:
    """Reject accidental non-example domains in generated payloads."""
    lowered = text.lower()
    # Allow only reserved domains when an @-address appears.
    for token in lowered.replace("<", " ").replace(">", " ").replace(",", " ").split():
        if "@" not in token:
            continue
        domain = token.rsplit("@", 1)[-1].strip(".,;:\"'()[]<>")
        if domain and not domain.endswith(".example") and domain not in RESERVED_EMAIL_DOMAINS:
            msg = f"non-reserved email domain in corpus text: {domain}"
            raise ValueError(msg)


def _generate_contacts(state: _GenerationState) -> tuple[str, list[dict[str, str]]]:
    """CSV contacts: repeated owners, shared mailbox, ownership-period rows."""
    artifact = "contacts_csv"
    relative = "raw/contacts.csv"
    rows: list[dict[str, str]] = []
    people = state.roster.people
    accounts = [a for a in state.roster.accounts if a.kind == "customer"]
    target = max(1, state.spec.record_count // 2)

    for index in range(target):
        person = people[index % len(people)]
        account = accounts[index % len(accounts)]
        # Re-emit early people often so repeated-mention density stays high.
        if index % 7 == 0:
            person = people[index % min(20, len(people))]
        row = {
            "row_id": f"C-{index:05d}",
            "full_name": _person_full_name(person),
            "email": person.email,
            "employee_id": person.employee_id,
            "organization": person.organization,
            "account_id": account.account_id,
            "owner_email": person.email,
            "as_of_date": (date(2024, 1, 1) + timedelta(days=index % 365)).isoformat(),
        }
        rows.append(row)
        base_tags = ("repeated_mention",) if index % 7 == 0 else ()
        person_tags = tuple(dict.fromkeys((*person.tags, *base_tags)))

        field_specs: list[tuple[str, str, str, tuple[str, ...]]] = [
            ("full_name", "person_name", person.entity_id, person_tags),
            ("email", "email_address", person.entity_id, person_tags),
            ("employee_id", "employee_id", person.entity_id, person_tags),
            ("organization", "organization_name", f"entity:org:{person.organization}", ()),
            ("account_id", "account_id", account.entity_id, ("customer_account",)),
            ("owner_email", "email_address", person.entity_id, person_tags),
        ]
        for field_name, entity_type, entity_ref, tags in field_specs:
            state.track(
                make_observation(
                    observation_id=state.observation_id(),
                    artifact_opaque_id=artifact,
                    source_version=state.spec.source_version,
                    relative_path=relative,
                    part_id=state.part_id(artifact, index),
                    surface_kind="structured_field",
                    coverage_state="complete",
                    entity_type=entity_type,  # type: ignore[arg-type]
                    evidence_locator=field_path_locator(f"rows[{index}].{field_name}"),
                    evidence_text=row[field_name],
                    underlying_entity_ref=entity_ref,
                    case_tags=tags,
                    recognizer_version=GENERATOR_VERSION,
                )
            )

    # Ownership-change rows for the recycled mailbox.
    for period_index, period in enumerate(state.roster.ownership_periods):
        owner = next(p for p in people if p.entity_id == period.owner_entity_id)
        index = len(rows)
        row = {
            "row_id": f"C-OWN-{period_index:02d}",
            "full_name": _person_full_name(owner),
            "email": period.mailbox,
            "employee_id": owner.employee_id,
            "organization": owner.organization,
            "account_id": "MBX-OPS",
            "owner_email": period.mailbox,
            "as_of_date": period.valid_from,
        }
        rows.append(row)
        for field_name, entity_type, entity_ref, tags in (
            ("full_name", "person_name", owner.entity_id, period.tags),
            ("email", "email_address", owner.entity_id, period.tags),
            ("owner_email", "email_address", owner.entity_id, period.tags),
            ("employee_id", "employee_id", owner.entity_id, period.tags),
        ):
            state.track(
                make_observation(
                    observation_id=state.observation_id(),
                    artifact_opaque_id=artifact,
                    source_version=state.spec.source_version,
                    relative_path=relative,
                    part_id=state.part_id(artifact, index),
                    surface_kind="structured_field",
                    coverage_state="complete",
                    entity_type=entity_type,  # type: ignore[arg-type]
                    evidence_locator=field_path_locator(f"rows[{index}].{field_name}"),
                    evidence_text=row[field_name],
                    underlying_entity_ref=entity_ref,
                    case_tags=tags,
                    recognizer_version=GENERATOR_VERSION,
                )
            )

    # Shared mailbox row (mailbox entity distinct from operator people).
    index = len(rows)
    row = {
        "row_id": "C-SHARED-00",
        "full_name": "Support Desk",
        "email": state.roster.shared_mailbox,
        "employee_id": "MBX-SUPPORT",
        "organization": ORGANIZATION_NAMES[0],
        "account_id": "MBX-SUPPORT",
        "owner_email": state.roster.shared_mailbox,
        "as_of_date": "2024-06-01",
    }
    rows.append(row)
    state.track(
        make_observation(
            observation_id=state.observation_id(),
            artifact_opaque_id=artifact,
            source_version=state.spec.source_version,
            relative_path=relative,
            part_id=state.part_id(artifact, index),
            surface_kind="structured_field",
            coverage_state="complete",
            entity_type="shared_mailbox",
            evidence_locator=field_path_locator(f"rows[{index}].email"),
            evidence_text=row["email"],
            underlying_entity_ref="entity:account:shared_support",
            case_tags=("shared_mailbox", "do_not_merge_operators"),
            recognizer_version=GENERATOR_VERSION,
        )
    )
    # Operators mentioned in a note field would be free text; keep CSV clean.

    fieldnames = list(rows[0].keys())
    stream = StringIO()
    writer = csv.DictWriter(stream, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    text = stream.getvalue()
    _assert_reserved_domains(text)
    return text, rows


def _generate_messages(state: _GenerationState) -> str:
    """JSON messages with authors, ambiguity, and ownership-period context."""
    artifact = "messages_json"
    relative = "raw/messages.json"
    people = state.roster.people
    target = max(1, state.spec.record_count // 3)
    messages: list[dict[str, Any]] = []

    for index in range(target):
        author = people[index % len(people)]
        mention = _distinct_mention(author, people, index)

        as_of = (date(2022, 1, 1) + timedelta(days=index % 900)).isoformat()
        body = (
            f"{author.first_name} ({author.email}) asked about account "
            f"AC-{(1000 + (index % 50)):d}. Also loop in {mention.first_name} "
            f"{mention.last_name} <{mention.email}>."
        )
        period: OwnershipPeriod | None = None
        if index % 17 == 0:
            period = _period_covering(as_of, state.roster.ownership_periods)
            body += f" Ops desk address in effect: {period.mailbox} (as of {as_of})."

        if index % 23 == 0:
            body += f" CC shared support: {state.roster.shared_mailbox}."

        message = {
            "message_id": f"M-{index:05d}",
            "thread_id": f"T-{index // 4:05d}",
            "sent_at": as_of,
            "author_name": _person_full_name(author),
            "author_email": author.email,
            "body": body,
        }
        messages.append(message)

        for field_name, entity_type, entity_ref, tags in (
            ("author_name", "person_name", author.entity_id, author.tags),
            ("author_email", "email_address", author.entity_id, author.tags),
        ):
            state.track(
                make_observation(
                    observation_id=state.observation_id(),
                    artifact_opaque_id=artifact,
                    source_version=state.spec.source_version,
                    relative_path=relative,
                    part_id=state.part_id(artifact, index),
                    surface_kind="structured_field",
                    coverage_state="complete",
                    entity_type=entity_type,  # type: ignore[arg-type]
                    evidence_locator=field_path_locator(f"messages[{index}].{field_name}"),
                    evidence_text=message[field_name],
                    underlying_entity_ref=entity_ref,
                    case_tags=tags,
                    recognizer_version=GENERATOR_VERSION,
                )
            )

        # Author email appears first; mention spans are searched after "Also loop in ".
        mention_region = body.index("Also loop in ")
        author_start = body.index(author.email)
        author_end = author_start + len(author.email)
        state.track(
            make_observation(
                observation_id=state.observation_id(),
                artifact_opaque_id=artifact,
                source_version=state.spec.source_version,
                relative_path=relative,
                part_id=state.part_id(artifact, index),
                surface_kind="plain_text",
                coverage_state="complete",
                entity_type="email_address",
                evidence_locator=text_offset_locator(start=author_start, end=author_end),
                evidence_text=author.email,
                underlying_entity_ref=author.entity_id,
                case_tags=(*author.tags, "in_body"),
                recognizer_version=GENERATOR_VERSION,
            )
        )
        for evidence_text, entity_type, entity_ref, body_tags in (
            (
                _person_full_name(mention),
                "person_name",
                mention.entity_id,
                (*mention.tags, "in_body", "cross_mention"),
            ),
            (
                mention.email,
                "email_address",
                mention.entity_id,
                (*mention.tags, "in_body", "cross_mention"),
            ),
        ):
            start, end = _span_in_region(body, evidence_text, region_start=mention_region)
            state.track(
                make_observation(
                    observation_id=state.observation_id(),
                    artifact_opaque_id=artifact,
                    source_version=state.spec.source_version,
                    relative_path=relative,
                    part_id=state.part_id(artifact, index),
                    surface_kind="plain_text",
                    coverage_state="complete",
                    entity_type=entity_type,  # type: ignore[arg-type]
                    evidence_locator=text_offset_locator(start=start, end=end),
                    evidence_text=evidence_text,
                    underlying_entity_ref=entity_ref,
                    case_tags=body_tags,
                    recognizer_version=GENERATOR_VERSION,
                )
            )

        if period is not None:
            start = body.index(period.mailbox)
            end = start + len(period.mailbox)
            state.track(
                make_observation(
                    observation_id=state.observation_id(),
                    artifact_opaque_id=artifact,
                    source_version=state.spec.source_version,
                    relative_path=relative,
                    part_id=state.part_id(artifact, index),
                    surface_kind="plain_text",
                    coverage_state="complete",
                    entity_type="email_address",
                    evidence_locator=text_offset_locator(start=start, end=end),
                    evidence_text=period.mailbox,
                    underlying_entity_ref=period.owner_entity_id,
                    case_tags=period.tags,
                    recognizer_version=GENERATOR_VERSION,
                )
            )

        if index % 23 == 0:
            start = body.index(state.roster.shared_mailbox)
            end = start + len(state.roster.shared_mailbox)
            state.track(
                make_observation(
                    observation_id=state.observation_id(),
                    artifact_opaque_id=artifact,
                    source_version=state.spec.source_version,
                    relative_path=relative,
                    part_id=state.part_id(artifact, index),
                    surface_kind="plain_text",
                    coverage_state="complete",
                    entity_type="shared_mailbox",
                    evidence_locator=text_offset_locator(start=start, end=end),
                    evidence_text=state.roster.shared_mailbox,
                    underlying_entity_ref="entity:account:shared_support",
                    case_tags=("shared_mailbox", "do_not_merge_operators"),
                    recognizer_version=GENERATOR_VERSION,
                )
            )

    payload = {
        "schema_version": SCHEMA_VERSION,
        "corpus": state.spec.source_version,
        "messages": messages,
    }
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    _assert_reserved_domains(text)
    return text


def _generate_notes(state: _GenerationState) -> str:
    """Free-text notes with repeated people and intentional name collisions."""
    artifact = "notes_txt"
    relative = "raw/notes.txt"
    people = state.roster.people
    # Remainder after contacts (~1/2) and messages (~1/3) allocations.
    allocated = (state.spec.record_count // 2) + (state.spec.record_count // 3)
    target = max(1, state.spec.record_count - allocated)
    lines: list[str] = [
        f"# Synthetic notes for {state.spec.source_version}",
        "# Fictional content; reserved .example domains only.",
        "",
    ]
    # Track absolute codepoint offsets across the growing document.
    cursor = sum(len(line) + 1 for line in lines)

    for index in range(target):
        person = people[index % len(people)]
        peer = people[(index * 3 + 1) % len(people)]
        line = (
            f"Note {index:05d}: Follow up with {_person_full_name(person)} "
            f"({person.email}, {person.employee_id}) and {_person_full_name(peer)}."
        )
        if index % 9 == 0:
            # Ambiguous first-name-only mention — expected abstain case.
            line += f" Someone named {person.first_name} also replied on the thread."
        if index % 19 == 0:
            period = state.roster.ownership_periods[0]
            line += f" Historical ops contact: {period.mailbox}."
        lines.append(line)

        spans: list[tuple[str, str, str, tuple[str, ...]]] = [
            (
                _person_full_name(person),
                "person_name",
                person.entity_id,
                person.tags,
            ),
            (person.email, "email_address", person.entity_id, person.tags),
            (person.employee_id, "employee_id", person.entity_id, person.tags),
            (
                _person_full_name(peer),
                "person_name",
                peer.entity_id,
                (*peer.tags, "cross_mention"),
            ),
        ]
        for evidence_text, entity_type, entity_ref, tags in spans:
            local_start = line.index(evidence_text)
            start = cursor + local_start
            end = start + len(evidence_text)
            state.track(
                make_observation(
                    observation_id=state.observation_id(),
                    artifact_opaque_id=artifact,
                    source_version=state.spec.source_version,
                    relative_path=relative,
                    part_id=state.part_id(artifact, index),
                    surface_kind="plain_text",
                    coverage_state="complete",
                    entity_type=entity_type,  # type: ignore[arg-type]
                    evidence_locator=text_offset_locator(start=start, end=end),
                    evidence_text=evidence_text,
                    underlying_entity_ref=entity_ref,
                    case_tags=tags,
                    recognizer_version=GENERATOR_VERSION,
                )
            )

        if index % 9 == 0:
            # First-name-only: link expectation will be abstain_review.
            evidence_text = person.first_name
            # Find the trailing ambiguous mention, not the full-name occurrence.
            local_start = line.rindex(f"named {person.first_name}") + len("named ")
            start = cursor + local_start
            end = start + len(evidence_text)
            state.track(
                make_observation(
                    observation_id=state.observation_id(),
                    artifact_opaque_id=artifact,
                    source_version=state.spec.source_version,
                    relative_path=relative,
                    part_id=state.part_id(artifact, index),
                    surface_kind="plain_text",
                    coverage_state="complete",
                    entity_type="person_name",
                    evidence_locator=text_offset_locator(start=start, end=end),
                    evidence_text=evidence_text,
                    underlying_entity_ref=person.entity_id,
                    case_tags=("shared_first_name", "first_name_only", "ambiguous"),
                    recognizer_version=GENERATOR_VERSION,
                )
            )

        if index % 19 == 0:
            period = state.roster.ownership_periods[0]
            local_start = line.index(period.mailbox)
            start = cursor + local_start
            end = start + len(period.mailbox)
            state.track(
                make_observation(
                    observation_id=state.observation_id(),
                    artifact_opaque_id=artifact,
                    source_version=state.spec.source_version,
                    relative_path=relative,
                    part_id=state.part_id(artifact, index),
                    surface_kind="plain_text",
                    coverage_state="complete",
                    entity_type="email_address",
                    evidence_locator=text_offset_locator(start=start, end=end),
                    evidence_text=period.mailbox,
                    underlying_entity_ref=period.owner_entity_id,
                    case_tags=period.tags,
                    recognizer_version=GENERATOR_VERSION,
                )
            )

        cursor += len(line) + 1

    text = "\n".join(lines) + "\n"
    _assert_reserved_domains(text)
    return text


def _build_identity_links(state: _GenerationState) -> list[dict[str, Any]]:
    links: list[dict[str, Any]] = []
    link_index = 0

    def next_link_id() -> str:
        nonlocal link_index
        value = f"link_{state.spec.size_key}_{link_index:05d}"
        link_index += 1
        return value

    obs_by_id = {o["observation_id"]: o for o in state.observations}

    # Strong-anchor accept links for people with employee/email observations.
    for person in state.roster.people:
        obs_ids: list[str] = []
        for oid in state.obs_by_entity.get(person.entity_id, []):
            tags = set(obs_by_id[oid].get("case_tags", []))
            if tags & {"first_name_only", "ambiguous"}:
                continue
            obs_ids.append(oid)
        if not obs_ids:
            continue
        links.append(
            make_identity_link(
                link_id=next_link_id(),
                entity_id=person.entity_id,
                entity_kind="person",
                observation_ids=obs_ids,
                expected_decision="accept",
                case_tags=("strong_anchor", *person.tags),
            )
        )

    # Ambiguous first-name-only observations → abstain.
    ambiguous_obs = [
        o
        for o in state.observations
        if "first_name_only" in o.get("case_tags", []) or "ambiguous" in o.get("case_tags", [])
    ]
    if ambiguous_obs:
        # Group by first-name surface text for review clusters.
        by_name: dict[str, list[str]] = {}
        for obs in ambiguous_obs:
            by_name.setdefault(obs["evidence_text"], []).append(obs["observation_id"])
        for name, obs_ids in sorted(by_name.items()):
            related = tuple(
                sorted(
                    {
                        o["underlying_entity_ref"]
                        for o in ambiguous_obs
                        if o["evidence_text"] == name
                    }
                )
            )
            links.append(
                make_identity_link(
                    link_id=next_link_id(),
                    entity_id=f"entity:ambiguous_cluster:{name.lower()}",
                    entity_kind="person",
                    observation_ids=obs_ids,
                    expected_decision="abstain_review",
                    case_tags=("shared_first_name", "first_name_only", "ambiguous"),
                    related_entity_ids=related,
                )
            )

    # Ownership periods: same mailbox, different owners across time → keep_separate.
    for period in state.roster.ownership_periods:
        obs_ids = [
            o["observation_id"]
            for o in state.observations
            if o["evidence_text"] == period.mailbox
            and o["underlying_entity_ref"] == period.owner_entity_id
        ]
        links.append(
            make_identity_link(
                link_id=next_link_id(),
                entity_id=period.owner_entity_id,
                entity_kind="person",
                observation_ids=obs_ids,
                expected_decision="accept",
                case_tags=period.tags,
                ownership_period={
                    "mailbox": period.mailbox,
                    "valid_from": period.valid_from,
                    "valid_to": period.valid_to,
                },
            )
        )
    # Explicit keep_separate between the two owners of the recycled mailbox.
    prior, current = state.roster.ownership_periods
    links.append(
        make_identity_link(
            link_id=next_link_id(),
            entity_id=prior.owner_entity_id,
            entity_kind="person",
            observation_ids=[],
            expected_decision="keep_separate",
            case_tags=("ownership_change", "distinct_owners"),
            related_entity_ids=(current.owner_entity_id,),
            ownership_period={
                "mailbox": prior.mailbox,
                "valid_from": prior.valid_from,
                "valid_to": prior.valid_to,
            },
        )
    )

    # Shared mailbox must not merge into operators.
    shared_obs = [
        o["observation_id"]
        for o in state.observations
        if o["underlying_entity_ref"] == "entity:account:shared_support"
    ]
    links.append(
        make_identity_link(
            link_id=next_link_id(),
            entity_id="entity:account:shared_support",
            entity_kind="mailbox",
            observation_ids=shared_obs,
            expected_decision="keep_separate",
            case_tags=("shared_mailbox", "do_not_merge_operators"),
            related_entity_ids=state.roster.shared_mailbox_operator_ids,
        )
    )

    # Customer accounts.
    for account in state.roster.accounts:
        if account.kind != "customer":
            continue
        obs_ids = state.obs_by_entity.get(account.entity_id, [])
        if not obs_ids:
            continue
        links.append(
            make_identity_link(
                link_id=next_link_id(),
                entity_id=account.entity_id,
                entity_kind="account",
                observation_ids=list(obs_ids),
                expected_decision="accept",
                case_tags=account.tags,
            )
        )

    for link in links:
        validate_identity_link(link)
    return links


def generate_corpus(spec: CorpusSpec) -> dict[str, Any]:
    """Generate in-memory corpus artifacts and held-out expectations."""
    rng = random.Random(spec.seed)
    # Roster scales with corpus size but stays bounded for ambiguity coverage.
    person_count = 48 if spec.size_key == "1k" else 120
    roster = build_roster(person_count=person_count, seed_label=spec.source_version)
    state = _GenerationState(
        rng=rng,
        roster=roster,
        spec=spec,
        observations=[],
        obs_by_entity={},
        next_obs=0,
        next_part=0,
    )

    contacts_text, _rows = _generate_contacts(state)
    messages_text = _generate_messages(state)
    notes_text = _generate_notes(state)
    links = _build_identity_links(state)

    raw_files = {
        "raw/contacts.csv": contacts_text,
        "raw/messages.json": messages_text,
        "raw/notes.txt": notes_text,
    }
    digests = {path: _sha256_text(content) for path, content in raw_files.items()}

    observations_lines = [json.dumps(o, sort_keys=True) for o in state.observations]
    links_lines = [json.dumps(link, sort_keys=True) for link in links]
    expected_observations_text = "\n".join(observations_lines) + "\n"
    expected_links_text = "\n".join(links_lines) + "\n"

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "generator_version": GENERATOR_VERSION,
        "corpus_series": CORPUS_SERIES,
        "size_key": spec.size_key,
        "record_count_target": spec.record_count,
        "source_version": spec.source_version,
        "seed": spec.seed,
        "reserved_email_domains": list(RESERVED_EMAIL_DOMAINS),
        "person_count": len(roster.people),
        "account_count": len(roster.accounts),
        "observation_count": len(state.observations),
        "identity_link_count": len(links),
        "raw_files": digests,
        "scenarios": [
            "repeated_people",
            "shared_first_name_ambiguity",
            "shared_mailbox_operators",
            "email_ownership_change",
        ],
        "held_out": {
            "expected_observations": "expected/expected_observations.jsonl",
            "expected_identity_links": "expected/expected_identity_links.jsonl",
            "engine_accessible": False,
        },
    }
    manifest_text = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    digests["manifest.json"] = _sha256_text(manifest_text)
    digests["expected/expected_observations.jsonl"] = _sha256_text(expected_observations_text)
    digests["expected/expected_identity_links.jsonl"] = _sha256_text(expected_links_text)

    digest_doc = {
        "schema_version": SCHEMA_VERSION,
        "source_version": spec.source_version,
        "files": digests,
    }

    return {
        "spec": spec,
        "manifest": manifest,
        "manifest_text": manifest_text,
        "raw_files": raw_files,
        "expected_observations_text": expected_observations_text,
        "expected_links_text": expected_links_text,
        "digest_doc": digest_doc,
        "observations": state.observations,
        "links": links,
    }


def write_corpus(
    *,
    spec: CorpusSpec,
    examples_root: Path,
    fixtures_root: Path,
) -> dict[str, Any]:
    """Write raw corpus under examples/ and held-out expectations under fixtures/."""
    generated = generate_corpus(spec)
    corpus_dir = examples_root / CORPUS_SERIES / spec.size_key
    raw_dir = corpus_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    for relative, content in generated["raw_files"].items():
        path = corpus_dir / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    (corpus_dir / "manifest.json").write_text(generated["manifest_text"], encoding="utf-8")
    (corpus_dir / "DIGESTS.json").write_text(
        json.dumps(generated["digest_doc"], indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (corpus_dir / "README.md").write_text(
        _corpus_readme(spec),
        encoding="utf-8",
    )

    expected_dir = fixtures_root / CORPUS_SERIES / spec.size_key
    expected_dir.mkdir(parents=True, exist_ok=True)
    (expected_dir / "expected_observations.jsonl").write_text(
        generated["expected_observations_text"],
        encoding="utf-8",
    )
    (expected_dir / "expected_identity_links.jsonl").write_text(
        generated["expected_links_text"],
        encoding="utf-8",
    )
    (expected_dir / "DIGESTS.json").write_text(
        json.dumps(generated["digest_doc"], indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (fixtures_root / "ENGINE_INACCESSIBLE").write_text(ENGINE_INACCESSIBLE_MARKER, encoding="utf-8")
    (fixtures_root / "README.md").write_text(_fixtures_readme(), encoding="utf-8")

    generated["corpus_dir"] = corpus_dir
    generated["expected_dir"] = expected_dir
    return generated


def _corpus_readme(spec: CorpusSpec) -> str:
    return f"""# Synthetic corpus `{spec.source_version}`

Fictional raw inputs for CloakMill evaluation. Reserved `.example` domains only.

- `raw/contacts.csv` — structured contacts with repeated people and ownership rows
- `raw/messages.json` — message threads with cross-mentions and shared mailboxes
- `raw/notes.txt` — free-text notes with ambiguous first-name mentions
- `manifest.json` / `DIGESTS.json` — provenance and SHA-256 digests

Held-out expected observations and identity links are **not** stored here.
They live under `tests/fixtures/eval/` and must never be imported by detection code.

Regenerate with:

```bash
uv run python -m scripts.synthetic_corpus --size {spec.size_key}
```
"""


def _fixtures_readme() -> str:
    return """# Held-out evaluation expectations

These files are the complete expected observations and identity links for the
synthetic corpora under `examples/synthetic/corpora/`.

**Engine-inaccessible:** detection, identity resolution, transforms, and pipeline
runtime code must never import or load this directory. Eval harnesses and tests
may read it.

The 10k `expected_observations.jsonl` blob is gitignored (see `DIGESTS.json` for
its SHA-256). Regenerate with `uv run python -m scripts.synthetic_corpus --size 10k`.

See `docs/development/synthetic-eval-corpora.md`.
"""
