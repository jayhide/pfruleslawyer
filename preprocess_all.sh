#!/bin/bash
# Preprocess all rules files:
# - Normal mode for base-level rules files
# - Simple mode for subdirectory content (skills, class, feats, spells)

set -e

echo "=== Processing base-level rules files (normal mode) ==="
poetry run python preprocess_sections.py -v "$@"

# Process each subdirectory in simple mode
for subdir in skills class feats spells; do
    if [ -d "rules/$subdir" ]; then
        echo ""
        echo "=== Processing rules/$subdir (simple mode) ==="
        mkdir -p "manifests/$subdir"
        poetry run python preprocess_sections.py \
            --rules-dir "rules/$subdir" \
            --output-dir "manifests/$subdir" \
            --simple \
            -v \
            "$@"
    fi
done

echo ""
echo "=== Done ==="
