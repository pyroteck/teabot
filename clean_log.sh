#!/bin/bash
# Simple bash script to clean up log file generated with tee command in docker-compose

# Hardcoded file path
input_file="./data/bot_output.log"

# Check if input file exists
if [ ! -f "$input_file" ]; then
    echo "Error: File $input_file not found"
    exit 1
fi

# Process the file in-place using sed
sed -i '/rate limited\|^[[:space:]]*$/d' "$input_file"

echo "Processed $input_file"
