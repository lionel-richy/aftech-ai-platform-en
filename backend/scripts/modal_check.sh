#!/bin/bash
# Checks that the Modal CLI is installed and authenticated, without deploying anything.
set -e

echo "== Active Modal profile =="
modal profile current

echo ""
echo "== Modal apps (running, deployed, recently stopped) =="
modal app list
