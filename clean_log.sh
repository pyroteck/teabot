#!/bin/bash
# Simple bash script to clean up log file generated with tee command in docker-compose

# Hardcoded file path
input_file="./data/bot_output.log"

# Check if input file exists
if [ ! -f "$input_file" ]; then
    echo "Error: File $input_file not found"
    exit 1
fi

# Create cleaned_logs directory if it doesn't exist
mkdir -p "./bot_logs"

# Generate output filename with date and time in MM-DD-YYYY_HH-MM-SS format
output_file="./bot_logs/$(date +%m-%d-%Y_%H-%M-%S)_output-cleaned.log"

# Process the file and create new output file
sed '/rate limited\|^[[:space:]]*$/d' "$input_file" > "$output_file"

echo "Processed $input_file -> $output_file"
