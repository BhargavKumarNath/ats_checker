# Skill taxonomy

The living IP of this project (`docs/gap_analysis_spec.md`). One YAML file per category; `categories.yaml` holds the per-category default role-track weights from `gap_analysis_spec.md` §3.

Each cluster:

```yaml
- cluster_id: peft                # stable, snake_case, never renamed once shipped
  canonical_name: Fine-tuning / PEFT
  surface_forms: [LoRA, QLoRA, ...] # every phrasing that should match this cluster; case-insensitive,
                                    # hyphen/space/"&"-tolerant, matched on word boundaries
  role_track_weight:               # optional per-cluster override of the category default
    data_engineer: 0.5
```

Rules: a surface form may appear in more than one cluster when the spec cross-references it (Airflow). Prefer adding a surface form over relying on the embedding fallback once the fallback is seen catching the same phrasing repeatedly (`gap_analysis_spec.md` §4).
