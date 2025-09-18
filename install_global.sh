#!/bin/bash
# DevHub Global Installation Script
# Professional installation as a global tool

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color
BOLD='\033[1m'

# Print colored output
print_header() {
    echo -e "\n${BLUE}${BOLD}=== $1 ===${NC}\n"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

# Detect OS
detect_os() {
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        OS="linux"
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        OS="macos"
    elif [[ "$OSTYPE" == "msys" ]] || [[ "$OSTYPE" == "cygwin" ]]; then
        OS="windows"
    else
        OS="unknown"
    fi
}

print_header "DevHub Professional Installer"
echo "This will install DevHub globally as a command-line tool"
echo "Installation location: ~/.local/bin/ (or system Python)"
echo ""

# Check Python version
print_header "Checking Requirements"

if ! command -v python3 &> /dev/null; then
    print_error "Python 3 is not installed"
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
print_success "Python $PYTHON_VERSION found"

# Check for uv or pipx
print_header "Selecting Installation Method"

INSTALL_METHOD=""

# Check for uv
if command -v uv &> /dev/null; then
    print_success "Found uv (fast installation!)"
    INSTALL_METHOD="uv"
elif command -v pipx &> /dev/null; then
    print_success "Found pipx (isolated environment)"
    INSTALL_METHOD="pipx"
else
    print_info "Neither uv nor pipx found"
    echo ""
    echo "Choose installation method:"
    echo "1) Install uv (recommended - very fast)"
    echo "2) Install pipx (standard Python tool)"
    echo "3) Use pip --user (simple but less isolated)"
    echo ""
    read -p "Your choice (1/2/3): " choice

    case $choice in
        1)
            print_info "Installing uv..."
            curl -LsSf https://astral.sh/uv/install.sh | sh
            export PATH="$HOME/.cargo/bin:$PATH"
            INSTALL_METHOD="uv"
            print_success "uv installed successfully"
            ;;
        2)
            print_info "Installing pipx..."
            python3 -m pip install --user pipx
            python3 -m pipx ensurepath
            export PATH="$HOME/.local/bin:$PATH"
            INSTALL_METHOD="pipx"
            print_success "pipx installed successfully"
            ;;
        3)
            INSTALL_METHOD="pip"
            ;;
        *)
            print_error "Invalid choice"
            exit 1
            ;;
    esac
fi

# Get DevHub path
DEVHUB_PATH=$(cd "$(dirname "$0")" && pwd)
print_info "Installing DevHub from: $DEVHUB_PATH"

# Install DevHub
print_header "Installing DevHub"

case $INSTALL_METHOD in
    uv)
        print_info "Installing with uv tool..."
        uv tool install --from "$DEVHUB_PATH" devhub
        print_success "DevHub installed with uv"
        ;;
    pipx)
        print_info "Installing with pipx..."
        pipx install "$DEVHUB_PATH"
        print_success "DevHub installed with pipx"
        ;;
    pip)
        print_info "Installing with pip --user..."
        python3 -m pip install --user "$DEVHUB_PATH"
        print_success "DevHub installed with pip"

        # Check if ~/.local/bin is in PATH
        if [[ ":$PATH:" != *":$HOME/.local/bin:"* ]]; then
            print_warning "~/.local/bin is not in your PATH"
            echo "Add this to your shell config (.bashrc, .zshrc, etc.):"
            echo "export PATH=\"\$HOME/.local/bin:\$PATH\""
        fi
        ;;
esac

# Verify installation
print_header "Verifying Installation"

if command -v devhub &> /dev/null; then
    print_success "DevHub command is available"
    DEVHUB_VERSION=$(devhub --version 2>/dev/null || echo "version check failed")
    print_info "Version: $DEVHUB_VERSION"
else
    print_warning "DevHub command not found in PATH"
    print_info "You may need to restart your terminal or add to PATH"
fi

# Setup instructions
print_header "Next Steps"

echo "1. Initialize DevHub (one time only):"
echo "   ${BOLD}devhub init${NC}"
echo ""
echo "2. Set up authentication:"
echo "   ${BOLD}devhub auth setup${NC}"
echo ""
echo "3. Use in any project:"
echo "   ${BOLD}cd /your/project${NC}"
echo "   ${BOLD}devhub status${NC}          # Check detection"
echo "   ${BOLD}devhub claude context${NC}  # Generate Claude context"
echo ""
print_success "Installation complete!"
echo ""
echo "📚 Full documentation: devhub --help"
echo "🚀 Ready to enhance your Claude Code experience!"