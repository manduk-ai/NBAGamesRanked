#!/bin/bash

echo "Current time: $(date +%H:%M)"

# Load the environment variables
echo "Loading environment variables..."
source /home/ec2-user/.bash_profile

# Check if the source command succeeded
if [ $? -eq 0 ]; then
    echo "Environment variables loaded."
else
    echo "Failed to load environment variables."
    exit 1
fi

# Activate your Python virtual environment
echo "Activating virtual environment..."
source /home/ec2-user/nba_venv/bin/activate

# Check if the activate command succeeded
if [ $? -eq 0 ]; then
    echo "Virtual environment activated."
else
    echo "Failed to activate virtual environment."
    exit 1
fi

# Run your Python script with an absolute path
echo "Running the Python script..."
/home/ec2-user/nba_venv/bin/python /home/ec2-user/post-tweet.py

# Check if the python command succeeded
if [ $? -eq 0 ]; then
    echo "Python script ran successfully."
else
    echo "Python script failed to run."
    exit 1
fi

# Deactivate the virtual environment
echo "Deactivating virtual environment..."
deactivate

# Final message
echo "Script execution completed."
