#!/bin/bash
# Runs when the VM boots. The VM keeps nothing of its own: it downloads the code,
# runs tonight's work and switches itself off.
cd /home/app/data-platform
git fetch origin main && git reset --hard origin/main   # the repo IS the deployment
source venv/bin/activate
pip install --quiet -r requirements.txt
bash ops/run_nightly.sh
sudo shutdown +10
