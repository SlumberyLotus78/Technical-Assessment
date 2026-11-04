# Catálogo de pruebas

## Alcance

El catálogo describe los 259 casos de la suite: 168 sin servidor PostgreSQL y 91 de integración SQL. Los casos se identifican por su clase y método para poder localizarlos en el código.

Las pruebas utilizan datos ficticios, capturas archivadas y HTTP simulado. Los casos SQL usan PostgreSQL real, con una base desechable por caso. El runner carga únicamente `TEST_DATABASE_URL` desde el archivo indicado, valida el prefijo `grain_test_` y no utiliza `DATABASE_URL` como alternativa. No se realizan consultas reales a FRED o Banxico ni escrituras en la base del producto.

## Resultado de la entrega

Se ejecutaron y aprobaron **las 259 pruebas: 168 sin servidor y 91 de integración PostgreSQL**, con cero fallos, errores u omisiones.

El [resumen de resultados](evidencias/entrega_final/resumen_pruebas.json) resume los resultados de la suite completa con Python 3.12.4 y PostgreSQL 18.6.

## Ejecución reproducible

Se requiere instalar las dependencias del proyecto, incluido `cryptography`. Para integración SQL, PostgreSQL debe estar disponible y el usuario de pruebas debe tener permisos `CREATEDB` y `CREATEROLE`. La base de conexión debe existir y comenzar por `grain_test_`.

```powershell
.\.venv\Scripts\python.exe -X utf8 -m tests.run --postgres --env-file .env --report data/informe_pruebas.json
```

El directorio del informe debe existir y el archivo debe ser nuevo. El modo `--postgres` exige cero omisiones. Cada caso SQL cierra sus conexiones y elimina su base UUID al finalizar. La prueba de acceso de solo lectura crea un rol temporal con contraseña aleatoria, concede únicamente consultas al dashboard y retira el rol y sus permisos al finalizar. Para ejecutar solamente los casos sin servidor, se utiliza `python -m tests.run`, que omite los 91 casos SQL.

## Catálogo por módulo

| Módulo | Casos | Tipo | Qué comprueba |
|---|---:|---|---|
| [test_analytics](../tests/test_analytics.py) | 7 | Sin servidor | Identidades numéricas y denominadores del análisis; sin PostgreSQL ni APIs. |
| [test_api_credentials](../tests/test_api_credentials.py) | 5 | Sin servidor | Cifrado, contraseñas y escritura de configuración local con credenciales ficticias. |
| [test_automation](../tests/test_automation.py) | 7 | Sin servidor | Contratos de distribución y del ejecutor programado; sin APIs ni base del proyecto. |
| [test_banking_calendar](../tests/test_banking_calendar.py) | 9 | Sin servidor | Calendario de referencia independiente y controles de fechas bancarias FIX. |
| [test_configuration](../tests/test_configuration.py) | 4 | Sin servidor | Comprobaciones de configuración con archivos y claves ficticias. |
| [test_contracts](../tests/test_contracts.py) | 12 | Sin servidor | Escenarios ficticios para las reglas de metadatos, sin comunicación HTTP. |
| [test_dashboard](../tests/test_dashboard.py) | 2 | Sin servidor | Interacción y privacidad de la interfaz mediante Streamlit AppTest, sin servidor SQL. |
| [test_database](../tests/test_database.py) | 9 | Sin servidor | Configuración y errores PostgreSQL sin consultar una base ni leer .env real. |
| [test_dates](../tests/test_dates.py) | 6 | Sin servidor | Casos de calendario y formatos que utilizarán las ventanas de consulta. |
| [test_gold](../tests/test_gold.py) | 13 | Sin servidor | Agregación, referencias y variaciones con datos ficticios y capturas archivadas. |
| [test_historical](../tests/test_historical.py) | 9 | Sin servidor | Planificación, capturas y perfil histórico sin APIs ni PostgreSQL. |
| [test_http](../tests/test_http.py) | 6 | Sin servidor | Pruebas del transporte HTTP con sesiones y respuestas simuladas. |
| [test_incremental](../tests/test_incremental.py) | 8 | Sin servidor | Plan incremental y argumentos sin PostgreSQL ni consultas reales. |
| [test_metadata](../tests/test_metadata.py) | 3 | Sin servidor | Pruebas de selección e identidad de series con respuestas ficticias. |
| [test_observations](../tests/test_observations.py) | 6 | Sin servidor | Contratos de observaciones y parámetros de consulta con transporte simulado. |
| [test_postgres_dashboard](../tests/test_postgres_dashboard.py) | 7 | PostgreSQL | Lectura del dashboard sobre PostgreSQL real aislado, con permisos e instantáneas. |
| [test_postgres_historical](../tests/test_postgres_historical.py) | 10 | PostgreSQL | Histórico completo con PostgreSQL desechable y respuestas HTTP ficticias. |
| [test_postgres_incremental](../tests/test_postgres_incremental.py) | 15 | PostgreSQL | Incremental con PostgreSQL real desechable y HTTP simulado, usando exclusivamente la conexión de pruebas. |
| [test_postgres_persistence](../tests/test_postgres_persistence.py) | 11 | PostgreSQL | Persistencia real sobre archivos ficticios y bases PostgreSQL desechables. |
| [test_postgres_publication](../tests/test_postgres_publication.py) | 21 | PostgreSQL | Publicación real con capturas ficticias y bases PostgreSQL desechables. |
| [test_postgres_recovery](../tests/test_postgres_recovery.py) | 12 | PostgreSQL | Recuperación y reproceso sobre bases desechables; ningún dato del proyecto se utiliza. |
| [test_postgres_schema](../tests/test_postgres_schema.py) | 11 | PostgreSQL | Esquema y restricciones SQL en bases desechables, con conexión de pruebas explícita. |
| [test_postgres_state](../tests/test_postgres_state.py) | 4 | PostgreSQL | Preflight del scheduler en una base propia y transacciones de solo lectura. |
| [test_profiling](../tests/test_profiling.py) | 6 | Sin servidor | Escenarios de calidad y cobertura mensual con registros preparados en memoria. |
| [test_publication_rules](../tests/test_publication_rules.py) | 7 | Sin servidor | Reglas puras de publicación: continuidad, contexto, duplicados y procedencia. |
| [test_recovery_rules](../tests/test_recovery_rules.py) | 6 | Sin servidor | Decisiones de recuperación y límites de corrección, sin servidor ni red. |
| [test_retry](../tests/test_retry.py) | 6 | Sin servidor | Reintentos con transporte y esperas simulados; nunca realiza llamadas externas. |
| [test_sample](../tests/test_sample.py) | 6 | Sin servidor | Muestra completa con APIs simuladas y capturas en carpetas temporales. |
| [test_sampling](../tests/test_sampling.py) | 9 | Sin servidor | Planificación de una muestra con metadatos y fechas de referencia ficticios. |
| [test_silver](../tests/test_silver.py) | 14 | Sin servidor | Capturas, reglas y preparación Silver sin APIs ni conexiones PostgreSQL. |
| [test_test_runner](../tests/test_test_runner.py) | 3 | Sin servidor | Configuración explícita de integración, sin leer el .env real ni conectar. |
| [test_values](../tests/test_values.py) | 5 | Sin servidor | Reglas numéricas con ejemplos ficticios; no se consultan fuentes reales. |

## Inventario de casos

Los nombres conservan los identificadores del código. El propósito de cada grupo se describe en la tabla anterior.

### test_analytics

- `AnalyticalTests.test_indices_use_selected_base_and_mom_keeps_exact_previous_month`.
- `AnalyticalTests.test_symmetric_attribution_reconciles_product_change_and_percentage_points`.
- `AnalyticalTests.test_zero_denominator_is_null_and_one_month_has_zero_cumulative_change`.
- `AnalyticalTests.test_decimal_context_is_local_and_inputs_are_preserved`.
- `AnalyticalTests.test_dashboard_contract_rejects_missing_duplicate_and_inconsistent_gold`.
- `AnalyticalTests.test_charts_have_expected_traces_and_reject_nonrepresentable_values`.
- `AnalyticalTests.test_readonly_override_is_optional_literal_and_empty_values_are_rejected`.

### test_api_credentials

- `ApiCredentialsTests.test_round_trip_and_random_salt`.
- `ApiCredentialsTests.test_wrong_password_and_tampering_are_rejected`.
- `ApiCredentialsTests.test_update_preserves_database_and_literal_credentials`.
- `ApiCredentialsTests.test_create_from_template`.
- `ApiCredentialsTests.test_short_password_rejected`.

### test_automation

- `ScheduledExecutionTests.test_installed_child_is_isolated_and_only_invokes_incremental_with_absolute_paths`.
- `ScheduledExecutionTests.test_child_exit_code_is_propagated_and_logs_are_retained`.
- `ScheduledExecutionTests.test_timeout_and_launch_failure_do_not_expose_original_exception_details`.
- `ScheduledExecutionTests.test_readiness_mode_uses_only_the_state_command`.
- `ScheduledExecutionTests.test_invalid_bounds_and_missing_configuration_prevent_child_execution`.
- `ScheduledExecutionTests.test_missing_dashboard_extra_and_invalid_port_are_controlled`.
- `DistributionContractTests.test_package_and_development_requirements_have_the_same_runtime_versions`.

### test_banking_calendar

- `BankingReferenceTests.test_september_has_the_exact_expected_dates_and_versioned_evidence`.
- `BankingReferenceTests.test_banking_closures_and_weekends_are_excluded_without_moving_holidays`.
- `BankingReferenceTests.test_unknown_year_and_invalid_month_do_not_produce_a_fabricated_calendar`.
- `BankingReferenceTests.test_incompatible_resource_is_an_error_and_crlf_preserves_the_fingerprint`.
- `FixCoverageTests.test_complete_month_passes_and_does_not_modify_inputs`.
- `FixCoverageTests.test_same_count_with_a_wrong_date_reports_missing_and_unexpected`.
- `FixCoverageTests.test_duplicates_empty_and_outside_dates_block_the_month`.
- `FixCoverageTests.test_bad_values_dates_and_series_cannot_certify_coverage`.
- `FixCoverageTests.test_unreviewed_year_is_pending_and_invalid_rows_still_fail`.

### test_configuration

- `CredentialConfigurationTests.test_file_values_remain_literal_and_accept_utf8_bom`.
- `CredentialConfigurationTests.test_environment_value_overrides_file_value`.
- `CredentialConfigurationTests.test_empty_environment_value_requires_correction`.
- `CredentialConfigurationTests.test_missing_credential_message_excludes_available_value`.

### test_contracts

- `MetadataContractTests.test_expected_metadata_is_accepted_for_all_series`.
- `MetadataContractTests.test_text_normalization_preserves_original_values`.
- `MetadataContractTests.test_wrong_units_are_rejected`.
- `MetadataContractTests.test_wrong_frequencies_are_rejected`.
- `MetadataContractTests.test_wrong_titles_are_rejected`.
- `MetadataContractTests.test_missing_required_fields_are_rejected`.
- `MetadataContractTests.test_non_text_required_fields_are_rejected`.
- `MetadataContractTests.test_wrong_classification_is_rejected`.
- `MetadataContractTests.test_date_ranges_are_read_for_both_providers`.
- `MetadataContractTests.test_missing_or_invalid_date_values_are_rejected`.
- `MetadataContractTests.test_reversed_date_ranges_are_rejected`.
- `MetadataContractTests.test_monthly_range_dates_must_identify_month_start`.

### test_dashboard

- `DashboardInteractionTests.test_filters_units_and_one_month_selection_keep_three_charts`.
- `DashboardInteractionTests.test_missing_configuration_and_database_errors_are_controlled_and_private`.

### test_database

- `DatabaseConfigurationTests.test_database_configuration_works_without_api_credentials`.
- `DatabaseConfigurationTests.test_environment_overrides_file_and_empty_values_require_correction`.
- `DatabaseConfigurationTests.test_database_configuration_preserves_literal_values`.
- `DatabaseConnectionTests.test_missing_database_name_prevents_connection`.
- `DatabaseConnectionTests.test_invalid_connection_string_excludes_its_original_value`.
- `DatabaseConnectionTests.test_connection_has_bounded_wait_and_utc_session`.
- `DatabaseConnectionTests.test_connection_error_excludes_private_driver_details`.
- `DatabaseCommandTests.test_missing_configuration_does_not_open_a_connection`.
- `DatabaseCommandTests.test_sql_error_does_not_print_connection_or_original_message`.

### test_dates

- `DateOperationsTests.test_source_formats_produce_calendar_dates`.
- `DateOperationsTests.test_nonstandard_and_impossible_dates_are_rejected`.
- `DateOperationsTests.test_month_argument_requires_year_and_month`.
- `DateOperationsTests.test_month_shift_crosses_year_without_fixed_day_counts`.
- `DateOperationsTests.test_month_end_respects_leap_years`.
- `DateOperationsTests.test_month_shift_rejects_out_of_calendar_range`.

### test_gold

- `GoldCalculationTests.test_known_mean_and_references_use_decimal_and_preserve_input`.
- `GoldCalculationTests.test_calculations_ignore_and_restore_the_callers_decimal_context`.
- `GoldCalculationTests.test_missing_grain_duplicate_and_invalid_silver_inputs_block_gold`.
- `GoldCalculationTests.test_missing_or_unexpected_fix_and_unreviewed_year_block_gold`.
- `GoldCalculationTests.test_current_future_and_invalid_month_windows_are_rejected`.
- `GoldCalculationTests.test_complete_interval_and_revision_recalculate_dependent_changes`.
- `GoldCalculationTests.test_half_even_precision_and_numeric_extremes_are_controlled`.
- `ReferenceChangesTests.test_mom_and_yoy_use_the_correct_month_and_allow_negative_and_zero`.
- `ReferenceChangesTests.test_internal_gaps_and_duplicate_references_are_rejected`.
- `ReferenceChangesTests.test_month_ranges_include_year_boundaries_and_the_maximum_date`.
- `GoldPreviewTests.test_archived_real_month_has_complete_fix_and_three_references`.
- `GoldPreviewTests.test_cli_can_export_a_new_report_and_never_overwrites_it`.
- `GoldPreviewTests.test_missing_capture_partial_month_and_invalid_cli_month_fail`.

### test_historical

- `HistoricalPlanningTests.test_yearly_windows_cover_the_exact_requested_period`.
- `HistoricalPlanningTests.test_metadata_availability_and_all_calendars_are_required`.
- `HistoricalPlanningTests.test_daily_metadata_can_end_on_the_last_banking_day_before_month_end`.
- `HistoricalPlanningTests.test_open_reversed_and_non_initial_months_are_rejected`.
- `HistoricalPlanningTests.test_reviewed_resources_preserve_exceptions_and_previous_evidence`.
- `HistoricalCaptureTests.test_metadata_and_yearly_observations_build_a_consolidated_profile`.
- `HistoricalCaptureTests.test_incompatible_metadata_response_is_archived_before_rejection`.
- `HistoricalCaptureTests.test_cli_missing_private_configuration_does_not_connect_or_query_sources`.
- `HistoricalCaptureTests.test_cli_missing_timezone_returns_a_controlled_error_before_configuration`.

### test_http

- `HttpClientTests.test_fred_authentication_and_connection_options`.
- `HttpClientTests.test_banxico_token_uses_header`.
- `HttpClientTests.test_http_errors_release_response_and_exclude_private_body`.
- `HttpClientTests.test_connection_errors_exclude_original_exception_details`.
- `HttpClientTests.test_invalid_response_formats_are_rejected`.
- `HttpClientTests.test_invalid_destinations_and_private_parameters_are_rejected`.

### test_incremental

- `IncrementalPlanningTests.test_three_month_review_includes_the_last_three_published_months`.
- `IncrementalPlanningTests.test_new_months_are_added_without_holes_and_zero_review_starts_after_watermark`.
- `IncrementalPlanningTests.test_zero_review_and_no_new_months_has_no_observation_window`.
- `IncrementalPlanningTests.test_common_month_respects_a_lagging_grain_and_the_last_closed_month`.
- `IncrementalPlanningTests.test_revision_window_clips_to_baseline_and_crosses_years`.
- `IncrementalPlanningTests.test_source_regression_and_invalid_end_caps_are_rejected`.
- `IncrementalPlanningTests.test_missing_baseline_invalid_review_and_open_watermark_fail`.
- `IncrementalCommandTests.test_invalid_configuration_review_and_timezone_do_not_connect`.

### test_metadata

- `MetadataTests.test_fred_endpoint_and_identifier`.
- `MetadataTests.test_banxico_endpoint_and_identifier`.
- `MetadataTests.test_wrong_identifiers_errors_and_shapes_are_rejected`.

### test_observations

- `ObservationSourceTests.test_fred_requests_original_values_for_the_requested_window`.
- `ObservationSourceTests.test_banxico_uses_iso_request_dates_and_preserves_response_dates`.
- `ObservationSourceTests.test_invalid_range_or_provider_prevents_the_request`.
- `ObservationSourceTests.test_fred_rejects_partial_pages_changed_units_and_invalid_shapes`.
- `ObservationSourceTests.test_banxico_rejects_wrong_series_errors_and_missing_fields`.
- `ObservationSourceTests.test_mapping_leaves_native_payload_and_text_precision_unchanged`.

### test_postgres_dashboard

- `PostgresDashboardTests.test_uninitialized_product_returns_a_controlled_empty_snapshot`.
- `PostgresDashboardTests.test_published_snapshot_has_decimal_values_and_does_not_change_control`.
- `PostgresDashboardTests.test_readonly_connection_rejects_writes_even_with_an_admin_account`.
- `PostgresDashboardTests.test_a_select_only_login_can_read_the_dashboard`.
- `PostgresDashboardTests.test_corrupt_gold_is_reported_instead_of_plotting_partial_or_wrong_values`.
- `PostgresDashboardTests.test_repeatable_read_does_not_mix_two_publications`.
- `PostgresDashboardTests.test_interface_runs_against_the_real_readonly_query_and_reacts_to_filters`.

### test_postgres_historical

- `PostgresHistoricalTests.test_complete_month_has_durable_artifacts_and_no_open_transaction_during_http`.
- `PostgresHistoricalTests.test_selected_2009_2026_period_reaches_gold_with_all_expected_rows`.
- `PostgresHistoricalTests.test_existing_baseline_rejects_another_initial_history_without_api_calls`.
- `PostgresHistoricalTests.test_exhausted_network_failure_keeps_previous_captures_and_private_error_out_of_logs`.
- `PostgresHistoricalTests.test_incompatible_metadata_is_registered_before_the_contract_fails`.
- `PostgresHistoricalTests.test_missing_calendar_stops_before_observation_requests`.
- `PostgresHistoricalTests.test_truncated_fred_page_is_archived_and_blocks_further_requests`.
- `PostgresHistoricalTests.test_incomplete_fix_has_a_consolidated_profile_and_durable_failed_coverage`.
- `PostgresHistoricalTests.test_publication_failure_keeps_its_actual_stage_instead_of_reclosing_as_extraction`.
- `PostgresHistoricalTests.test_cli_loads_only_fixture_configuration_and_runs_the_real_historical_path`.

### test_postgres_incremental

- `PostgresIncrementalTests.test_missing_history_is_failed_without_api_calls_or_invoking_historical`.
- `PostgresIncrementalTests.test_review_without_new_months_confirms_checks_and_preserves_fact_audit`.
- `PostgresIncrementalTests.test_full_original_history_fetches_only_recent_window_to_add_october`.
- `PostgresIncrementalTests.test_grain_revision_updates_its_reference_and_later_mom`.
- `PostgresIncrementalTests.test_fix_revision_changes_the_monthly_average_and_all_three_references`.
- `PostgresIncrementalTests.test_no_new_months_with_review_disabled_skips_without_touching_watermark`.
- `PostgresIncrementalTests.test_skip_cannot_hide_inconsistent_gold_and_does_not_repair_it_silently`.
- `PostgresIncrementalTests.test_catch_up_with_zero_review_includes_all_new_months`.
- `PostgresIncrementalTests.test_year_boundary_uses_two_windows_without_duplicate_dates`.
- `PostgresIncrementalTests.test_source_regression_fails_before_observations_and_preserves_publication`.
- `PostgresIncrementalTests.test_incomplete_declared_fix_or_unreviewed_new_year_stops_before_observations`.
- `PostgresIncrementalTests.test_failure_after_watermark_update_rolls_back_increment_and_keeps_new_captures`.
- `PostgresIncrementalTests.test_network_uses_idle_sql_connection_and_holds_the_product_lock`.
- `PostgresIncrementalTests.test_skipped_finalizer_and_period_assignment_reject_incompatible_attempts`.
- `PostgresIncrementalTests.test_cli_uses_fixture_configuration_and_never_initializes_history`.

### test_postgres_persistence

- `PostgresPersistenceTests.test_run_stages_failure_and_private_error_details`.
- `PostgresPersistenceTests.test_invalid_plans_and_autocommit_are_rejected`.
- `PostgresPersistenceTests.test_capture_registration_is_repeatable_without_reassigning_original_run`.
- `PostgresPersistenceTests.test_modified_capture_is_detected_before_any_observation_write`.
- `PostgresPersistenceTests.test_initial_insert_and_unchanged_repeat_preserve_precision_and_audit_fields`.
- `PostgresPersistenceTests.test_source_revision_updates_only_the_changed_row_and_preserves_creation`.
- `PostgresPersistenceTests.test_failed_data_preserves_committed_dq_without_publishing_observations`.
- `PostgresPersistenceTests.test_helpers_leave_commit_and_rollback_to_the_coordinator`.
- `PostgresPersistenceTests.test_wrong_capture_type_plan_interval_and_closed_run_are_rejected`.
- `PostgresPersistenceTests.test_profile_rules_are_saved_with_provenance_and_daily_calendar_pending`.
- `PostgresPersistenceTests.test_catalog_or_registered_source_context_changes_block_silver`.

### test_postgres_publication

- `PostgresPublicationTests.test_initial_history_publishes_all_layers_and_success_together`.
- `PostgresPublicationTests.test_unchanged_repeat_keeps_silver_and_gold_audit_fields`.
- `PostgresPublicationTests.test_revision_recalculates_prior_context_and_later_mom_without_retreating_watermark`.
- `PostgresPublicationTests.test_incremental_requires_baseline_and_then_extends_continuously`.
- `PostgresPublicationTests.test_incremental_without_history_fails_and_preserves_attempt_captures`.
- `PostgresPublicationTests.test_gap_or_earlier_extension_keeps_the_existing_publication`.
- `PostgresPublicationTests.test_missing_fix_preserves_detailed_failed_dq_and_never_publishes`.
- `PostgresPublicationTests.test_invalid_metadata_preserves_its_failed_source_check`.
- `PostgresPublicationTests.test_tampered_registered_capture_blocks_before_silver`.
- `PostgresPublicationTests.test_gold_failure_rolls_back_silver_and_keeps_dq_without_private_error`.
- `PostgresPublicationTests.test_failure_after_gold_reverts_all_product_tables`.
- `PostgresPublicationTests.test_failure_after_watermark_and_success_updates_reverts_them_too`.
- `PostgresPublicationTests.test_other_sessions_see_the_previous_publication_until_commit`.
- `PostgresPublicationTests.test_duplicate_observations_between_captures_have_a_global_failed_check`.
- `PostgresPublicationTests.test_finalizer_cannot_succeed_from_stage_alone_without_gold`.
- `PostgresPublicationTests.test_wrong_gold_value_with_correct_counts_is_detected_before_commit`.
- `PostgresPublicationTests.test_silver_values_must_match_bronze_before_reusing_a_baseline`.
- `PostgresPublicationTests.test_session_lock_survives_commit_and_rollback_and_releases_after_error`.
- `PostgresPublicationTests.test_pending_transactions_and_autocommit_are_rejected_without_confirming_work`.
- `PostgresPublicationTests.test_gold_helper_does_not_commit_and_caller_can_rollback_it`.
- `PostgresPublicationTests.test_unknown_calendar_year_is_logged_pending_and_blocks_publication`.

### test_postgres_recovery

- `PostgresRecoveryTests.test_orphan_is_closed_and_a_new_attempt_reuses_original_capture_owners`.
- `PostgresRecoveryTests.test_failed_attempt_keeps_its_original_failure_when_recovered`.
- `PostgresRecoveryTests.test_partial_and_unplanned_orphans_close_without_fabricating_inputs`.
- `PostgresRecoveryTests.test_active_product_lock_prevents_closing_another_process`.
- `PostgresRecoveryTests.test_later_publication_blocks_replaying_old_corrections`.
- `PostgresRecoveryTests.test_tampered_or_missing_capture_cannot_publish_and_closure_is_durable`.
- `PostgresRecoveryTests.test_failure_after_watermark_rolls_back_and_recovery_child_can_resume`.
- `PostgresRecoveryTests.test_recovery_cli_needs_only_database_configuration`.
- `PostgresRecoveryTests.test_reprocessing_old_month_recalculates_later_mom_and_yoy_without_extending_watermark`.
- `PostgresRecoveryTests.test_unchanged_reprocess_preserves_all_fact_audit_fields`.
- `PostgresRecoveryTests.test_reprocess_rejects_initialization_and_outside_period_before_http`.
- `PostgresRecoveryTests.test_bad_reprocessing_inputs_preserve_previous_product`.

### test_postgres_schema

- `PostgresSchemaTests.test_initialize_twice_and_check_only_preserve_catalog_and_empty_facts`.
- `PostgresSchemaTests.test_failure_rolls_back_schema_catalog_and_version_together`.
- `PostgresSchemaTests.test_occupied_unversioned_schema_is_preserved`.
- `PostgresSchemaTests.test_catalog_mismatch_is_detected_without_overwriting_existing_unit`.
- `PostgresSchemaTests.test_modified_migration_checksum_or_missing_table_are_detected`.
- `PostgresSchemaTests.test_numeric_precision_duplicate_keys_and_foreign_keys`.
- `PostgresSchemaTests.test_missing_non_positive_and_non_finite_values_are_rejected`.
- `PostgresSchemaTests.test_run_status_and_paired_month_constraints`.
- `PostgresSchemaTests.test_gold_accepts_negative_variation_but_rejects_non_finite_values_and_bad_counts`.
- `PostgresSchemaTests.test_dq_scope_and_watermark_interval_constraints`.
- `PostgresSchemaTests.test_concurrent_preparation_creates_one_version_and_one_catalog`.

### test_postgres_state

- `PostgresStateTests.test_missing_historical_publication_is_not_ready_and_creates_no_run`.
- `PostgresStateTests.test_complete_product_is_checked_without_locks_or_writes`.
- `PostgresStateTests.test_modified_originals_or_gold_prevent_registration_readiness`.
- `PostgresStateTests.test_cli_works_without_api_keys_and_exports_only_public_state`.

### test_profiling

- `ObservationProfilingTests.test_complete_monthly_values_preserve_precision_and_do_not_require_sorting`.
- `ObservationProfilingTests.test_a_missing_value_does_not_count_as_a_month_with_usable_data`.
- `ObservationProfilingTests.test_independent_counters_detect_bad_dates_ranges_duplicates_and_values`.
- `ObservationProfilingTests.test_daily_records_do_not_claim_a_verified_banking_calendar`.
- `ObservationProfilingTests.test_empty_responses_are_reported_as_issues`.
- `ObservationProfilingTests.test_incompatible_windows_or_series_are_rejected`.

### test_publication_rules

- `PublicationRulesTests.test_initial_history_and_incremental_require_different_preconditions`.
- `PublicationRulesTests.test_revisions_preserve_the_interval_and_extensions_require_continuity`.
- `PublicationRulesTests.test_capture_set_requires_unique_valid_metadata_and_planned_windows`.
- `PublicationRulesTests.test_combined_checks_detect_duplicates_and_missing_grain_months`.
- `PublicationRulesTests.test_overlay_keeps_revisions_without_mutating_or_hiding_duplicates`.
- `PublicationRulesTests.test_silver_lineage_requires_exact_series_date_and_original_value`.
- `PublicationRulesTests.test_gold_comparison_detects_wrong_values_even_when_counts_match`.

### test_recovery_rules

- `RecoveryRulesTests.test_only_complete_exact_windows_are_reusable`.
- `RecoveryRulesTests.test_newer_publications_and_unplanned_attempts_require_fresh_extraction`.
- `RecoveryRulesTests.test_finished_success_is_not_reopened`.
- `RecoveryRulesTests.test_year_boundary_requires_both_year_windows_for_each_source`.
- `RecoveryRulesTests.test_reprocessing_requires_a_published_interval_and_never_extends_it`.
- `RecoveryRulesTests.test_retry_instruction_distinguishes_initialization_review_and_extension`.

### test_retry

- `RetryPolicyTests.test_delay_accepts_seconds_dates_and_invalid_headers_without_shortening_server_wait`.
- `RetryPolicyTests.test_retryable_response_is_closed_before_waiting_and_then_can_succeed`.
- `RetryPolicyTests.test_429_honors_retry_after_and_excessive_wait_stops_without_an_early_retry`.
- `RetryPolicyTests.test_transient_connection_failure_can_recover_and_exhaustion_is_private`.
- `RetryPolicyTests.test_authentication_tls_and_semantic_errors_are_not_retried`.
- `RetryPolicyTests.test_invalid_attempt_counts_never_open_a_request`.

### test_sample

- `SampleCollectionTests.test_full_sample_preserves_eight_captures_and_writes_a_serializable_profile`.
- `SampleCollectionTests.test_value_issues_still_produce_a_profile_for_all_four_series`.
- `SampleCollectionTests.test_contract_failure_keeps_the_incompatible_capture_without_a_completion_report`.
- `SampleCollectionTests.test_connection_failure_keeps_previous_captures_and_does_not_claim_completion`.
- `SampleCollectionTests.test_new_runs_and_exclusive_writes_preserve_earlier_captures`.
- `SampleCollectionTests.test_cli_returns_a_failure_status_when_the_profile_contains_issues`.

### test_sampling

- `SampleWindowTests.test_provider_windows_have_the_same_final_month`.
- `SampleWindowTests.test_oldest_latest_declared_month_limits_the_sample`.
- `SampleWindowTests.test_current_open_month_is_excluded`.
- `SampleWindowTests.test_january_reference_uses_previous_december`.
- `SampleWindowTests.test_requested_available_month_is_honored`.
- `SampleWindowTests.test_requested_open_unavailable_or_noninitial_month_is_rejected`.
- `SampleWindowTests.test_incomplete_or_duplicate_series_are_rejected`.
- `SampleWindowTests.test_insufficient_history_for_proposed_window_is_rejected`.
- `SampleWindowTests.test_daily_last_date_can_precede_calendar_month_end`.

### test_silver

- `CaptureReaderTests.test_capture_hash_context_and_payload_match_the_file`.
- `CaptureReaderTests.test_paths_outside_the_bronze_root_are_rejected`.
- `CaptureReaderTests.test_invalid_context_dates_and_json_are_rejected`.
- `CaptureReaderTests.test_metadata_has_no_observation_window`.
- `SilverPreparationTests.test_dates_precision_sorting_and_original_records_are_preserved`.
- `SilverPreparationTests.test_invalid_or_incomplete_rows_block_preparation`.
- `SilverPreparationTests.test_daily_dates_are_typed_with_calendar_publication_still_pending`.
- `SilverPreparationTests.test_missing_common_fields_raise_a_controlled_error`.
- `SilverPreparationTests.test_archived_real_sample_can_be_prepared_without_network_or_database`.
- `ProfileRuleTests.test_monthly_missing_value_is_failed_for_value_and_coverage`.
- `ProfileRuleTests.test_daily_rules_keep_calendar_pending_and_omit_monthly_checks`.
- `ProfileRuleTests.test_empty_daily_response_is_failed_even_with_zero_row_error_counts`.
- `SilverPreviewTests.test_preview_accepts_four_captures_and_preserves_all_files`.
- `SilverPreviewTests.test_finder_ignores_incomplete_folders_and_preview_rejects_missing_series`.

### test_test_runner

- `TestRunnerConfigurationTests.test_project_database_url_is_not_used_as_a_fallback`.
- `TestRunnerConfigurationTests.test_test_connection_is_read_without_interpolation_and_environment_has_priority`.
- `TestRunnerConfigurationTests.test_empty_invalid_and_non_test_database_connections_are_rejected_privately`.

### test_values

- `SourceValueTests.test_decimal_preserves_all_digits_from_the_source_text`.
- `SourceValueTests.test_banxico_grouping_requires_complete_thousands_groups`.
- `SourceValueTests.test_missing_markers_are_distinct_from_zero`.
- `SourceValueTests.test_invalid_types_formats_and_non_finite_text_are_rejected`.
- `SourceValueTests.test_zero_and_negative_numbers_remain_visible_for_the_positivity_rule`.
