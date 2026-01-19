#!/bin/bash

# --- Script: utils_colors.sh ---
# Description: Defines color codes and logging functions for prettier terminal output.

# Define colors
BOLD="\033[1m"
RESET="\033[0m"
RED="\033[1;31m"
GREEN="\033[1;32m"
YELLOW="\033[1;33m"
BLUE="\033[1;34m"
CYAN="\033[1;36m"
WHITE="\033[1;37m"

# Header function
print_header() {
    echo -e "\n${BLUE}${BOLD}============================================================${RESET}"
    echo -e "${BLUE}${BOLD}   $1${RESET}"
    echo -e "${BLUE}${BOLD}============================================================${RESET}\n"
}

# Sub-header function
print_subheader() {
    echo -e "\n${CYAN}${BOLD}--- $1 ---${RESET}"
}

# Info message
log_info() {
    echo -e "${WHITE}[INFO]${RESET} $1"
}

# Success message
log_success() {
    echo -e "${GREEN}[SUCCESS]${RESET} $1"
}

# Warning message
log_warn() {
    echo -e "${YELLOW}[WARN]${RESET} $1"
}

# Error message
log_error() {
    echo -e "${RED}[ERROR]${RESET} $1"
}
