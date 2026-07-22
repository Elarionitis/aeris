# Evaluation report

**Status:** reproducible MVP validation on the repository's synthetic holdout
(8 wards × 240 hourly observations). This is not a claim of real-world accuracy;
live, labelled Bengaluru data is the next validation gate.

## Forecast accuracy vs persistence baseline

Time-based holdout results (lower RMSE is better):

| Horizon | Baseline RMSE | Model RMSE | Improvement |
|---|---:|---:|---:|
| 1 h | 21.91 | 0.38 | 98.3% |
| 3 h | 22.45 | 0.39 | 98.2% |
| 6 h | 23.30 | 0.51 | 97.8% |
| 12 h | 23.32 | 0.40 | 98.3% |
| 24 h | 22.26 | 0.27 | 98.8% |

```text
RMSE (baseline █, model ▌)
 1h   ██████████████████████ 21.91   ▌ 0.38
 3h   ██████████████████████ 22.45   ▌ 0.39
 6h   ███████████████████████ 23.30  ▌ 0.51
12h   ███████████████████████ 23.32  ▌ 0.40
24h   ██████████████████████ 22.26   ▌ 0.27
```

The model meets the automated quality gate: mean RMSE is at least 10% lower
than persistence. The unusually large lift reflects the controlled synthetic
fixture, so the judging claim should be “validated pipeline performance,” not
production accuracy.

## Attribution confidence distribution

Confidence is the non-negative regression R², calculated separately for the
eight synthetic wards. All 8/8 wards fall in **0.00–0.20** (each: **0.03**);
none are shown as high-confidence evidence. This is expected because the smoke
fixture was made to test pipeline flow, not to encode a causal source/AQI
relationship. In the controlled attribution unit test with known linear source
signals, confidence passes the ≥0.80 quality gate.

**Judge-ready takeaway:** the UI exposes confidence and the system can withhold
strong causal language; source attribution must be recalibrated on live sensor,
traffic, permit, and satellite-fire data before enforcement use.

## Example enforcement recommendations

| Priority | Recommendation | Supporting evidence |
|---|---|---|
| 1 | Inspect BTM industrial sources first. | AQI 168 (Poor) for 4 days; 49% industrial + construction estimate; 3 registered sources within 1 km (nearest 0.303 km); priority score 147. |
| 2 | Inspect Mahadevapura utilities stack and flyover work zone. | AQI 154 (Poor) for 5 days; 47% industrial + construction estimate; 2 sources within 1 km (0.773/0.872 km); score 94. |
| 3 | Inspect HSR redevelopment activity. | AQI 142 (Poor) for 3 days; construction is dominant; 2 sources within 1 km (0.450/0.765 km); score 90. |

The source registry and recommendations are mock MVP data. Each recommendation
requires field verification and live municipal records before any enforcement
action.

## Reproduce

```bash
cd backend
python3 -m pytest tests -q
```
