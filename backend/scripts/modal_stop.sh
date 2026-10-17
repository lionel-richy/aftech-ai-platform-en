#!/bin/bash
# Permanently stops the Modal app (also terminates any running containers).
set -e

echo "This will PERMANENTLY stop the 'aftech-ai-platform' app on Modal."
read -r -p "Confirm the shutdown? (type 'yes' to continue) " reponse

if [ "$reponse" == "yes" ]; then
    modal app stop aftech-ai-platform
else
    echo "Cancelled."
fi
