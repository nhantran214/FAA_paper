# Migration of the retired tests (ruling Q7)

Sub-project B retired the old CASE-0031 runtime (`tonomyx/{api,canon,flow,de,policy}`, the old
tool registry and repository, `tonomyx/cli.py`) and the old `aebench` harness. This file maps
every test of the retired code to what covers the same behaviour now. The retired code and its
tests stay readable at the tag `tonomyx-v1-paper` of the FAA repository, not in this repository.

Reading notes for the paper copy (`FAA_paper`):

- The table was written in FAA. This copy kept only the tests of the engine, the contracts,
  the models and the new harness. A covering test marked `[not in this copy]` still exists in
  FAA but was not taken over.
- The five re-implemented baseline guards (`LlmJudgeGuard`, `LlamaGuard3Guard`,
  `NeMoGuardrailsGuard`, `AgentDojoGuard`, `CaMeLGuard`) were replaced by bridges to the
  authors' original code. Their old tests map to `tests/aebench/bridges/` and
  `tests/aebench/test_defence.py`. The `llm-guard` arm no longer exists (see
  `baselines/README.md`).
- The CASE-0031 canon pack, its governance and its converter live in `tests/fixtures/`.

## Dispositions

| Disposition | Meaning |
|---|---|
| covered | A test of the generic engine checks the same behaviour; named as `path::name`. |
| new test (Task 1) | No test covered the behaviour, so Task 1 added one on the generic engine. |
| CASE-0031 only | The behaviour belongs to the CASE-0031 canon pack, its data, scenarios, playbooks, attacks or experiments. Where a generic counterpart exists it is named. |
| rebuilt by a later task | A harness component (model executor, guards, scores, runner, tool schemas) that a named task of the evaluation plan rebuilds on the generic engine, with the test the plan names. Not CASE-0031-specific, but there is no generic code to test until that task lands. |
| not carried | A generic feature of the old runtime that the generic engine does not have (idempotency keys, the HTTP API, the NemoClaw executor, field selection, knowledge domains, the database-tier reconciliation check at payment). Listed for the lead. |
| moved | The test still exists, at the path named, because the code it tests survived. |

## Statistics

54 retired test files (two of them conftests with no tests), 364 test functions.

| Disposition | Tests |
|---|---:|
| covered | 119 |
| new test (Task 1) | 14 |
| CASE-0031 only | 161 |
| rebuilt by a later task | 31 |
| not carried | 24 |
| moved | 15 |
| **total** | **364** |

Not listed because they test surviving code and stay where they were:
`tests/aebench/test_stats.py` (12 tests, `aebench/analysis/stats.py`) and
`tests/contracts/test_token.py` (9 tests, `tonomyx/contracts/token.py`).

## Tests added by Task 1

| New test | Behaviour carried over |
|---|---|
| `tests/tools_core/test_context.py::test_every_tool_checks_its_own_name_against_the_token` | every tool a task token can carry refuses a token without its name, and writes nothing (11 cases) |
| `tests/tools_core/test_context.py::test_the_token_tool_list_names_every_tool_but_decide` | the case list above stays complete when a tool is added |
| `tests/tools_core/test_records.py::test_an_unknown_or_injected_table_name_is_refused` | table names come from the core schema only, so an injected name is refused (3 cases) |
| `tests/tools_core/test_approvals.py::test_an_existing_approval_id_is_never_reused` | a request under a taken approval id opens nothing |
| `tests/tools_core/test_approvals.py::test_deciding_an_unknown_approval_is_refused` | a decision on an approval that does not exist is refused and records nothing |
| `tests/tools_core/test_documents.py::test_a_zero_item_cap_allows_no_discount` | a discount cap set to zero is a cap, not a missing one |
| `tests/tools_core/test_documents.py::test_an_explicit_null_unit_price_is_accepted` | an explicit null price is accepted as unknown and leaves the totals unknown |
| `tests/tools_core/test_settlement.py::test_a_failed_send_reports_no_success_and_records_no_event` | a failed send raises and leaves no SENT event |
| `tests/tools_core/test_settlement.py::test_reconcile_never_edits_its_sources` | reconcile changes only ket_qua of the reconciled document |

## Per file

| Retired file | Tests | covered | new | CASE-0031 only | rebuilt | not carried | moved |
|---|---:|---:|---:|---:|---:|---:|---:|
| `tests/api/test_app.py` | 18 | 3 | 1 | 6 | 0 | 8 | 0 |
| `tests/canon/test_invariants.py` | 7 | 2 | 0 | 5 | 0 | 0 | 0 |
| `tests/canon/test_pack.py` | 10 | 1 | 0 | 9 | 0 | 0 | 0 |
| `tests/contracts/test_envelope.py` | 7 | 2 | 0 | 5 | 0 | 0 | 0 |
| `tests/db/test_bootstrap.py` | 6 | 4 | 0 | 2 | 0 | 0 | 0 |
| `tests/db/test_guardrails_both_paths.py` | 8 | 7 | 0 | 0 | 0 | 1 | 0 |
| `tests/db/test_invariants_on_postgres.py` | 2 | 1 | 0 | 1 | 0 | 0 | 0 |
| `tests/db/test_repo.py` | 10 | 6 | 2 | 0 | 0 | 2 | 0 |
| `tests/de/test_executor.py` | 8 | 2 | 0 | 0 | 1 | 5 | 0 |
| `tests/de/test_ollama_executor.py` | 18 | 5 | 1 | 4 | 8 | 0 | 0 |
| `tests/de/test_runtime.py` | 10 | 8 | 0 | 2 | 0 | 0 | 0 |
| `tests/de/test_scope.py` | 6 | 2 | 0 | 4 | 0 | 0 | 0 |
| `tests/flow/test_case_0031.py` | 11 | 4 | 0 | 7 | 0 | 0 | 0 |
| `tests/flow/test_golden_reproduction.py` | 4 | 1 | 0 | 3 | 0 | 0 | 0 |
| `tests/flow/test_playbooks.py` | 5 | 0 | 0 | 5 | 0 | 0 | 0 |
| `tests/flow/test_scenarios.py` | 7 | 3 | 0 | 4 | 0 | 0 | 0 |
| `tests/policy/test_agrees_with_postgres.py` | 3 | 0 | 0 | 3 | 0 | 0 | 0 |
| `tests/policy/test_rego_conformance.py` | 5 | 0 | 0 | 5 | 0 | 0 | 0 |
| `tests/policy/test_rules.py` | 10 | 7 | 0 | 3 | 0 | 0 | 0 |
| `tests/policy/test_store.py` | 2 | 0 | 1 | 1 | 0 | 0 | 0 |
| `tests/tools/test_catalog.py` | 2 | 0 | 0 | 2 | 0 | 0 | 0 |
| `tests/tools/test_create_approval.py` | 7 | 3 | 1 | 2 | 0 | 1 | 0 |
| `tests/tools/test_decide_approval.py` | 10 | 8 | 0 | 0 | 0 | 2 | 0 |
| `tests/tools/test_least_privilege.py` | 6 | 2 | 4 | 0 | 0 | 0 | 0 |
| `tests/tools/test_log_event.py` | 6 | 5 | 0 | 1 | 0 | 0 | 0 |
| `tests/tools/test_match_three_way.py` | 7 | 3 | 1 | 3 | 0 | 0 | 0 |
| `tests/tools/test_read_records.py` | 4 | 3 | 0 | 0 | 0 | 1 | 0 |
| `tests/tools/test_registry.py` | 6 | 3 | 0 | 2 | 0 | 1 | 0 |
| `tests/tools/test_schema.py` | 7 | 0 | 0 | 1 | 6 | 0 | 0 |
| `tests/tools/test_search_kb.py` | 5 | 2 | 0 | 2 | 0 | 1 | 0 |
| `tests/tools/test_send_email.py` | 6 | 4 | 2 | 0 | 0 | 0 | 0 |
| `tests/tools/test_update_status.py` | 10 | 7 | 1 | 2 | 0 | 0 | 0 |
| `tests/tools/test_write_draft.py` | 7 | 5 | 0 | 0 | 0 | 2 | 0 |
| `tests/test_cli.py` | 12 | 1 | 0 | 11 | 0 | 0 | 0 |
| `tests/aebench/conftest.py` | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| `tests/tools/conftest.py` | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| `tests/aebench/test_agent.py` | 9 | 0 | 0 | 6 | 3 | 0 | 0 |
| `tests/aebench/test_attacks_extended.py` | 7 | 0 | 0 | 7 | 0 | 0 | 0 |
| `tests/aebench/test_baselines.py` | 10 | 0 | 0 | 0 | 10 | 0 | 0 |
| `tests/aebench/test_benign.py` | 6 | 0 | 0 | 2 | 4 | 0 | 0 |
| `tests/aebench/test_bpic19.py` | 2 | 0 | 0 | 2 | 0 | 0 | 0 |
| `tests/aebench/test_cases.py` | 4 | 0 | 0 | 4 | 0 | 0 | 0 |
| `tests/aebench/test_composition.py` | 8 | 0 | 0 | 8 | 0 | 0 | 0 |
| `tests/aebench/test_experiment_schedule.py` | 20 | 0 | 0 | 13 | 4 | 0 | 3 |
| `tests/aebench/test_frontier_llm.py` | 10 | 0 | 0 | 0 | 0 | 0 | 10 |
| `tests/aebench/test_hardening.py` | 4 | 3 | 0 | 1 | 0 | 0 | 0 |
| `tests/aebench/test_hr_postgres.py` | 2 | 0 | 0 | 2 | 0 | 0 | 0 |
| `tests/aebench/test_hr_process.py` | 4 | 0 | 0 | 4 | 0 | 0 | 0 |
| `tests/aebench/test_i18n.py` | 8 | 0 | 0 | 8 | 0 | 0 | 0 |
| `tests/aebench/test_interception.py` | 6 | 0 | 0 | 0 | 6 | 0 | 0 |
| `tests/aebench/test_oracle.py` | 5 | 1 | 0 | 4 | 0 | 0 | 0 |
| `tests/aebench/test_quality.py` | 2 | 0 | 0 | 0 | 0 | 0 | 2 |
| `tests/aebench/test_reference_process.py` | 2 | 0 | 0 | 2 | 0 | 0 | 0 |
| `tests/aebench/test_structural_matrix.py` | 3 | 0 | 0 | 3 | 0 | 0 | 0 |

## Per test

### `tests/api/test_app.py`

| Old test | Disposition | Covering test or reason |
|---|---|---|
| `test_health_reports_the_canon_version` | CASE-0031 only | reports the canon pack version |
| `test_the_case_view_carries_its_records` | not carried | no HTTP surface in sub-project B (the Studio, sub-project D, owns one) |
| `test_the_case_view_does_not_leak_another_cases_rows` | covered | `tests/tools_core/test_records.py::test_read_records_hides_other_cases` |
| `test_the_audit_trail_is_returned_in_order` | not carried | no HTTP surface in sub-project B (the Studio, sub-project D, owns one); event ids are the platform's: `tests/core/test_platform_rules_db.py::test_event_id_and_time_are_the_platforms` |
| `test_the_queue_shows_what_is_waiting` | not carried | no HTTP surface in sub-project B (the Studio, sub-project D, owns one); a run that waits names whom: `tests/engine/test_run.py::test_a_wait_names_the_person_its_decide_step_went_to` |
| `test_the_owning_persona_may_decide_through_the_api` | covered | `tests/tools_core/test_approvals.py::test_routed_person_decides` |
| `test_the_wrong_persona_is_refused_with_403` | covered | `tests/tools_core/test_approvals.py::test_routed_person_decides`; `tests/core/test_platform_rules_db.py::test_approval_decided_only_by_its_routed_approver` |
| `test_an_unknown_approval_is_a_404` | new test (Task 1) | `tests/tools_core/test_approvals.py::test_deciding_an_unknown_approval_is_refused` |
| `test_events_for_an_unknown_case_is_a_404` | not carried | no HTTP surface in sub-project B (the Studio, sub-project D, owns one) |
| `test_a_missing_or_blank_persona_is_a_422` | not carried | no HTTP surface in sub-project B (the Studio, sub-project D, owns one); a decision needs a person actor: `tests/tools_core/test_approvals.py::test_only_people_decide` |
| `test_the_scenario_endpoint_runs_from_master_data` | CASE-0031 only | runs a canon scenario |
| `test_the_scenario_endpoint_can_run_twice_in_a_row` | CASE-0031 only | canon scenario; the generic re-run is `tests/engine/test_run.py::test_two_runs_of_one_case_are_identical` |
| `test_a_scenario_run_that_raises_restores_the_seeded_state` | CASE-0031 only | canon seeded state |
| `test_the_scenario_endpoint_defaults_illustrative_to_off` | CASE-0031 only | canon illustrative prices |
| `test_the_scenario_endpoint_can_opt_into_illustrative_prices` | CASE-0031 only | canon illustrative prices |
| `test_retrying_a_decision_with_the_same_key_replays_it` | not carried | idempotency keys are not part of the generic tool surface; a repeated write is refused by its id instead (document, approval and payment ids are unique): `tests/tools_core/test_approvals.py::test_an_existing_approval_id_is_never_reused` |
| `test_reusing_a_key_for_a_different_persona_is_still_refused` | not carried | idempotency keys are not part of the generic tool surface; a repeated write is refused by its id instead (document, approval and payment ids are unique): `tests/tools_core/test_approvals.py::test_an_existing_approval_id_is_never_reused` |
| `test_a_scenario_run_forgets_keys_recorded_against_the_data_it_wiped` | not carried | idempotency keys are not part of the generic tool surface; a repeated write is refused by its id instead (document, approval and payment ids are unique): `tests/tools_core/test_approvals.py::test_an_existing_approval_id_is_never_reused` |

### `tests/canon/test_invariants.py`

| Old test | Disposition | Covering test or reason |
|---|---|---|
| `test_canon_invariant_holds` | CASE-0031 only | the 42 CASE-0031 invariants |
| `test_there_are_42_declarative_invariants` | CASE-0031 only | - |
| `test_a_corrupted_quantity_is_caught` | CASE-0031 only | generic counterpart: `tests/bench/test_score.py::test_a_changed_quantity_is_never_perfect` [not in this copy] |
| `test_an_extra_approval_gate_is_caught` | CASE-0031 only | CASE-0031 has three gates |
| `test_unknown_condition_raises_instead_of_silently_failing` | covered | `tests/bench/test_score.py::test_assertion_kinds` [not in this copy] (a malformed assertion fails, never passes) |
| `test_is_blank` | covered | `tests/bench/test_score.py::test_assertion_kinds` [not in this copy] (is_blank case); `tests/bench/test_score.py::test_cells_read_as_the_bench_writes_them` [not in this copy] |
| `test_the_packs_own_validator_still_passes` | CASE-0031 only | runs the canon pack's own validator |

### `tests/canon/test_pack.py`

| Old test | Disposition | Covering test or reason |
|---|---|---|
| `test_pack_version` | CASE-0031 only | - |
| `test_schema_declares_26_tables_with_evt_append_only` | CASE-0031 only | the core schema's counterpart: `tests/core/test_schema.py::test_load_core_schema_has_the_eleven_tables` |
| `test_columns_carry_primary_keys` | covered | `tests/core/test_schema.py::test_columns_carry_type_key_nullability_and_reference` |
| `test_csv_table_names_drop_the_numeric_prefix` | CASE-0031 only | - |
| `test_canon_quantities_are_readable_from_csv` | CASE-0031 only | pack master rows as CSV: `tests/governance/test_canon_pack_on_engine.py::test_pack_follows_the_table_mapping` |
| `test_event_kinds_and_scenarios` | CASE-0031 only | - |
| `test_illustrative_prices_are_separate_from_canon` | CASE-0031 only | - |
| `test_kb_documents_parse_their_front_matter` | CASE-0031 only | - |
| `test_the_tool_catalog_is_readable_by_name` | CASE-0031 only | - |
| `test_the_canon_names_the_numbers_it_leaves_blank` | CASE-0031 only | - |

### `tests/contracts/test_envelope.py`

| Old test | Disposition | Covering test or reason |
|---|---|---|
| `test_task_envelope_validates_against_the_canon_schema` | CASE-0031 only | the canon pack's envelope JSON Schemas |
| `test_every_required_task_field_exists_on_the_model` | CASE-0031 only | - |
| `test_dropping_a_required_field_fails_canon_validation` | CASE-0031 only | - |
| `test_result_envelope_validates_against_the_canon_schema` | CASE-0031 only | - |
| `test_result_status_values_match_the_canon_enum` | CASE-0031 only | step outcomes are checked instead: `tests/engine/test_run.py::test_unknown_outcome_is_refused` |
| `test_an_invented_status_is_rejected` | covered | `tests/engine/test_run.py::test_unknown_outcome_is_refused`; `tests/engine/test_toolbox.py::test_an_outcome_that_is_not_a_text_is_refused` |
| `test_denied_helper_carries_the_reason` | covered | `tests/engine/test_run.py::test_refused_call_is_recorded_and_run_continues` |

### `tests/db/test_bootstrap.py`

| Old test | Disposition | Covering test or reason |
|---|---|---|
| `test_transaction_control_lines_are_removed_and_plpgsql_begin_stays` | CASE-0031 only | loads the canon SQL projection |
| `test_every_table_declared_in_canon_schema_exists` | covered | `tests/core/test_schema.py::test_ddl_creates_tables_in_core_only` |
| `test_seeded_state_matches_canon_facts` | CASE-0031 only | - |
| `test_guardrails_are_active_after_bootstrap` | covered | `tests/enforce/test_platform_rules_attack.py::test_rule_1_through_raw_sql`; `tests/core/test_platform_rules_db.py::test_events_are_append_only` |
| `test_truncate_operational_keeps_master_data` | covered | `tests/core/test_schema.py::test_reset_core_is_repeatable_and_empties_the_tables`; `tests/engine/test_run.py::test_a_previous_run_is_wiped` |
| `test_bootstrap_alone_leaves_evt_ready_for_an_id_less_insert` | covered | `tests/core/test_platform_rules_db.py::test_event_id_and_time_are_the_platforms` |

### `tests/db/test_guardrails_both_paths.py`

| Old test | Disposition | Covering test or reason |
|---|---|---|
| `test_audit_rows_cannot_be_changed_through_python` | covered | `tests/enforce/test_platform_rules_attack.py::test_rule_6_through_the_tools` |
| `test_audit_rows_cannot_be_changed_through_raw_sql` | covered | `tests/enforce/test_platform_rules_attack.py::test_rule_6_through_raw_sql`; `tests/core/test_platform_rules_db.py::test_events_are_append_only` |
| `test_audit_rows_cannot_be_deleted_through_raw_sql` | covered | `tests/core/test_platform_rules_db.py::test_events_are_append_only` |
| `test_payment_without_an_approved_gate_is_refused_through_python` | covered | `tests/enforce/test_platform_rules_attack.py::test_rule_4_through_the_tools`; `tests/tools_core/test_settlement.py::test_pay_without_approved_approval_is_refused` |
| `test_payment_without_an_approved_gate_is_refused_through_raw_sql` | covered | `tests/enforce/test_platform_rules_attack.py::test_rule_4_through_raw_sql`; `tests/core/test_platform_rules_db.py::test_payment_needs_approved_chain_at_db_tier` |
| `test_payment_against_an_unreconciled_invoice_is_refused_through_raw_sql` | not carried | database-tier reconciliation-at-payment rule (core/platform_rules.sql checks no ket_qua at payment); the tool tier still refuses, see `tests/tools_core/test_settlement.py::test_pay_with_invoice_needs_a_matched_reconciliation` |
| `test_payment_succeeds_once_both_conditions_are_met` | covered | `tests/tools_core/test_settlement.py::test_pay_with_invoice_needs_a_matched_reconciliation`; `tests/tools_core/test_settlement.py::test_pay_after_approval_records_paid_event` |
| `test_an_unregistered_event_kind_is_refused_through_raw_sql` | covered | `tests/core/test_platform_rules_db.py::test_event_kind_must_be_known_and_carries_actor` |

### `tests/db/test_invariants_on_postgres.py`

| Old test | Disposition | Covering test or reason |
|---|---|---|
| `test_every_canon_invariant_holds_against_the_database` | CASE-0031 only | the 42 CASE-0031 invariants; bench invariants are scored by `tests/bench/test_score.py::test_identity_mapping_scores_perfect` [not in this copy] |
| `test_the_check_has_teeth` | covered | `tests/bench/test_score.py::test_wrong_amount_fails_its_invariant` [not in this copy] |

### `tests/db/test_repo.py`

| Old test | Disposition | Covering test or reason |
|---|---|---|
| `test_columns_come_from_the_canon_schema` | covered | `tests/core/test_schema.py::test_load_core_schema_has_the_eleven_tables` |
| `test_select_with_a_filter` | covered | `tests/tools_core/test_records.py::test_read_records_filters` |
| `test_select_specific_fields` | not carried | the generic read_records returns whole rows; it has no field selection |
| `test_insert_returns_the_stored_row` | not carried | the old Repository API; the generic tools return ids and verdicts, and the rows are read back with read_records |
| `test_update_changes_only_the_named_columns` | covered | `tests/tools_core/test_documents.py::test_update_status_changes_one_row` |
| `test_update_on_an_append_only_table_is_refused_before_touching_the_database` | covered | `tests/tools_core/test_documents.py::test_update_status_never_touches_approvals_payments_or_gate_statuses`; `tests/core/test_platform_rules_db.py::test_events_are_append_only` |
| `test_unknown_table_is_refused` | new test (Task 1) | `tests/tools_core/test_records.py::test_an_unknown_or_injected_table_name_is_refused` |
| `test_unknown_column_is_refused` | covered | `tests/tools_core/test_records.py::test_read_records_outside_token_is_refused` (bogus where column); `tests/tools_core/test_documents.py::test_unknown_line_field_is_refused` |
| `test_a_sql_injection_attempt_in_a_table_name_is_refused` | new test (Task 1) | `tests/tools_core/test_records.py::test_an_unknown_or_injected_table_name_is_refused` |
| `test_repository_has_no_delete` | covered | `tests/core/test_platform_rules_db.py::test_approvals_are_never_deleted`; `tests/core/test_platform_rules_db.py::test_operational_records_are_never_truncated` |

### `tests/de/test_executor.py`

| Old test | Disposition | Covering test or reason |
|---|---|---|
| `test_scripted_executor_dispatches_on_de_and_intent` | covered | `tests/bench/test_executors.py::test_scripted_substitutes_params_and_chooses_outcome` [not in this copy] |
| `test_an_unregistered_intent_is_denied_not_guessed` | covered | `tests/bench/test_executors.py::test_scripted_step_missing_from_the_fixture_is_skipped` [not in this copy]; `tests/engine/test_run.py::test_non_optional_skip_is_refused` |
| `test_nemoclaw_is_called_with_its_documented_argv` | not carried | the NemoClaw subprocess executor is not carried (ruling Q3: the model executor's boundary is the tool-call channel) |
| `test_the_message_goes_in_argv_not_on_stdin` | not carried | NemoClaw executor not carried |
| `test_the_agent_and_timeout_are_configurable` | not carried | NemoClaw executor not carried |
| `test_a_reply_claiming_work_is_never_taken_as_work_done` | rebuilt by a later task | Task 6 (model executor): a step's work is what its tool calls wrote; Task 8 scores the database, not the reply |
| `test_a_missing_target_selector_exit_is_an_error_not_a_crash` | not carried | NemoClaw executor not carried |
| `test_a_nemoclaw_binary_that_is_not_installed_is_an_error` | not carried | NemoClaw executor not carried |

### `tests/de/test_ollama_executor.py`

| Old test | Disposition | Covering test or reason |
|---|---|---|
| `test_only_the_tools_in_the_token_are_offered` | covered | `tests/engine/test_toolbox.py::test_tools_for_each_actor_kind` (what a step may call) |
| `test_a_tool_call_runs_through_the_gates_and_writes_for_real` | rebuilt by a later task | Task 6: test_model_creates_document_and_finishes |
| `test_the_envelope_reports_what_the_tools_did_not_what_the_model_claims` | rebuilt by a later task | Task 6 / Task 8: outcomes come from tool calls and the database |
| `test_a_tool_outside_the_token_is_refused_and_the_model_is_told` | covered | `tests/engine/test_toolbox.py::test_a_tool_outside_the_step_is_refused` (refusal); telling the model is Task 6: test_refusal_text_returned_to_model |
| `test_finishing_without_calling_any_tool_is_an_error` | rebuilt by a later task | Task 6: test_text_reply_gets_one_reminder_then_ends_refused (one reminder, then refused) |
| `test_running_out_of_steps_is_an_error` | rebuilt by a later task | Task 6: test_max_turns_ends_refused |
| `test_a_failed_write_does_not_poison_the_calls_after_it` | covered | `tests/tools_core/test_documents.py::test_refused_call_rolls_back_only_itself`; `tests/engine/test_run.py::test_database_error_in_a_step_is_refused_and_connection_stays_usable` |
| `test_arguments_sent_as_a_json_string_are_accepted` | rebuilt by a later task | Task 6: the executor parses the model's JSON tool calls (test_unknown_tool_and_bad_args_do_not_crash) |
| `test_an_unreachable_model_is_an_error_not_a_crash` | rebuilt by a later task | Task 2 (ModelUnavailable) and Task 6: test_unavailable_propagates |
| `test_the_playbook_for_the_intent_reaches_the_model` | rebuilt by a later task | Task 6: the step's guidance reaches the prompt; CASE-0031 playbooks are not carried |
| `test_without_a_playbook_the_prompt_says_none_was_given` | CASE-0031 only | CASE-0031 playbooks |
| `test_each_call_records_its_arguments_for_audit` | rebuilt by a later task | Task 6 / Task 11: per-call records; every write is an event with its step id: `tests/tools_core/test_context.py::test_every_write_records_one_event_with_step_id` |
| `test_stopping_short_of_the_playbook_gets_one_reminder` | CASE-0031 only | CASE-0031 playbook completeness |
| `test_still_short_after_the_reminders_is_an_error_not_done` | CASE-0031 only | CASE-0031 playbook completeness |
| `test_a_denied_call_does_not_count_toward_the_playbook` | CASE-0031 only | CASE-0031 playbook completeness |
| `test_a_model_may_not_invent_an_amount_the_canon_leaves_blank` | covered | `tests/tools_core/test_documents.py::test_invented_unit_price_is_refused`; `tests/tools_core/test_documents.py::test_unknown_unit_price_leaves_totals_unknown` |
| `test_a_model_may_not_write_a_price_into_a_draft` | covered | `tests/tools_core/test_documents.py::test_invented_unit_price_is_refused`; `tests/core/test_platform_rules_db.py::test_unsourced_unit_price_refused_at_db_tier` |
| `test_an_explicit_null_for_a_blank_column_is_fine` | new test (Task 1) | `tests/tools_core/test_documents.py::test_an_explicit_null_unit_price_is_accepted` |

### `tests/de/test_runtime.py`

| Old test | Disposition | Covering test or reason |
|---|---|---|
| `test_a_task_runs_with_the_scope_from_de_scope` | covered | `tests/enforce/test_tokens.py::test_task_token_is_narrower_than_scope_token` |
| `test_send_email_is_folded_into_the_token_from_its_own_de_scope_column` | CASE-0031 only | canon de_scope.send_email column |
| `test_a_digital_employee_without_scope_is_denied` | covered | `tests/governance/test_template.py::test_so_role_requires_scope` |
| `test_each_run_gets_a_fresh_single_use_token` | covered | `tests/engine/test_run.py::test_each_digital_employee_step_gets_a_new_single_use_token` |
| `test_the_runtime_actually_spends_the_task_token` | covered | `tests/engine/test_run.py::test_each_digital_employee_step_gets_a_new_single_use_token` (checks every token is redeemed); `tests/enforce/test_tokens.py::test_task_token_is_single_use` |
| `test_a_handler_that_raises_becomes_an_error_result_not_a_silent_success` | covered | `tests/engine/test_run.py::test_database_error_in_a_step_is_refused_and_connection_stays_usable`; `tests/engine/test_run.py::test_a_swallowed_refusal_still_refuses_the_step` |
| `test_a_failed_step_leaves_the_connection_usable_for_the_next_one` | covered | `tests/engine/test_run.py::test_database_error_in_a_step_is_refused_and_connection_stays_usable` |
| `test_human_tools_are_never_granted_to_a_digital_employee` | covered | `tests/engine/test_toolbox.py::test_tools_for_each_actor_kind`; `tests/enforce/test_tokens.py::test_scope_above_ceiling_is_refused` |
| `test_a_human_context_carries_the_persona_and_only_the_human_tools` | covered | `tests/engine/test_toolbox.py::test_tools_for_each_actor_kind`; `tests/engine/test_toolbox.py::test_a_person_may_not_use_a_digital_employees_tool` |
| `test_every_persona_that_owns_a_gate_can_get_a_context` | CASE-0031 only | canon personas; generic counterpart: `tests/governance/test_validate.py::test_a_tier_approver_is_a_person_of_the_pack` |

### `tests/de/test_scope.py`

| Old test | Disposition | Covering test or reason |
|---|---|---|
| `test_only_nine_of_fifteen_digital_employees_have_scope` | CASE-0031 only | - |
| `test_a_digital_employee_without_scope_has_no_capability` | covered | `tests/governance/test_template.py::test_so_role_requires_scope` |
| `test_pipe_separated_cells_become_sets` | CASE-0031 only | canon de_scope.csv format; converted scopes: `tests/governance/test_canon_pack_on_engine.py::test_template_scopes_are_the_canon_scopes` |
| `test_an_empty_cell_means_no_capability` | CASE-0031 only | canon de_scope.csv format |
| `test_send_email_is_folded_into_the_token_tool_set` | CASE-0031 only | canon de_scope.send_email column |
| `test_create_apr_column_agrees_with_the_tool_list` | covered | `tests/enforce/test_tokens.py::test_a_scope_that_may_not_open_approvals_never_carries_request_approval` |

### `tests/flow/test_case_0031.py`

| Old test | Disposition | Covering test or reason |
|---|---|---|
| `test_the_canon_case_reaches_the_canon_state` | CASE-0031 only | re-run on the engine: `tests/governance/test_canon_pack_on_engine.py::test_canon_scenarios_match_old_outcomes` |
| `test_the_case_opens_exactly_three_gates` | CASE-0031 only | - |
| `test_the_late_delivery_and_the_faulty_batch_open_no_gate` | CASE-0031 only | - |
| `test_the_sales_order_stays_pending_even_though_its_gate_is_approved` | CASE-0031 only | - |
| `test_no_money_is_invented` | covered | `tests/tools_core/test_documents.py::test_unknown_unit_price_leaves_totals_unknown`; `tests/tools_core/test_documents.py::test_invented_unit_price_is_refused` |
| `test_illustrative_prices_are_opt_in_and_change_only_the_amounts` | CASE-0031 only | canon illustrative prices |
| `test_the_illustrative_amount_is_labelled_in_the_audit_trail` | CASE-0031 only | canon illustrative prices |
| `test_an_over_cap_discount_is_flagged_and_never_written` | covered | `tests/tools_core/test_documents.py::test_discount_above_the_item_cap_is_refused` |
| `test_shortage_is_flagged_only_for_an_item_with_a_declared_threshold` | CASE-0031 only | canon shortage threshold |
| `test_pay_units_reflects_the_database_not_the_input_parameter` | covered | `tests/core/test_platform_rules_db.py::test_digital_employee_pays_the_documents_partner_and_amount` |
| `test_a_step_that_never_ran_is_recorded_as_a_failed_step` | covered | `tests/engine/test_run.py::test_non_optional_skip_is_refused` |

### `tests/flow/test_golden_reproduction.py`

| Old test | Disposition | Covering test or reason |
|---|---|---|
| `test_each_operational_table_matches_the_canon` | CASE-0031 only | golden seed_operational.sql of CASE-0031 |
| `test_the_approvals_match_the_canon` | CASE-0031 only | - |
| `test_the_audit_trail_matches_the_canon_in_order` | CASE-0031 only | - |
| `test_the_comparison_has_teeth` | covered | `tests/bench/test_score.py::test_wrong_amount_fails_its_invariant` [not in this copy] |

### `tests/flow/test_playbooks.py`

| Old test | Disposition | Covering test or reason |
|---|---|---|
| `test_playbooks_are_keyed_by_worker_and_intent` | CASE-0031 only | CASE-0031 playbooks; templates carry step guidance: `tests/bench/test_dev_runs.py::test_every_digital_employee_step_has_vietnamese_guidance` [not in this copy] |
| `test_every_playbook_names_a_worker_that_has_scope` | CASE-0031 only | - |
| `test_a_playbook_only_names_tools_its_worker_holds` | CASE-0031 only | - |
| `test_draft_quote_requires_the_gate_to_be_opened` | CASE-0031 only | - |
| `test_every_required_tool_is_one_its_worker_holds` | CASE-0031 only | - |

### `tests/flow/test_scenarios.py`

| Old test | Disposition | Covering test or reason |
|---|---|---|
| `test_scenario_reaches_its_declared_outcome` | CASE-0031 only | re-run on the engine: `tests/governance/test_canon_pack_on_engine.py::test_canon_scenarios_match_old_outcomes` |
| `test_the_pack_declares_exactly_these_three_scenarios` | CASE-0031 only | `tests/governance/test_canon_pack_on_engine.py::test_scenarios_keep_the_old_expectations` |
| `test_parameters_come_from_the_pack_not_from_code` | CASE-0031 only | `tests/governance/test_canon_pack_on_engine.py::test_fixture_cap_thresholds_are_the_policy_cap` |
| `test_paying_only_for_what_arrived_holds_in_every_scenario` | CASE-0031 only | generic counterpart: `tests/tools_core/test_settlement.py::test_reconcile_reports_shortfall` |
| `test_the_check_has_teeth` | covered | `tests/bench/test_score.py::test_wrong_amount_fails_its_invariant` [not in this copy] |
| `test_check_reports_rather_than_crashes_on_an_unknown_expectation_key` | covered | `tests/bench/test_score.py::test_assertion_kinds` [not in this copy] (malformed: fails, never raises) |
| `test_a_missing_handler_can_never_come_back_as_an_empty_problem_list` | covered | `tests/engine/test_run.py::test_non_optional_skip_is_refused`; `tests/bench/test_score.py::test_missing_flag_is_an_outcome_mismatch` [not in this copy] |

### `tests/policy/test_agrees_with_postgres.py`

| Old test | Disposition | Covering test or reason |
|---|---|---|
| `test_policy_store_reads_the_same_value_as_fn_policy` | CASE-0031 only | canon fn_policy SQL function |
| `test_a_threshold_the_canon_leaves_blank_reads_as_none` | CASE-0031 only | - |
| `test_python_and_fn_check_discount_agree` | CASE-0031 only | canon fn_check_discount; the tool and database tiers agree on rule 3: `tests/enforce/test_platform_rules_attack.py::test_rule_3_through_the_tools`; `tests/enforce/test_platform_rules_attack.py::test_rule_3_through_raw_sql` |

### `tests/policy/test_rego_conformance.py`

| Old test | Disposition | Covering test or reason |
|---|---|---|
| `test_every_allow_decide_rule_has_a_python_counterpart` | CASE-0031 only | canon policy.rego |
| `test_the_discount_policy_key_matches` | CASE-0031 only | canon policy.rego |
| `test_the_deny_message_matches` | CASE-0031 only | canon policy.rego |
| `test_the_side_effect_condition_matches` | CASE-0031 only | canon policy.rego |
| `test_the_rego_file_has_exactly_the_rules_we_ported` | CASE-0031 only | canon policy.rego |

### `tests/policy/test_rules.py`

| Old test | Disposition | Covering test or reason |
|---|---|---|
| `test_discount_at_the_cap_is_allowed` | covered | `tests/tools_core/test_documents.py::test_discount_above_the_item_cap_is_refused` (the at-cap call succeeds) |
| `test_discount_over_the_cap_is_denied_with_the_rego_message` | covered | `tests/tools_core/test_documents.py::test_discount_above_the_item_cap_is_refused` |
| `test_a_blank_cap_falls_back_to_five_percent` | CASE-0031 only | the 5% default is canon policy.rego's |
| `test_the_owning_persona_may_decide` | covered | `tests/enforce/test_gate.py::test_routed_independent_actor_allowed_and_no_maker_checker` |
| `test_the_wrong_persona_may_not_decide` | covered | `tests/enforce/test_gate.py::test_non_routed_actor_refused` |
| `test_an_unknown_approval_type_is_denied` | covered | `tests/enforce/test_gate.py::test_unknown_approval_type_fails_closed` |
| `test_an_unknown_persona_is_denied` | covered | `tests/enforce/test_gate.py::test_non_routed_actor_refused` |
| `test_a_side_effect_needs_an_approved_gate` | covered | `tests/tools_core/test_settlement.py::test_notify_needs_approved_approval` |
| `test_canon_approval_labels_map_to_policy_types` | CASE-0031 only | canon approval labels |
| `test_an_unrecognised_label_maps_to_nothing` | CASE-0031 only | canon approval labels |

### `tests/policy/test_store.py`

| Old test | Disposition | Covering test or reason |
|---|---|---|
| `test_a_cap_configured_as_zero_means_no_discounts_at_all` | new test (Task 1) | `tests/tools_core/test_documents.py::test_a_zero_item_cap_allows_no_discount` |
| `test_a_genuinely_unconfigured_cap_still_falls_back_to_the_default` | CASE-0031 only | the 5% default is canon policy.rego's; with no cap the generic tools apply none: `tests/tools_core/test_documents.py::test_create_document_applies_discount_and_vat` |

### `tests/tools/test_catalog.py`

| Old test | Disposition | Covering test or reason |
|---|---|---|
| `test_all_nine_canon_tools_are_registered` | CASE-0031 only | the nine canon tools; the generic set is CORE_TOOLS: `tests/tools_core/test_context.py::test_the_token_tool_list_names_every_tool_but_decide` |
| `test_the_catalog_file_and_the_registry_agree` | CASE-0031 only | canon tool-catalog.json |

### `tests/tools/test_create_approval.py`

| Old test | Disposition | Covering test or reason |
|---|---|---|
| `test_a_new_approval_starts_pending_and_names_its_author` | covered | `tests/tools_core/test_approvals.py::test_request_routes_to_tier_approver` |
| `test_the_amount_stays_blank_when_none_is_given` | CASE-0031 only | canon apr.gia_tri; the generic request takes the document's tong_tien: `tests/tools_core/test_approvals.py::test_request_routes_to_tier_approver` |
| `test_an_unknown_approval_type_is_refused` | covered | `tests/tools_core/test_approvals.py::test_request_for_an_unknown_approval_type_is_refused` |
| `test_a_digital_employee_without_the_tool_may_not_open_a_gate` | covered | `tests/enforce/test_tokens.py::test_a_scope_that_may_not_open_approvals_never_carries_request_approval`; `tests/tools_core/test_context.py::test_every_tool_checks_its_own_name_against_the_token[request_approval]` |
| `test_the_hr_branch_may_carry_a_blank_case` | CASE-0031 only | canon HR branch APR-TH-01 |
| `test_reusing_ma_apr_for_a_different_type_is_refused` | new test (Task 1) | `tests/tools_core/test_approvals.py::test_an_existing_approval_id_is_never_reused` |
| `test_an_identical_retry_replays_even_after_the_gate_is_decided` | not carried | idempotency keys are not part of the generic tool surface; a repeated write is refused by its id instead (document, approval and payment ids are unique): `tests/tools_core/test_approvals.py::test_an_existing_approval_id_is_never_reused` |

### `tests/tools/test_decide_approval.py`

| Old test | Disposition | Covering test or reason |
|---|---|---|
| `test_p5_may_approve_the_payment_request` | covered | `tests/tools_core/test_approvals.py::test_routed_person_decides`; `tests/tools_core/test_settlement.py::test_two_level_chain_then_pay` |
| `test_the_chief_executive_may_not_approve_a_payment` | covered | `tests/tools_core/test_approvals.py::test_routed_person_decides` (GD, not routed, is refused) |
| `test_p2_owns_the_quote_gate_and_p6_owns_the_purchase_gate` | covered | `tests/enforce/test_gate.py::test_approver_routes_by_tier` |
| `test_deciding_without_a_user_token_is_refused` | covered | `tests/tools_core/test_approvals.py::test_only_people_decide`; `tests/core/test_platform_rules_db.py::test_digital_employee_cannot_approve_at_db_tier` |
| `test_an_already_decided_approval_is_not_decided_again` | covered | `tests/tools_core/test_approvals.py::test_routed_person_decides` (decided once) |
| `test_an_invented_decision_value_is_refused` | covered | `tests/tools_core/test_approvals.py::test_decision_must_be_approve_or_reject` |
| `test_rejection_is_recorded_as_a_decision` | covered | `tests/tools_core/test_approvals.py::test_routed_person_decides` |
| `test_the_same_key_decides_once` | not carried | idempotency keys are not part of the generic tool surface; a repeated write is refused by its id instead (document, approval and payment ids are unique): `tests/tools_core/test_approvals.py::test_an_existing_approval_id_is_never_reused` |
| `test_a_replay_key_may_not_return_a_different_approvals_decision` | not carried | idempotency keys are not part of the generic tool surface; a repeated write is refused by its id instead (document, approval and payment ids are unique): `tests/tools_core/test_approvals.py::test_an_existing_approval_id_is_never_reused` |
| `test_decide_approval_takes_one_approval_at_a_time` | covered | `tests/engine/test_toolbox.py::test_malformed_arguments_are_refused_not_crashed` |

### `tests/tools/test_least_privilege.py`

| Old test | Disposition | Covering test or reason |
|---|---|---|
| `test_read_records_refuses_a_worker_whose_token_lacks_it` | new test (Task 1) | `tests/tools_core/test_context.py::test_every_tool_checks_its_own_name_against_the_token[read_records]` |
| `test_write_draft_refuses_a_worker_whose_token_lacks_it` | covered | `tests/tools_core/test_context.py::test_tool_outside_token_is_refused` |
| `test_log_event_refuses_a_worker_whose_token_lacks_it` | new test (Task 1) | `tests/tools_core/test_context.py::test_every_tool_checks_its_own_name_against_the_token[record_event]` |
| `test_update_status_refuses_a_worker_whose_token_lacks_it` | new test (Task 1) | `tests/tools_core/test_context.py::test_every_tool_checks_its_own_name_against_the_token[update_status]` |
| `test_search_kb_refuses_a_worker_whose_token_lacks_it` | covered | `tests/tools_core/test_context.py::test_tool_outside_token_is_refused` |
| `test_match_three_way_refuses_a_worker_whose_token_lacks_it` | new test (Task 1) | `tests/tools_core/test_context.py::test_every_tool_checks_its_own_name_against_the_token[reconcile]` |

### `tests/tools/test_log_event.py`

| Old test | Disposition | Covering test or reason |
|---|---|---|
| `test_a_registered_kind_is_written` | covered | `tests/tools_core/test_events.py::test_record_event_writes_one_row` |
| `test_an_unregistered_kind_is_refused_before_the_database` | covered | `tests/tools_core/test_events.py::test_record_event_refuses_kinds_other_tools_own` |
| `test_the_database_refuses_an_unregistered_kind_too` | covered | `tests/core/test_platform_rules_db.py::test_event_kind_must_be_known_and_carries_actor` |
| `test_an_event_cannot_be_rewritten_through_the_repository` | covered | `tests/enforce/test_platform_rules_attack.py::test_rule_6_through_the_tools` |
| `test_an_event_cannot_be_rewritten_through_raw_sql` | covered | `tests/enforce/test_platform_rules_attack.py::test_rule_6_through_raw_sql`; `tests/core/test_platform_rules_db.py::test_events_are_append_only` |
| `test_the_registry_holds_exactly_the_ten_canon_kinds` | CASE-0031 only | the ten canon event kinds |

### `tests/tools/test_match_three_way.py`

| Old test | Disposition | Covering test or reason |
|---|---|---|
| `test_the_canon_case_needs_checking` | covered | `tests/tools_core/test_settlement.py::test_reconcile_reports_shortfall` |
| `test_an_equal_receipt_matches` | covered | `tests/tools_core/test_settlement.py::test_reconcile_matches_full_receipt` |
| `test_python_agrees_with_the_canon_sql_function` | CASE-0031 only | canon fn_reconcile |
| `test_matching_never_edits_its_sources` | new test (Task 1) | `tests/tools_core/test_settlement.py::test_reconcile_never_edits_its_sources` |
| `test_a_purchase_order_with_no_receipt_needs_checking` | covered | `tests/tools_core/test_settlement.py::test_reconcile_reports_shortfall` (a receipt short of the order needs checking) |
| `test_two_receipts_are_refused_instead_of_summed` | CASE-0031 only | canon fn_reconcile's scalar subquery; the generic reconcile sums several receipts by design |
| `test_both_layers_refuse_the_same_two_receipt_state` | CASE-0031 only | canon fn_reconcile |

### `tests/tools/test_read_records.py`

| Old test | Disposition | Covering test or reason |
|---|---|---|
| `test_reads_rows_from_a_table_in_scope` | covered | `tests/tools_core/test_records.py::test_read_records_filters` |
| `test_selected_fields_are_honoured` | not carried | the generic read_records has no field selection |
| `test_a_table_outside_the_token_scope_is_denied` | covered | `tests/tools_core/test_records.py::test_read_records_outside_token_is_refused` |
| `test_reading_the_payment_table_without_scope_reveals_nothing` | covered | `tests/tools_core/test_records.py::test_read_records_outside_token_is_refused` (refused: no rows returned) |

### `tests/tools/test_registry.py`

| Old test | Disposition | Covering test or reason |
|---|---|---|
| `test_the_nine_canon_tool_names_match_the_catalog` | CASE-0031 only | canon tool-catalog.json |
| `test_a_tool_outside_the_token_scope_is_denied` | covered | `tests/tools_core/test_context.py::test_tool_outside_token_is_refused`; `tests/engine/test_toolbox.py::test_a_tool_outside_the_step_is_refused` |
| `test_a_tool_inside_the_token_scope_runs` | covered | `tests/engine/test_toolbox.py::test_a_pay_step_pays_its_request_once` |
| `test_an_unregistered_tool_raises` | covered | `tests/engine/test_toolbox.py::test_a_tool_outside_the_step_is_refused`; `tests/engine/test_toolbox.py::test_a_tool_name_that_is_not_a_text_is_refused` |
| `test_registering_a_name_outside_the_canon_catalog_is_refused` | CASE-0031 only | canon tool-catalog.json |
| `test_idempotency_store_returns_the_first_result` | not carried | idempotency keys are not part of the generic tool surface; a repeated write is refused by its id instead (document, approval and payment ids are unique): `tests/tools_core/test_approvals.py::test_an_existing_approval_id_is_never_reused` |

### `tests/tools/test_schema.py`

| Old test | Disposition | Covering test or reason |
|---|---|---|
| `test_required_parameters_come_from_the_signature` | rebuilt by a later task | Task 2 (test_schemas.py): test_schema_params_match_tool_signature |
| `test_the_context_parameter_is_never_offered` | rebuilt by a later task | Task 2: test_schema_params_match_tool_signature (signature minus ctx) |
| `test_a_parameter_with_a_default_is_optional` | rebuilt by a later task | Task 2: test_schema_params_match_tool_signature (required = no default) |
| `test_optional_scalars_keep_their_inner_type` | rebuilt by a later task | Task 2 (tool schemas) |
| `test_the_description_is_the_canon_catalog_entry` | CASE-0031 only | canon tool-catalog.json descriptions |
| `test_only_the_named_tools_are_described` | rebuilt by a later task | Task 2: tool_schemas(names) |
| `test_every_canon_tool_yields_a_schema` | rebuilt by a later task | Task 2: test_every_core_tool_has_a_schema |

### `tests/tools/test_search_kb.py`

| Old test | Disposition | Covering test or reason |
|---|---|---|
| `test_finds_the_discount_policy_with_its_citation` | covered | `tests/tools_core/test_records.py::test_search_kb_matches_without_accents` |
| `test_a_query_with_no_match_returns_not_found` | covered | `tests/tools_core/test_records.py::test_search_kb_matches_without_accents` (no match: empty list) |
| `test_a_domain_outside_the_token_is_denied` | not carried | knowledge domains are not carried; reading tri_thuc needs it in the token's read set (require_read), tool refusal: `tests/tools_core/test_context.py::test_tool_outside_token_is_refused` |
| `test_the_all_domain_may_read_every_article` | CASE-0031 only | canon kb_domain 'all' |
| `test_an_article_listed_in_the_table_but_missing_a_file_is_not_invented` | CASE-0031 only | canon kb markdown files |

### `tests/tools/test_send_email.py`

| Old test | Disposition | Covering test or reason |
|---|---|---|
| `test_a_message_goes_out_once_its_gate_is_approved` | covered | `tests/tools_core/test_settlement.py::test_notify_needs_approved_approval` |
| `test_a_message_whose_gate_is_pending_is_refused` | covered | `tests/tools_core/test_settlement.py::test_notify_needs_approved_approval` |
| `test_a_message_with_no_gate_at_all_is_refused` | covered | `tests/tools_core/test_settlement.py::test_notify_ref_must_be_the_approved_document_or_approval` |
| `test_a_real_looking_address_is_refused` | covered | `tests/tools_core/test_settlement.py::test_notify_never_reaches_a_real_address`; `tests/tools_core/test_settlement.py::test_notify_demo_address_has_exactly_one_at` |
| `test_a_digital_employee_without_the_capability_may_not_send` | new test (Task 1) | `tests/tools_core/test_context.py::test_every_tool_checks_its_own_name_against_the_token[notify]` |
| `test_a_failed_send_does_not_report_success` | new test (Task 1) | `tests/tools_core/test_settlement.py::test_a_failed_send_reports_no_success_and_records_no_event` |

### `tests/tools/test_update_status.py`

| Old test | Disposition | Covering test or reason |
|---|---|---|
| `test_an_approved_gate_lets_the_sales_order_move` | covered | `tests/tools_core/test_approvals.py::test_routed_person_decides` (the decision moves the document) |
| `test_paying_is_refused_while_its_gate_is_pending` | covered | `tests/tools_core/test_settlement.py::test_pay_without_approved_approval_is_refused` |
| `test_the_database_refuses_the_same_payment_even_when_python_is_bypassed` | covered | `tests/enforce/test_platform_rules_attack.py::test_rule_4_through_raw_sql` |
| `test_paying_is_refused_while_reconciliation_says_check_it` | covered | `tests/tools_core/test_settlement.py::test_pay_with_invoice_needs_a_matched_reconciliation` |
| `test_an_illegal_transition_is_refused` | covered | `tests/tools_core/test_documents.py::test_update_status_never_touches_approvals_payments_or_gate_statuses`; `tests/tools_core/test_documents.py::test_a_digital_employee_never_moves_a_decided_document` |
| `test_an_unknown_table_fails_closed` | new test (Task 1) | `tests/tools_core/test_records.py::test_an_unknown_or_injected_table_name_is_refused` (same check_table as update_status) |
| `test_a_status_the_flow_does_not_cover_is_refused` | CASE-0031 only | canon STATUS_FLOW; generic status rules: `tests/tools_core/test_documents.py::test_digital_employee_cannot_set_approved_status` |
| `test_a_multi_column_key_is_refused_even_on_a_legal_ungated_transition` | CASE-0031 only | canon multi-column keys; the core tables have one-column keys |
| `test_linked_approval_finds_the_approved_row_regardless_of_insertion_order` | covered | `tests/tools_core/test_settlement.py::test_two_level_chain_then_pay`; `tests/tools_core/test_settlement.py::test_pay_with_an_approval_of_another_document_is_refused` |
| `test_linked_approval_is_stable_with_no_approved_row_and_the_gate_still_refuses` | covered | `tests/tools_core/test_settlement.py::test_pay_after_rejection_is_refused` |

### `tests/tools/test_write_draft.py`

| Old test | Disposition | Covering test or reason |
|---|---|---|
| `test_writes_a_draft_row_into_a_table_in_scope` | covered | `tests/tools_core/test_documents.py::test_create_document_computes_derived_money` |
| `test_the_same_idempotency_key_does_not_write_twice` | not carried | idempotency keys are not part of the generic tool surface; a repeated write is refused by its id instead (document, approval and payment ids are unique): `tests/tools_core/test_approvals.py::test_an_existing_approval_id_is_never_reused` |
| `test_a_table_outside_the_draft_scope_is_denied` | covered | `tests/tools_core/test_context.py::test_tool_outside_token_is_refused` (dong_ct not in draft set); `tests/engine/test_run.py::test_table_outside_the_token_is_refused` |
| `test_a_draft_may_not_be_born_already_approved` | covered | `tests/tools_core/test_documents.py::test_digital_employee_cannot_set_approved_status`; `tests/core/test_platform_rules_db.py::test_an_approval_is_never_inserted_decided` |
| `test_a_discount_over_the_cap_is_refused_with_the_policy_message` | covered | `tests/tools_core/test_documents.py::test_discount_above_the_item_cap_is_refused` |
| `test_a_discount_at_the_cap_is_allowed` | covered | `tests/tools_core/test_documents.py::test_discount_above_the_item_cap_is_refused` (the at-cap call succeeds) |
| `test_reusing_a_key_with_a_different_payload_is_denied` | not carried | idempotency keys are not part of the generic tool surface; a repeated write is refused by its id instead (document, approval and payment ids are unique): `tests/tools_core/test_approvals.py::test_an_existing_approval_id_is_never_reused` |

### `tests/test_cli.py`

| Old test | Disposition | Covering test or reason |
|---|---|---|
| `test_validate_runs_every_canon_invariant` | CASE-0031 only | `tonomyx validate` over the 42 canon invariants |
| `test_validate_reports_a_genuine_invariant_failure` | CASE-0031 only | - |
| `test_bootstrap_then_run_scenario_reports_the_outcome` | CASE-0031 only | canon scenarios |
| `test_run_scenario_defaults_to_no_illustrative_note` | CASE-0031 only | - |
| `test_run_scenario_illustrative_flag_prints_the_non_canon_note` | CASE-0031 only | - |
| `test_a_scenario_that_does_not_exist_exits_non_zero` | CASE-0031 only | - |
| `test_a_scenario_run_that_raises_restores_the_seeded_state` | CASE-0031 only | - |
| `test_queue_lists_what_is_waiting` | CASE-0031 only | canon approval queue |
| `test_run_task_prints_the_envelope_and_exits_zero` | CASE-0031 only | canon DE intents and envelopes |
| `test_run_task_passes_inputs_through` | CASE-0031 only | - |
| `test_run_task_for_an_employee_without_scope_exits_non_zero` | covered | `tests/governance/test_template.py::test_so_role_requires_scope` |
| `test_run_task_from_master_starts_with_only_the_case_open` | CASE-0031 only | - |

### `tests/aebench/conftest.py`

Fixture file of the retired code only; no tests.

### `tests/tools/conftest.py`

Fixture file of the retired code only; no tests.

### `tests/aebench/test_agent.py`

| Old test | Disposition | Covering test or reason |
|---|---|---|
| `test_vietnamese_prompt_is_the_vendored_prompt` | CASE-0031 only | the vendored CASE-0031 system prompt |
| `test_calls_are_recorded_with_the_refusing_layer` | rebuilt by a later task | Task 6 (call records) and Task 5 (which tier refused: test_database_only_refuses_the_same_calls_with_platform_rule) |
| `test_followup_arrives_after_the_playbook_succeeds` | CASE-0031 only | CASE-0031 follow-up attacks |
| `test_followup_is_not_sent_on_another_step` | CASE-0031 only | CASE-0031 follow-up attacks; payload delivery on bench_v1 is Task 4 |
| `test_a_model_that_stops_early_is_reminded_then_reported` | CASE-0031 only | CASE-0031 playbook completeness |
| `test_invented_money_is_refused_only_with_the_business_layer` | rebuilt by a later task | Task 5: test_none_lets_de_decide_own_request_pay_unapproved_and_invent_price |
| `test_a_guard_refusal_is_attributed_to_the_guard` | rebuilt by a later task | Task 6: test_guard_block_recorded_and_tool_not_called |
| `test_every_process_intent_has_a_playbook` | CASE-0031 only | - |
| `test_english_needs_a_translation` | CASE-0031 only | English locale of the CASE-0031 prompts |

### `tests/aebench/test_attacks_extended.py`

| Old test | Disposition | Covering test or reason |
|---|---|---|
| `test_extended_catalog_exists_and_loads` | CASE-0031 only | CASE-0031 attack catalog |
| `test_all_seventeen_safety_properties_are_covered` | CASE-0031 only | - |
| `test_all_four_delivery_channels_are_represented` | CASE-0031 only | - |
| `test_all_four_cpv_classes_are_represented` | CASE-0031 only | - |
| `test_all_target_steps_are_valid_de_handlers` | CASE-0031 only | - |
| `test_every_attack_fits_canon_case` | CASE-0031 only | - |
| `test_translatable_strings_succeeds_on_extended_catalog` | CASE-0031 only | - |

### `tests/aebench/test_baselines.py`

| Old test | Disposition | Covering test or reason |
|---|---|---|
| `test_llama_guard_verdict_safe` | covered | `tests/aebench/bridges/test_llama_guard.py::test_safe_and_unsafe_replies_map_to_verdicts` |
| `test_llama_guard_verdict_unsafe` | covered | `tests/aebench/bridges/test_llama_guard.py::test_safe_and_unsafe_replies_map_to_verdicts` |
| `test_llama_guard_unreadable_fails_closed` | covered | `tests/aebench/bridges/test_llama_guard.py::test_unreadable_reply_fails_closed_and_counts` |
| `test_nemo_guardrails_blocks_out_of_scope_action` | covered | `tests/aebench/bridges/test_nemo.py::test_rails_run_inside_llmrails` |
| `test_nemo_guardrails_blocks_terminal_status_and_approvals` | covered | `tests/aebench/bridges/test_nemo.py::test_rails_run_inside_llmrails` |
| `test_nemo_guardrails_blocks_excessive_discount` | covered | `tests/aebench/bridges/test_nemo.py::test_cap_rail_blocks_a_value_over_the_pack_cap` |
| `test_agentdojo_blocks_prompt_injections` | covered | `tests/aebench/bridges/test_agentdojo.py::test_injection_in_a_tool_result_is_replaced_by_the_original_transform` (the original detector replaces the old regex checks) |
| `test_camel_capability_enforces_grants` | covered | `tests/aebench/bridges/test_camel.py::test_untrusted_data_flowing_into_a_state_changing_call_is_denied_by_camel` |
| `test_build_guard_factory` | covered | `tests/aebench/test_defence.py::test_build_defence_has_a_bridge_for_every_guard_arm` |
| `test_baseline_governance_presets` | covered | `tests/aebench/test_defence.py::test_arms_table_has_progent_and_no_llm_guard` |

### `tests/aebench/test_benign.py`

| Old test | Disposition | Covering test or reason |
|---|---|---|
| `test_load_all_benign_cases` | CASE-0031 only | CASE-0031 benign hard cases |
| `test_tonomyx_full_and_step_gateway_zero_over_refusal` | CASE-0031 only | CASE-0031 benign hard cases; wrongly-blocked scoring on bench_v1 is Task 8 |
| `test_agentdojo_false_refusal_on_benign_delimiters` | covered | `tests/aebench/bridges/test_agentdojo.py::test_benign_vietnamese_result_passes_unchanged` |
| `test_llm_judge_false_refusal_attribution` | rebuilt by a later task | Task 7 / Task 8 |
| `test_llama_guard_false_refusal_attribution` | rebuilt by a later task | Task 7 / Task 8 |
| `test_benign_table_and_metrics_summary` | rebuilt by a later task | Task 8: test_benign_refused_stop_is_wrongly_blocked; Task 12 (report) |

### `tests/aebench/test_bpic19.py`

| Old test | Disposition | Covering test or reason |
|---|---|---|
| `test_bpic19_suite_completeness` | CASE-0031 only | CASE-0031 variants from BPIC19 profiles |
| `test_bpic_to_case_spec_conversion` | CASE-0031 only | - |

### `tests/aebench/test_cases.py`

| Old test | Disposition | Covering test or reason |
|---|---|---|
| `test_generation_is_deterministic_in_its_seed` | CASE-0031 only | CASE-0031 variant generator |
| `test_every_stratum_is_covered_equally` | CASE-0031 only | - |
| `test_a_spec_survives_serialisation` | CASE-0031 only | - |
| `test_a_spec_refuses_an_impossible_case` | CASE-0031 only | - |

### `tests/aebench/test_composition.py`

| Old test | Disposition | Covering test or reason |
|---|---|---|
| `test_clean_grn12_has_an_empty_report` | CASE-0031 only | composition rules over CASE-0031 traces |
| `test_split_discounts_recover_threshold_laundering` | CASE-0031 only | - |
| `test_two_payments_recover_cumulative_sum` | CASE-0031 only | generic rule: `tests/core/test_platform_rules_db.py::test_a_document_is_paid_once` |
| `test_needs_check_payment_recovers_context_collapse` | CASE-0031 only | - |
| `test_two_purchase_orders_are_a_silent_quantity_witness` | CASE-0031 only | generic counterpart: `tests/bench/test_score.py::test_a_second_purchase_order_is_unexpected` [not in this copy] |
| `test_purchase_item_outside_the_quote_is_a_silent_witness` | CASE-0031 only | - |
| `test_restatement_without_a_silent_witness_does_not_satisfy` | CASE-0031 only | - |
| `test_reference_episode_carries_an_empty_composition_report` | CASE-0031 only | - |

### `tests/aebench/test_experiment_schedule.py`

| Old test | Disposition | Covering test or reason |
|---|---|---|
| `test_e0_counts_attacks_and_case_controls` | CASE-0031 only | v1 experiment files |
| `test_e2_cell_is_534_and_the_layer_slice_stands_alone` | CASE-0031 only | - |
| `test_e5_pairs_vietnamese_and_english_on_the_same_seed` | CASE-0031 only | - |
| `test_e6_accepts_none_beside_all` | CASE-0031 only | - |
| `test_followup_probe_names_the_exploit_after_the_playbook` | CASE-0031 only | - |
| `test_followup_held_covers_the_attacks_full_blocks` | CASE-0031 only | - |
| `test_e3_followup_is_one_case_of_the_five_cpv_attacks` | CASE-0031 only | - |
| `test_e1_names_every_local_model_including_the_guard` | CASE-0031 only | - |
| `test_a_missing_local_model_is_refused_before_any_episode` | rebuilt by a later task | `tests/aebench/test_runner.py::test_unavailable_stops_and_resume_skips_done` [not in this copy] (model identity is read before any episode); the model check itself: `tests/models/test_chat.py::test_missing_ollama_models_accepts_latest_for_a_bare_name` |
| `test_a_hosted_model_without_a_key_is_refused` | rebuilt by a later task | Task 2: test_missing_key_is_model_unavailable; the key check itself: `tests/models/test_chat.py::test_frontier_setup_error_follows_the_provider` |
| `test_guard_sampling_does_not_leave_thinking_on` | rebuilt by a later task | `tests/aebench/test_runner.py::test_guard_sampling_does_not_leave_thinking_on` [not in this copy]; in a run: `tests/aebench/test_runner.py::test_each_repetition_has_its_own_seed_for_model_and_guard` [not in this copy] |
| `test_infrastructure_failure_is_a_missed_endpoint_not_a_tool_refusal` | rebuilt by a later task | `tests/aebench/test_runner.py::test_unavailable_stops_and_resume_skips_done` [not in this copy] |
| `test_listed_files_exist` | CASE-0031 only | - |
| `test_indirect_paper_schedule_matches_full_and_leaves_the_probe` | CASE-0031 only | - |
| `test_explicit_turn_keeps_the_stored_repetition` | CASE-0031 only | - |
| `test_clean_schedule_keeps_stored_full_ids` | CASE-0031 only | - |
| `test_ledger_keeps_a_finished_clean_grid_when_baselines_are_absent` | moved | `tests/test_update_experiment_ledger.py::test_ledger_keeps_a_finished_clean_grid_when_baselines_are_absent` [not in this copy] |
| `test_ledger_names_the_indirect_paper_cell` | moved | `tests/test_update_experiment_ledger.py::test_ledger_names_the_indirect_paper_cell` [not in this copy] |
| `test_ledger_checklist_does_not_reopen_finished_runs` | moved | `tests/test_update_experiment_ledger.py::test_ledger_checklist_does_not_reopen_finished_runs` [not in this copy] |
| `test_confirmatory_schedule_is_three_local_models` | CASE-0031 only | - |

### `tests/aebench/test_frontier_llm.py`

| Old test | Disposition | Covering test or reason |
|---|---|---|
| `test_is_frontier_model` | moved | `tests/models/test_chat.py::test_is_frontier_model` |
| `test_create_chat_model_routing` | moved | `tests/models/test_chat.py::test_create_chat_model_routing` |
| `test_openai_chat_mock_completion` | moved | `tests/models/test_chat.py::test_openai_chat_mock_completion` |
| `test_openai_chat_message_normalization` | moved | `tests/models/test_chat.py::test_openai_chat_message_normalization` |
| `test_streamed_tool_call_is_one_message` | moved | `tests/models/test_chat.py::test_streamed_tool_call_is_one_message` |
| `test_ollama_chat_caps_context_below_the_48gib_default` | moved | `tests/models/test_chat.py::test_ollama_chat_caps_context_below_the_48gib_default` |
| `test_ollama_chat_retries_once_after_a_runner_500` | moved | `tests/models/test_chat.py::test_ollama_chat_retries_once_after_a_runner_500` |
| `test_ollama_chat_retries_once_after_a_read_timeout` | moved | `tests/models/test_chat.py::test_ollama_chat_retries_once_after_a_read_timeout` |
| `test_missing_ollama_models_accepts_latest_for_a_bare_name` | moved | `tests/models/test_chat.py::test_missing_ollama_models_accepts_latest_for_a_bare_name` |
| `test_frontier_setup_error_follows_the_provider` | moved | `tests/models/test_chat.py::test_frontier_setup_error_follows_the_provider` |

### `tests/aebench/test_hardening.py`

| Old test | Disposition | Covering test or reason |
|---|---|---|
| `test_a_garbled_status_is_refused` | covered | `tests/core/test_schema.py::test_vocab_enforced` |
| `test_a_verdict_that_disagrees_with_fn_reconcile_is_refused` | CASE-0031 only | hardening.sql over canon fn_reconcile (the full-hardened arm, retired by Q1) |
| `test_a_payment_born_paid_is_refused` | covered | `tests/enforce/test_platform_rules_attack.py::test_rule_4_through_raw_sql`; `tests/core/test_platform_rules_db.py::test_payment_needs_approved_chain_at_db_tier` |
| `test_a_second_payment_and_a_second_receipt_are_refused` | covered | `tests/core/test_platform_rules_db.py::test_a_document_is_paid_once` (payment; a second receipt is legal on the generic schema) |

### `tests/aebench/test_hr_postgres.py`

| Old test | Disposition | Covering test or reason |
|---|---|---|
| `test_hr_process_end_to_end_on_live_postgres` | CASE-0031 only | canon HR branch |
| `test_hr_adversarial_bypass_blocked_by_interception_and_hardening` | CASE-0031 only | canon HR branch |

### `tests/aebench/test_hr_process.py`

| Old test | Disposition | Covering test or reason |
|---|---|---|
| `test_hr_case_spec_properties_and_serialization` | CASE-0031 only | canon HR branch |
| `test_hr_process_steps_generation` | CASE-0031 only | - |
| `test_hr_reference_executor_registration` | CASE-0031 only | - |
| `test_hr_safety_oracle_logic` | CASE-0031 only | - |

### `tests/aebench/test_i18n.py`

| Old test | Disposition | Covering test or reason |
|---|---|---|
| `test_export_import_round_trip` | CASE-0031 only | translation catalog of the CASE-0031 prompts and attacks |
| `test_a_changed_source_marks_the_english_stale` | CASE-0031 only | - |
| `test_a_standing_rule_selects_every_english_episode` | CASE-0031 only | - |
| `test_one_attack_string_selects_only_that_attack` | CASE-0031 only | - |
| `test_strength_wrapper_selects_only_that_strength` | CASE-0031 only | - |
| `test_an_unread_catalog_id_selects_nothing` | CASE-0031 only | - |
| `test_affected_command_refuses_a_csv` | CASE-0031 only | - |
| `test_selector_does_not_save_the_catalog` | CASE-0031 only | - |

### `tests/aebench/test_interception.py`

| Old test | Disposition | Covering test or reason |
|---|---|---|
| `test_scope_refusal` | rebuilt by a later task | the v1 refusal classifier; attribution is Task 5 (refusals name their tier, e.g. platform rule N). The refusal itself: `tests/engine/test_run.py::test_table_outside_the_token_is_refused` |
| `test_capability_refusal` | rebuilt by a later task | v1 refusal classifier (Task 5). The refusal itself: `tests/engine/test_toolbox.py::test_a_tool_outside_the_step_is_refused` |
| `test_business_refusal` | rebuilt by a later task | v1 refusal classifier (Task 5). The refusal itself: `tests/tools_core/test_approvals.py::test_request_refused_when_the_maker_would_check` |
| `test_schema_refusal` | rebuilt by a later task | v1 refusal classifier (Task 5). The refusal itself: `tests/core/test_platform_rules_db.py::test_events_are_append_only` |
| `test_database_refusal` | rebuilt by a later task | v1 refusal classifier (Task 5: test_database_only_refuses_the_same_calls_with_platform_rule). The refusal itself: `tests/enforce/test_platform_rules_attack.py::test_rule_4_through_raw_sql`; `tests/tools_core/test_documents.py::test_database_refusal_becomes_tool_denied` |
| `test_constraint_refusal` | rebuilt by a later task | v1 refusal classifier (Task 5). The refusal itself: `tests/core/test_schema.py::test_foreign_keys_enforced` |

### `tests/aebench/test_oracle.py`

| Old test | Disposition | Covering test or reason |
|---|---|---|
| `test_property_ids_are_unique` | CASE-0031 only | the 17 CASE-0031 safety properties; bench_v1 safety is Task 8 |
| `test_canon_scenarios_violate_nothing` | CASE-0031 only | - |
| `test_generated_variants_run_clean_under_the_reference` | CASE-0031 only | - |
| `test_each_planted_violation_is_caught` | CASE-0031 only | Task 8: test_forbidden_payment_happened is the bench_v1 counterpart |
| `test_fidelity_is_exact_against_itself_and_counts_differences` | covered | `tests/bench/test_score.py::test_identity_mapping_scores_perfect` [not in this copy]; `tests/bench/test_score.py::test_wrong_amount_fails_its_invariant` [not in this copy] |

### `tests/aebench/test_quality.py`

| Old test | Disposition | Covering test or reason |
|---|---|---|
| `test_comments_docstrings_and_identifiers_are_english` | moved | folded into `tests/quality/test_comments_are_english.py` (now scans tonomyx/ and aebench/) |
| `test_no_large_integer_literals` | moved | folded into `tests/quality/test_no_money_literals.py::test_no_large_integer_literals_outside_the_allowlist` (now scans tonomyx/ and aebench/; 32768 and 4096 in tonomyx/models/chat.py allow-listed as token counts) |

### `tests/aebench/test_reference_process.py`

| Old test | Disposition | Covering test or reason |
|---|---|---|
| `test_reference_reproduces_tonomyx_flow` | CASE-0031 only | re-run on the engine: `tests/governance/test_canon_pack_on_engine.py::test_canon_scenarios_match_old_outcomes` |
| `test_the_process_has_eleven_steps_and_seven_digital_employee_tasks` | CASE-0031 only | - |

### `tests/aebench/test_structural_matrix.py`

| Old test | Disposition | Covering test or reason |
|---|---|---|
| `test_every_attack_is_pinned` | CASE-0031 only | CASE-0031 compromised-model matrix |
| `test_structural_guarantee` | CASE-0031 only | CASE-0031; the generic tier guarantees: `tests/enforce/test_platform_rules_attack.py::test_rule_1_through_raw_sql` and the other rule tests there |
| `test_without_an_attack_the_adversary_is_the_reference` | CASE-0031 only | - |
