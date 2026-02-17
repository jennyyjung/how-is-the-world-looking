# Cluster Service Interface (V1)

## Service interface
`ClusterService.build_clusters(...)`

Inputs:
- `db: Session`
- `lookback_hours: int = 72`
- `similarity_threshold: float = 0.35`

Behavior:
- Loads recent claims (by article creation time lookback window).
- Computes token overlap similarity (Jaccard) between claim text and active cluster titles.
- Assigns claim to best matching cluster when score >= threshold.
- Creates new cluster when no active match meets threshold.
- Persists `event_cluster_id` on claim rows.

Returns:
- `clusters_created`
- `claims_clustered`
- `claims_scanned`

## API schema
`POST /clusters/build`

Request:
```json
{
  "lookback_hours": 72,
  "similarity_threshold": 0.35
}
```

Response:
```json
{
  "clusters_created": 6,
  "claims_clustered": 38,
  "claims_scanned": 44
}
```

## Notes
- This is a deterministic baseline clusterer intended for rapid MVP iteration.
- Later upgrades can replace lexical matching with embeddings while preserving endpoint contracts.
