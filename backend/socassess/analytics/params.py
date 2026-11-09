"""Detector parameters. Every value is stored with each analysis run (auditability).

Rate-based detectors flag an entity only when BOTH hold:
  * the rate passes an absolute floor (so a 0.1% -> 0.3% change never alarms), and
  * its robust z-score against same-source peers is >= z_min.
Robust z = (x - peer median) / max(1.4826 * MAD, min_scale).
"""

DEFAULT_PARAMS: dict = {
    "z_min": 3.0,
    "min_cases": 30,  # entities with fewer relevant cases are not judged on rates
    "fast_closure": {"max_minutes": {"critical": 15, "high": 10}, "min_rate": 0.05, "min_scale": 0.02},
    "critical_no_escalation": {"min_rate": 0.20, "min_scale": 0.05, "min_cases": 10},
    "template_notes": {"similarity": 0.92, "min_group": 5, "min_rate": 0.05, "min_scale": 0.02,
                       "min_chars": 15},
    "repeated_no_remediation": {"min_alerts": 12, "min_span_days": 7},
    "sla_gaming": {"final_window": 0.05, "prev_window": 0.10, "min_share": 0.08, "min_ratio": 3.0,
                   "min_scale": 0.02},
    "sla_breach": {"min_rate": 0.15, "min_scale": 0.03},
    "silent_assets": {"zero_day_share": 0.5, "low_fraction": 0.01, "recent_days": 30},
    "missing_categories": {"peer_presence": 0.75, "min_alerts_present": 3,
                           "high_impact": ["lateral_movement", "privilege_escalation",
                                           "data_exfiltration", "ics_anomaly", "malware"],
                           "sector_family": {"power": "ics", "transport": "ics", "water": "ics"}},
    "missing_records": {"min_uncased_rate": 0.01, "min_unrecorded_rate": 0.05, "min_items": 3},
    "low_activity": {"max_ratio": 0.35, "z_max": -3.0, "min_scale": 0.15},
    "anomaly": {"z_flag": 3.5, "min_entities": 8, "n_estimators": 300, "random_state": 0},
    "clustering": {"min_cluster_size": 5, "svd_dims": 8, "random_state": 0},
    "risk_weights": {
        "critical_no_escalation": 25, "silent_critical_assets": 20, "missing_records": 18,
        "fast_closure": 15, "sla_gaming": 14, "repeated_no_remediation": 12,
        "template_notes": 10, "missing_categories": 10, "low_activity": 10, "sla_breach": 8,
        "operational_anomaly": 5,
    },
    "severity_multiplier": {"low": 0.25, "medium": 0.5, "high": 0.75, "critical": 1.0},
    "review_samples_per_finding": 5,
    "spot_check_samples": 5,
}
