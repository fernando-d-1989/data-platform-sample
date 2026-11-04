#!/bin/bash
# The nightly order for one client. Each step only runs if the load worked.
LOG="reports/nightly_$(date +%F).log"
mkdir -p reports

python pipeline/load_crm.py >> "$LOG" 2>&1      # source -> bronze -> silver -> gold
CODE=$?
echo "load finished with code $CODE" >> "$LOG"

if [ "$CODE" -eq 0 ]; then
    python agent/baseline.py >> "$LOG" 2>&1 \
        || echo "ATTENTION: a known answer changed" >> "$LOG"
    python ml/train_lead_score.py >> "$LOG" 2>&1 \
        || echo "ATTENTION: no new scores, the dashboard keeps yesterday's list" >> "$LOG"
    # In production the AI-written analysis follows here. It is not in this sample.
fi
