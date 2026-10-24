#!/bin/bash

# --- Script: utils_colors.sh ---
# Description: Standard color definitions and logging helper functions for fMRI analysis scripts.

# Define ANSI color escape codes
BOLD="\033[1m"
RESET="\033[0m"
RED="\033[1;31m"
GREEN="\033[1;32m"
YELLOW="\033[1;33m"
BLUE="\033[1;34m"
CYAN="\033[1;36m"
WHITE="\033[1;37m"

# Ensure AFNI binaries are in PATH if available
if [[ -n "${HOME:-}" ]] && [[ -d "${HOME}/abin" ]] && [[ ":${PATH:-}:" != *":${HOME}/abin:"* ]]; then
    export PATH="${HOME}/abin:${PATH:-}"
fi

# Major section header
print_header() {
    echo -e "\n${BLUE}${BOLD}============================================================${RESET}"
    echo -e "${BLUE}${BOLD}   ${1:-}${RESET}"
    echo -e "${BLUE}${BOLD}============================================================${RESET}\n"
}

# Sub-section header
print_subheader() {
    echo -e "\n${CYAN}${BOLD}--- ${1:-} ---${RESET}"
}

# Standard informational message
log_info() {
    echo -e "${WHITE}[INFO]${RESET} ${1:-}"
}

# Success confirmation message
log_success() {
    echo -e "${GREEN}[SUCCESS]${RESET} ${1:-}"
}

# Warning message
log_warn() {
    echo -e "${YELLOW}[WARN]${RESET} ${1:-}"
}

# Error message directed to stderr
log_error() {
    echo -e "${RED}[ERROR]${RESET} ${1:-}" >&2
}
