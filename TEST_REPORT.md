# Test report

Run: 2026-11-12T17:31:47  
Python 3.12.3 on Linux; pandas 2.3.3, fastapi 0.128.8  
Command: `python -m pytest -q` from the project folder (re-run with `python scripts/make_test_report.py`)

**283 passed, 0 failed, 0 skipped, 283 in total.**

What the tests check: every tariff rate used against the Scale of Rates PDF; data files against the official reports; the incentive rules (eligibility, baselines, slabs, approvals, amendments); the end-to-end workflow; the monthly update (rollback on failure, safe re-run). They run on the data held in this project.

| File | Test | Result | Seconds |
|---|---|---|---|
| test_auth_pilot | test_actions_need_login_and_the_right_role | passed | 5.37 |
| test_auth_pilot | test_customer_notes_and_feedback_roles | passed | 0.54 |
| test_auth_pilot | test_demo_mode_without_users | passed | 0.01 |
| test_auth_pilot | test_passwords_are_hashed_and_wrong_password_refused | passed | 0.53 |
| test_download_daily_reports | test_certificate_options | passed | 0.00 |
| test_download_daily_reports | test_dates_in_many_formats[01 Sep 2025-expected5] | passed | 0.00 |
| test_download_daily_reports | test_dates_in_many_formats[01.09.2025-expected1] | passed | 0.00 |
| test_download_daily_reports | test_dates_in_many_formats[01/09/2025-expected2] | passed | 0.00 |
| test_download_daily_reports | test_dates_in_many_formats[1st September 2025-expected4] | passed | 0.00 |
| test_download_daily_reports | test_dates_in_many_formats[2025-09-01.pdf-expected6] | passed | 0.00 |
| test_download_daily_reports | test_dates_in_many_formats[Annual report-None] | passed | 0.00 |
| test_download_daily_reports | test_dates_in_many_formats[Vessel Position 01-09-2025.pdf-expected0] | passed | 0.00 |
| test_download_daily_reports | test_dates_in_many_formats[dvp_01092025.pdf-expected3] | passed | 0.00 |
| test_download_daily_reports | test_downloads_only_wanted_days_and_refuses_non_pdfs | passed | 0.01 |
| test_download_daily_reports | test_dry_run_downloads_nothing | passed | 0.00 |
| test_download_daily_reports | test_excel_workbook_has_every_day_and_traceability | passed | 4.16 |
| test_download_daily_reports | test_nothing_missing_is_handled | passed | 0.00 |
| test_download_daily_reports | test_typo_dates_do_not_stop_the_crawl_and_are_reported | passed | 0.00 |
| test_harvest_nmpa | test_downloads_statements_to_incoming_and_notices_for_review | passed | 0.01 |
| test_harvest_nmpa | test_dry_run_lists_and_classifies_without_downloading | passed | 0.01 |
| test_harvest_nmpa | test_ministry_reports | passed | 0.00 |
| test_harvest_nmpa | test_month_read_from_inside_a_real_statement | passed | 0.37 |
| test_harvest_nmpa | test_only_statements_newer_than_data_held_and_no_other_documents | passed | 0.40 |
| test_harvest_nmpa | test_poppler_installer_pins_version_and_fingerprint | passed | 0.00 |
| test_harvest_nmpa | test_project_poppler_is_found_without_system_changes | passed | 0.00 |
| test_incentive_decision_aids | test_board_note_and_trade_notice | passed | 0.02 |
| test_incentive_decision_aids | test_expiring_schemes_days_and_order | passed | 1.39 |
| test_incentive_decision_aids | test_growth_check_arithmetic | passed | 0.01 |
| test_incentive_engine | test_2025_26_rates_are_in_the_pdf | passed | 0.09 |
| test_incentive_engine | test_accounts_check_implied_rates | passed | 0.01 |
| test_incentive_engine | test_actual_income_table_adds_up | passed | 0.00 |
| test_incentive_engine | test_baseline_methods_and_missing_months | passed | 0.00 |
| test_incentive_engine | test_baseline_versions_freeze_and_review_gate | passed | 0.06 |
| test_incentive_engine | test_both_tariff_versions_held_and_identical_lines | passed | 0.00 |
| test_incentive_engine | test_break_even_formula | passed | 0.00 |
| test_incentive_engine | test_budget_lines_add_up_to_nmpa_totals_where_complete | passed | 0.00 |
| test_incentive_engine | test_container_royalty_is_teu_times_rate | passed | 0.01 |
| test_incentive_engine | test_crude_is_priced_by_where_it_is_discharged | passed | 0.00 |
| test_incentive_engine | test_customer_figures_use_only_months_fully_covered_by_daily_reports | passed | 0.01 |
| test_incentive_engine | test_customer_stage_validation | passed | 0.00 |
| test_incentive_engine | test_customer_wharfage_adds_up_and_excludes_own_arrangements | passed | 0.10 |
| test_incentive_engine | test_deal_desk_blocks_and_errors | passed | 0.10 |
| test_incentive_engine | test_deal_desk_proposal_arithmetic_and_labels | passed | 0.12 |
| test_incentive_engine | test_draft_flagged_when_data_changes_and_amendment_needs_reapproval | passed | 0.05 |
| test_incentive_engine | test_end_to_end_workflow_as_nmpa_would_use_it | passed | 0.28 |
| test_incentive_engine | test_endpoints_ok_no_nan[/incentive/evidence] | passed | 0.00 |
| test_incentive_engine | test_endpoints_ok_no_nan[/incentive/opportunities] | passed | 0.00 |
| test_incentive_engine | test_endpoints_ok_no_nan[/incentive/revenue] | passed | 0.00 |
| test_incentive_engine | test_every_rate_used_appears_on_one_line_of_the_scale_of_rates | passed | 0.00 |
| test_incentive_engine | test_evidence_states_its_limits | passed | 0.01 |
| test_incentive_engine | test_key_customers | passed | 0.00 |
| test_incentive_engine | test_kpi_tariff_check_survives_unreadable_pdftotext_output | passed | 7.89 |
| test_incentive_engine | test_large_customer_drop_counts_as_falling | passed | 0.00 |
| test_incentive_engine | test_marginal_slabs_and_cap | passed | 0.00 |
| test_incentive_engine | test_market_context_excludes_nmpa_and_missing_months | passed | 0.01 |
| test_incentive_engine | test_module_kpis | passed | 0.25 |
| test_incentive_engine | test_new_endpoints_ok_no_nan[/incentive/cochin-schemes] | passed | 0.00 |
| test_incentive_engine | test_new_endpoints_ok_no_nan[/incentive/published-accounts] | passed | 0.00 |
| test_incentive_engine | test_new_endpoints_ok_no_nan[/incentive/rules] | passed | 0.00 |
| test_incentive_engine | test_new_endpoints_ok_no_nan[/incentive/tariff-comparison] | passed | 0.01 |
| test_incentive_engine | test_nmpa_notices_and_iron_ore_monitor | passed | 0.01 |
| test_incentive_engine | test_nmpa_scheme_records_are_backed_by_notice_files | passed | 0.00 |
| test_incentive_engine | test_opportunities_are_reviews_not_discounts | passed | 0.00 |
| test_incentive_engine | test_original_policy_documents_are_held | passed | 0.00 |
| test_incentive_engine | test_other_ports_schemes_are_sourced_and_nmpa_use_comes_from_its_notices | passed | 0.01 |
| test_incentive_engine | test_ppp_berths_are_not_priced_as_wharfage | passed | 0.00 |
| test_incentive_engine | test_previous_financial_year_baseline_matches_nmpa_notice | passed | 0.00 |
| test_incentive_engine | test_rates_match_the_scale_of_rates_pdf[crude_spm-Crude oil through Single Point Mooring\\s+M\\.T\\.\\s+34\\.89\\s+34\\.90] | passed | 0.23 |
| test_incentive_engine | test_rates_match_the_scale_of_rates_pdf[fertilizer-MOP, SOP, Urea ,DAP, NPK, CAN,\\s+M\\.T\\s+26\\.65\\s+45\\.71] | passed | 0.00 |
| test_incentive_engine | test_rates_match_the_scale_of_rates_pdf[food_grains-Rice,Wheat, Maize, Pulses\\s+M\\.T\\.\\s+30\\.47\\s+52\\.04] | passed | 0.00 |
| test_incentive_engine | test_rates_match_the_scale_of_rates_pdf[iron_ore_fines_lumps-Iron Ore Fines/Lumps\\s+M\\.T\\.\\s+43\\.16\\s+43\\.16] | passed | 0.00 |
| test_incentive_engine | test_rates_match_the_scale_of_rates_pdf[lpg_lng_gas-LPG/LNG or any gas in any other form\\s+M\\.T\\.\\s+147\\.61\\s+245\\.57] | passed | 0.00 |
| test_incentive_engine | test_rates_match_the_scale_of_rates_pdf[pol_products-\\(d\\) Crude Oil\\s+M\\.T\\.\\s+96\\.60\\s+96\\.60] | passed | 0.00 |
| test_incentive_engine | test_rates_match_the_scale_of_rates_pdf[rock_phosphate_sulphate-Sulphate/ Rock phosphate\\s+M\\.T\\s+30\\.47\\s+52\\.04] | passed | 0.00 |
| test_incentive_engine | test_rates_match_the_scale_of_rates_pdf[thermal_coal-Thermal Coal \\(other than UPCL\\)\\s+M\\.T\\.\\s+31\\.73\\s+31\\.73] | passed | 0.00 |
| test_incentive_engine | test_rebate_only_touches_extra_volume | passed | 0.01 |
| test_incentive_engine | test_revenue_is_tonnes_times_rate | passed | 0.00 |
| test_incentive_engine | test_scenario_arithmetic_blanket_and_rebate | passed | 0.01 |
| test_incentive_engine | test_scenario_baseline_is_actual_last_12_months_and_rows_are_sourced | passed | 0.01 |
| test_incentive_engine | test_scenario_with_costs_is_contribution | passed | 0.01 |
| test_incentive_engine | test_scheme_workflow_and_audit | passed | 0.20 |
| test_incentive_engine | test_seasonal_windows | passed | 0.23 |
| test_incentive_engine | test_sor_allows_lower_rates_and_rebates | passed | 0.00 |
| test_incentive_engine | test_sor_reference_points_to_the_right_lines | passed | 0.00 |
| test_incentive_engine | test_source_register_lists_every_original | passed | 0.00 |
| test_incentive_engine | test_start_here_actions_and_brief | passed | 0.03 |
| test_incentive_engine | test_tariff_comparison_values_are_in_both_pdfs | passed | 0.00 |
| test_incentive_engine | test_tariff_version_and_identity_block_a_proposal | passed | 0.01 |
| test_incentive_engine | test_update_rolls_back_on_failure_and_rerun_changes_nothing | passed | 9.71 |
| test_incentive_engine | test_update_without_poppler_daily_only_works_and_statements_explain | passed | 1.93 |
| test_incentive_engine | test_voc_comparison_same_year_and_located | passed | 0.00 |
| test_incentive_engine | test_waiver_coverage_from_daily_reports | passed | 0.01 |
| test_incentive_engine | test_waiver_uses_the_circulars_dates | passed | 0.00 |
| test_incentive_engine | test_win_back_gap_is_split_between_linked_cargos | passed | 0.01 |
| test_incentive_engine | test_zero_discount_gives_original_receipts | passed | 0.01 |
| test_incentive_improvements | test_board_ceiling_allows_or_blocks_stacking | passed | 0.00 |
| test_incentive_improvements | test_default_policy_keeps_the_old_rule | passed | 0.00 |
| test_incentive_improvements | test_easy_baseline_is_flagged | passed | 0.00 |
| test_incentive_improvements | test_evaluate_on_real_data_has_a_plain_answer | passed | 0.15 |
| test_incentive_improvements | test_every_ship_charge_rate_is_in_the_scale_of_rates_pdf | passed | 0.01 |
| test_incentive_improvements | test_fx_parse_and_official_rates_win | passed | 0.00 |
| test_incentive_improvements | test_integrity_check_runs_for_a_real_customer | passed | 0.04 |
| test_incentive_improvements | test_new_routes_answer | passed | 0.17 |
| test_incentive_improvements | test_one_call_by_hand | passed | 0.00 |
| test_incentive_improvements | test_peer_arithmetic_uses_other_ports_not_all_ports | passed | 0.00 |
| test_incentive_improvements | test_pilotage_slabs_join_up_and_respect_the_minimum | passed | 0.00 |
| test_incentive_improvements | test_portfolio_runs | passed | 0.00 |
| test_incentive_improvements | test_rebates_say_so_when_ship_sizes_are_missing | passed | 0.01 |
| test_incentive_improvements | test_related_companies_come_from_the_evidence_file | passed | 0.00 |
| test_incentive_improvements | test_retention_break_even_equals_the_discount_share | passed | 0.00 |
| test_incentive_improvements | test_settlement_in_progress_shows_on_track | passed | 0.00 |
| test_incentive_improvements | test_settlement_proportional_and_all_or_nothing | passed | 0.00 |
| test_incentive_improvements | test_timing_shift_is_flagged | passed | 0.00 |
| test_incentive_improvements | test_wikidata_parse_and_name_match_skip_ambiguous | passed | 0.01 |
| test_incentive_scheme_review | test_readiness_condition_is_consistent | passed | 1.07 |
| test_incentive_scheme_review | test_review_uses_the_right_check_and_never_guesses | passed | 0.00 |
| test_incentive_scheme_review | test_simple_check_arithmetic | passed | 0.00 |
| test_incentive_scheme_review | test_simple_check_other_ports_are_all_ports_minus_new_mangalore | passed | 0.00 |
| test_ministry_monthly | test_benchmark_trend_in_api | passed | 0.05 |
| test_ministry_monthly | test_derived_months_equal_nmpa_own_reports | passed | 0.01 |
| test_ministry_monthly | test_months_are_continuous_and_complete | passed | 0.00 |
| test_ministry_monthly | test_non_major_table_adds_up_to_printed_totals | passed | 0.00 |
| test_ministry_monthly | test_parser_runs_and_checks_every_report | passed | 1.10 |
| test_ministry_monthly | test_ports_add_up_to_all_port_total_every_month | passed | 0.01 |
| test_trade_customers | test_alerts_follow_their_rules | passed | 0.00 |
| test_trade_customers | test_canonical_customer[-Not stated] | passed | 0.00 |
| test_trade_customers | test_canonical_customer[199(I)+150(E )-Not stated] | passed | 0.00 |
| test_trade_customers | test_canonical_customer[90(P) + 75(CREW)-Not stated] | passed | 0.00 |
| test_trade_customers | test_canonical_customer[AEGIS C/O SEALORD-AEGIS] | passed | 0.00 |
| test_trade_customers | test_canonical_customer[EPSILON-EPSILON CARBON] | passed | 0.00 |
| test_trade_customers | test_canonical_customer[HP/IOC/BPC-BPCL + HPCL + IOCL] | passed | 0.00 |
| test_trade_customers | test_canonical_customer[HPCL/IOCL/BPCL-BPCL + HPCL + IOCL] | passed | 0.00 |
| test_trade_customers | test_canonical_customer[IOC/BPC/HP-BPCL + HPCL + IOCL] | passed | 0.00 |
| test_trade_customers | test_canonical_customer[IOCL-IOCL] | passed | 0.00 |
| test_trade_customers | test_canonical_customer[MRPL 40000-MRPL] | passed | 0.00 |
| test_trade_customers | test_canonical_customer[NFL A/C IPL-IPL] | passed | 0.00 |
| test_trade_customers | test_canonical_customer[RECEIVER/ SHIPPER-Not stated] | passed | 0.00 |
| test_trade_customers | test_canonical_customer[SANTHOSHIMAT HAA-SANTHOSHIMATHAA] | passed | 0.00 |
| test_trade_customers | test_canonical_customer[SOME NEW COMPANY-SOME NEW COMPANY] | passed | 0.00 |
| test_trade_customers | test_canonical_customer[UF 250(I)+250(E )-UF] | passed | 0.00 |
| test_trade_customers | test_canonical_customer[VARIOUS-Not stated] | passed | 0.00 |
| test_trade_customers | test_detail_months_add_up_to_summary | passed | 0.00 |
| test_trade_customers | test_endpoints_ok_no_nan_and_unknown_is_404 | passed | 1.00 |
| test_trade_customers | test_parcel_is_handled_plus_balance | passed | 0.01 |
| test_trade_customers | test_real_data_is_checked_against_official_statements | passed | 0.00 |
| test_trade_customers | test_real_data_shares_and_counts_are_consistent | passed | 0.00 |
| test_trade_customers | test_trend_and_quiet_rules | passed | 0.05 |
| test_trade_customers | test_trend_windows_use_complete_months_only | passed | 0.00 |
| test_trade_customers | test_two_ships_on_alternate_days_are_two_voyages_not_more | passed | 0.01 |
| test_trade_customers | test_vessel_name_notes_are_removed[SEA GULL 18-SEA GULL 18] | passed | 0.00 |
| test_trade_customers | test_vessel_name_notes_are_removed[SM NEW ORLEANS 12.0-A)-SM NEW ORLEANS] | passed | 0.00 |
| test_trade_customers | test_vessel_name_notes_are_removed[UNION GLORY (5.90) B.3/ 2/ 6/ 7-UNION GLORY] | passed | 0.00 |
| test_trade_customers | test_vessel_name_notes_are_removed[VISHVA PRERNA (12.50-A)-VISHVA PRERNA] | passed | 0.00 |
| test_trade_customers | test_vessel_name_notes_are_removed[VISHVA PRERNA (BACK LDG)-VISHVA PRERNA] | passed | 0.00 |
| test_trade_extras | test_alert_feedback_round_trip | passed | 0.01 |
| test_trade_extras | test_annual_port_commodity_adds_up_and_matches_monthly_total | passed | 0.01 |
| test_trade_extras | test_april_reports_store_full_financial_years | passed | 0.00 |
| test_trade_extras | test_brief_pdf_is_one_page | passed | 0.57 |
| test_trade_extras | test_cargo_mix_shares_add_up_each_year | passed | 0.01 |
| test_trade_extras | test_container_lines_endpoint | passed | 0.21 |
| test_trade_extras | test_customer_names_csv | passed | 0.01 |
| test_trade_extras | test_customer_notes_round_trip | passed | 0.01 |
| test_trade_extras | test_every_daily_report_has_a_status | passed | 0.01 |
| test_trade_extras | test_freshness_lists_every_source | passed | 0.00 |
| test_trade_extras | test_main_group_share_has_every_month | passed | 0.00 |
| test_trade_extras | test_market_share_shares_are_consistent | passed | 0.00 |
| test_trade_extras | test_ministry_commodity_table_adds_up | passed | 0.07 |
| test_trade_extras | test_only_date_named_files_are_daily_reports[01-09-2025 (1).pdf-daily] | passed | 0.00 |
| test_trade_extras | test_only_date_named_files_are_daily_reports[01-09-2025.pdf-daily] | passed | 0.00 |
| test_trade_extras | test_only_date_named_files_are_daily_reports[01-09-2025_0.pdf-daily] | passed | 0.00 |
| test_trade_extras | test_only_date_named_files_are_daily_reports[01.09.2025.pdf-daily] | passed | 0.00 |
| test_trade_extras | test_only_date_named_files_are_daily_reports[05-09-2025-Revision-in-Credit-Rating-JSW-Mangalore-Container-Terminal.pdf-unknown] | passed | 0.00 |
| test_trade_extras | test_port_competition_endpoint | passed | 0.04 |
| test_trade_extras | test_seasonality_iron_ore_peaks_in_winter | passed | 0.03 |
| test_trade_extras | test_target_by_cargo_adds_up | passed | 0.00 |
| test_trade_extras | test_unconfirmed_identities_are_not_merged | passed | 0.00 |
| test_trade_extras | test_update_script_recognises_files[27-10-2026.pdf-daily] | passed | 0.00 |
| test_trade_extras | test_update_script_recognises_files[Cargo handled at Major Ports October 2026.pdf-ministry] | passed | 0.00 |
| test_trade_extras | test_update_script_recognises_files[Commodity wise traffic statement October 2026.pdf-commodity] | passed | 0.00 |
| test_trade_extras | test_update_script_recognises_files[container traffic for the month of October 2026.pdf-container] | passed | 0.00 |
| test_trade_extras | test_update_script_recognises_files[operational performance October 2026.pdf-performance] | passed | 0.00 |
| test_trade_extras | test_update_script_recognises_files[something.pdf-unknown] | passed | 0.00 |
| test_trade_extras | test_update_script_skips_a_file_already_held | passed | 0.28 |
| test_trade_forecast | test_backtest_never_uses_future_data | passed | 0.01 |
| test_trade_forecast | test_baseline_error_matches_independent_loop_on_real_inbound | passed | 0.02 |
| test_trade_forecast | test_challenger_used_only_when_it_wins_both_halves_by_margin | passed | 0.00 |
| test_trade_forecast | test_endpoint_horizon_limits | passed | 0.22 |
| test_trade_forecast | test_endpoint_ok_json_and_no_nan | passed | 0.52 |
| test_trade_forecast | test_forecast_months_come_after_latest_data | passed | 0.52 |
| test_trade_forecast | test_irregular_and_tiny_cargos_are_not_forecast | passed | 0.04 |
| test_trade_forecast | test_mean12_is_average_of_last_12_months_with_data | passed | 0.00 |
| test_trade_forecast | test_mean12_skips_missing_months_not_zero | passed | 0.00 |
| test_trade_forecast | test_not_forecastable_shows_no_number_and_high_error | passed | 0.00 |
| test_trade_forecast | test_range_contains_forecast_and_is_not_negative | passed | 0.00 |
| test_trade_forecast | test_seasonal_blend_is_average_of_mean12_and_same_month_last_year | passed | 0.00 |
| test_trade_forecast | test_seasonal_blend_is_nan_without_last_year_value | passed | 0.00 |
| test_trade_forecast | test_wape_matches_hand_calculation | passed | 0.00 |
| test_trade_intelligence | test_alerts_follow_their_rules | passed | 0.04 |
| test_trade_intelligence | test_august_2026_matches_official_nmpa_statement | passed | 0.00 |
| test_trade_intelligence | test_bad_params_422[/trade/commodities?direction=x] | passed | 0.00 |
| test_trade_intelligence | test_bad_params_422[/trade/flows?months=1] | passed | 0.00 |
| test_trade_intelligence | test_bad_params_422[/trade/flows?months=999] | passed | 0.00 |
| test_trade_intelligence | test_brief_has_findings_sources_and_real_numbers | passed | 0.05 |
| test_trade_intelligence | test_build_flow_table_rebuilds_prior_year_without_overriding_real_rows | passed | 0.06 |
| test_trade_intelligence | test_canon_merges_spelling_variants | passed | 0.00 |
| test_trade_intelligence | test_csv_matches_official_statement_transcripts[April-April_2026] | passed | 0.02 |
| test_trade_intelligence | test_csv_matches_official_statement_transcripts[March-March_2026] | passed | 0.02 |
| test_trade_intelligence | test_csv_matches_official_statement_transcripts[May-May_2026] | passed | 0.02 |
| test_trade_intelligence | test_forecast_trade_uses_service_output | passed | 0.00 |
| test_trade_intelligence | test_jan_and_feb_2023_outbound_match_official_nmpa_statements | passed | 0.00 |
| test_trade_intelligence | test_known_official_overseas_coastal_figures | passed | 0.00 |
| test_trade_intelligence | test_latest_month_totals_match_raw_csv | passed | 0.01 |
| test_trade_intelligence | test_ministry_totals_agree_with_nmpa_statements | passed | 0.00 |
| test_trade_intelligence | test_missing_months_are_missing_not_zero | passed | 0.00 |
| test_trade_intelligence | test_momentum_signals | passed | 0.00 |
| test_trade_intelligence | test_overseas_plus_coastal_equals_total_every_month | passed | 0.00 |
| test_trade_intelligence | test_prior_year_crosscheck_leaves_only_known_differences | passed | 0.02 |
| test_trade_intelligence | test_real_endpoints_ok_and_valid_json[/trade/alerts] | passed | 0.00 |
| test_trade_intelligence | test_real_endpoints_ok_and_valid_json[/trade/commodities?direction=inbound] | passed | 0.05 |
| test_trade_intelligence | test_real_endpoints_ok_and_valid_json[/trade/commodities] | passed | 0.05 |
| test_trade_intelligence | test_real_endpoints_ok_and_valid_json[/trade/commodity?name=IRON%20ORE] | passed | 0.05 |
| test_trade_intelligence | test_real_endpoints_ok_and_valid_json[/trade/flows?months=60] | passed | 0.01 |
| test_trade_intelligence | test_real_endpoints_ok_and_valid_json[/trade/overseas-coastal] | passed | 0.00 |
| test_trade_intelligence | test_real_endpoints_ok_and_valid_json[/trade/summary] | passed | 0.00 |
| test_trade_intelligence | test_rebuilt_december_2022_matches_official_statement | passed | 0.07 |
| test_trade_intelligence | test_simulated_endpoints_are_gone[/trade/commodity-prices] | passed | 0.00 |
| test_trade_intelligence | test_simulated_endpoints_are_gone[/trade/lanes] | passed | 0.00 |
| test_trade_intelligence | test_simulated_endpoints_are_gone[/trade/opportunities] | passed | 0.00 |
| test_trade_intelligence | test_unknown_commodity_404 | passed | 0.00 |
| test_trade_intelligence | test_verification_script_passes_against_official_pdf | passed | 0.44 |
| test_trade_intelligence | test_window_compare_matches_by_calendar_date_not_position | passed | 0.00 |
| test_trade_intelligence | test_yoy_matches_independent_calculation | passed | 0.01 |
| test_trade_lookahead | test_berth_outlook_queues_two_ships_for_one_berth | passed | 0.02 |
| test_trade_lookahead | test_berths[10/11/SPM-expected1] | passed | 0.00 |
| test_trade_lookahead | test_berths[12 / 13-expected0] | passed | 0.00 |
| test_trade_lookahead | test_berths[12(P)/9-expected4] | passed | 0.00 |
| test_trade_lookahead | test_berths[13/12/9-expected3] | passed | 0.00 |
| test_trade_lookahead | test_berths[14W-expected2] | passed | 0.00 |
| test_trade_lookahead | test_day[02/01-2026-12-30-2027-01-02] | passed | 0.00 |
| test_trade_lookahead | test_day[19/05/24-2026-09-16-2024-05-19] | passed | 0.00 |
| test_trade_lookahead | test_day[27/10-2026-10-26-2026-10-27] | passed | 0.00 |
| test_trade_lookahead | test_day[28/12-2027-01-02-2026-12-28] | passed | 0.00 |
| test_trade_lookahead | test_day[COMPLETED-2026-10-26-None] | passed | 0.00 |
| test_trade_lookahead | test_endpoint_on_real_latest_report | passed | 0.66 |
| test_trade_performance_containers | test_august_2026_report_values_as_printed | passed | 0.02 |
| test_trade_performance_containers | test_container_commodities_add_up_to_printed_totals | passed | 0.00 |
| test_trade_performance_containers | test_endpoints_ok_no_nan[/trade/containers] | passed | 0.01 |
| test_trade_performance_containers | test_endpoints_ok_no_nan[/trade/performance] | passed | 0.00 |
| test_trade_performance_containers | test_liquid_waiting_shares_are_consistent | passed | 0.68 |
| test_trade_performance_containers | test_report_traffic_equals_ministry_total | passed | 0.01 |
| test_trade_performance_containers | test_targets_read_from_nmpa_reports | passed | 0.01 |
| test_trade_split | test_blank_or_mixed_run_flag_is_left_out_of_the_split | passed | 0.01 |
| test_trade_split | test_classify_cargo[BOXES-Containers-both] | passed | 0.00 |
| test_trade_split | test_classify_cargo[COAL TAR PITCH (L)-Coal tar pitch-outbound] | passed | 0.00 |
| test_trade_split | test_classify_cargo[CRUDE(D)-Crude oil-inbound] | passed | 0.00 |
| test_trade_split | test_classify_cargo[IOF(D)-Iron ore-inbound] | passed | 0.00 |
| test_trade_split | test_classify_cargo[IOF(L)-Iron ore-outbound] | passed | 0.00 |
| test_trade_split | test_classify_cargo[LPG (D)-LPG-inbound] | passed | 0.00 |
| test_trade_split | test_classify_cargo[MS(L)-Petroleum products (fuels)-outbound] | passed | 0.00 |
| test_trade_split | test_classify_cargo[S.COAL(D)-Coal-inbound] | passed | 0.00 |
| test_trade_split | test_classify_cargo[SOMETHING NEW-Other cargo-unknown] | passed | 0.00 |
| test_trade_split | test_counts_add_up_and_shares_are_valid | passed | 0.53 |
| test_trade_split | test_endpoint_ok_and_no_nan | passed | 0.59 |
| test_trade_split | test_estimate_is_labelled_and_limits_are_stated | passed | 0.00 |
| test_trade_split | test_joint_receivers_are_split | passed | 0.00 |
| test_trade_split | test_non_cargo_rows_and_placeholders_are_dropped | passed | 0.01 |
| test_trade_split | test_same_ship_on_consecutive_days_is_one_voyage_and_a_long_gap_makes_two | passed | 0.01 |
| test_trade_split | test_validation_months_exist_in_the_ministry_file_and_miss_is_independent | passed | 0.00 |
| test_trade_target_benchmark | test_benchmark_ranks_and_headline | passed | 0.00 |
| test_trade_target_benchmark | test_endpoints_ok_no_nan[/trade/benchmark] | passed | 0.00 |
| test_trade_target_benchmark | test_endpoints_ok_no_nan[/trade/target] | passed | 0.00 |
| test_trade_target_benchmark | test_june_2026_statement_equals_the_value_we_had_derived | passed | 0.00 |
| test_trade_target_benchmark | test_ministry_august_equals_nmpa_traffic_and_performance_report | passed | 0.00 |
| test_trade_target_benchmark | test_ministry_file_matches_the_original_pdfs | passed | 0.68 |
| test_trade_target_benchmark | test_ministry_new_mangalore_rows_match_the_overseas_coastal_file | passed | 0.01 |
| test_trade_target_benchmark | test_ministry_table_is_transcribed_exactly[major_ports_ministry_2026-07.csv-printed0] | passed | 0.00 |
| test_trade_target_benchmark | test_ministry_table_is_transcribed_exactly[major_ports_ministry_2026-09.csv-printed1] | passed | 0.00 |
| test_trade_target_benchmark | test_target_arithmetic | passed | 0.00 |
| test_trade_target_benchmark | test_target_done_equals_ministry_april_to_september | passed | 0.00 |
| test_trade_waiting | test_blank_wait_is_not_counted | passed | 0.01 |
| test_trade_waiting | test_buckets | passed | 0.00 |
| test_trade_waiting | test_longest_wait_kept_and_one_event | passed | 0.01 |
| test_trade_waiting | test_real_data_totals_and_endpoint | passed | 0.47 |
