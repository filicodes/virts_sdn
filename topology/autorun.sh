#!/bin/bash

# Change this to your virtual environment path
VENV_PATH="/home/jhinx/ryu-venv"

# Controller and Topology files
RYU_APP="$VENV_PATH/virts_sdn/controller/virts_controller_v2.py"
TOPO_SCRIPT="$VENV_PATH/virts_sdn/topology/virts_network.py"

# Activate venv
source "$VENV_PATH/bin/activate"

# Open Ryu controller in a new terminal
gnome-terminal -- bash -c "cd $VENV_PATH && source bin/activate && cd $VENV_PATH/virts_sdn/topology && sudo mn -c && cd $VENV_PATH/virts_sdn/controller && ryu-manager $RYU_APP; exec bash"

# Small delay to let controller start
sleep 3

# Open Mininet-WiFi topology in another terminal
gnome-terminal -- bash -c "cd $VENV_PATH && source bin/activate && cd $VENV_PATH/virts_sdn/topology && sudo python3 $TOPO_SCRIPT; exec bash"
