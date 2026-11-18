"""Decision policy constants for strong-anchor identity resolution."""

from __future__ import annotations

POLICY_VERSION = "strong-anchor-v1"

RULE_STRONG_ANCHOR_MERGE = "identity.strong_anchor.merge"
RULE_DIRECTORY_BIND = "identity.directory.bind"
RULE_SHARED_ACCOUNT_SEPARATE = "identity.shared_account.separate"
RULE_KIND_SEPARATE = "identity.kind.separate"
RULE_CONFLICTING_ANCHORS = "identity.conflict.exclusive_anchors"
RULE_WEAK_NAME_REVIEW = "identity.weak.first_name.review"
RULE_COLOCATED_REVIEW = "identity.colocated.review"
RULE_SINGLETON_ACCEPT = "identity.singleton.accept"
RULE_NON_IDENTITY_SKIP = "identity.non_anchor.skip"

REASON_STRONG_ANCHOR_MATCH = "strong_anchor_match"
REASON_DIRECTORY_ENTITY = "directory_entity_bind"
REASON_SHARED_MAILBOX = "shared_mailbox_not_person_alias"
REASON_KIND_MISMATCH = "entity_kind_mismatch"
REASON_CONFLICTING_EMPLOYEE_ID = "conflicting_employee_id"
REASON_CONFLICTING_ACCOUNT_ID = "conflicting_account_id"
REASON_CONFLICTING_EMAIL = "conflicting_email"
REASON_WEAK_FIRST_NAME = "ambiguous_first_name_only"
REASON_COLOCATED_NEED_DIRECTORY = "colocated_anchors_need_directory"
REASON_SINGLETON = "singleton_strong_anchor"
REASON_NO_STRONG_ANCHOR = "no_strong_anchor"
