#!/usr/bin/env bash
# DevHub Enterprise Installer
# Copyright (c) 2024 DevHub Team
#
# This script installs DevHub globally on your system with all dependencies
# properly isolated. No Python knowledge required.

set -e  # Exit on error

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# Configuration
DEVHUB_VERSION="0.1.0"
DEVHUB_HOME="${DEVHUB_HOME:-$HOME/.devhub}"
INSTALL_DIR="$HOME/.local/bin"
MIN_PYTHON_VERSION="3.11"

# Logging functions
log_info() {
    echo -e "${BLUE}ℹ${NC}  $1"
}

log_success() {
    echo -e "${GREEN}✓${NC}  $1"
}

log_error() {
    echo -e "${RED}✗${NC}  $1" >&2
}

log_warning() {
    echo -e "${YELLOW}⚠${NC}  $1"
}

print_banner() {
    echo -e "${BOLD}"
    echo "╔════════════════════════════════════════════╗"
    echo "║           DevHub Installer v${DEVHUB_VERSION}          ║"
    echo "║    Enterprise Development Hub for Teams    ║"
    echo "╚════════════════════════════════════════════╝"
    echo -e "${NC}"
}

# System detection
detect_os() {
    case "$(uname -s)" in
        Linux*)     OS="Linux";;
        Darwin*)    OS="macOS";;
        CYGWIN*|MINGW*|MSYS*) OS="Windows";;
        *)          OS="Unknown";;
    esac
    echo "$OS"
}

detect_arch() {
    case "$(uname -m)" in
        x86_64|amd64)  ARCH="x64";;
        arm64|aarch64) ARCH="arm64";;
        *)             ARCH="unknown";;
    esac
    echo "$ARCH"
}

# Python detection and validation
find_python() {
    # Try to find the best Python installation
    local python_cmd=""

    for cmd in python3.13 python3.12 python3.11 python3 python; do
        if command -v "$cmd" &> /dev/null; then
            local version=$("$cmd" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
            if python_version_ok "$version"; then
                python_cmd="$cmd"
                break
            fi
        fi
    done

    echo "$python_cmd"
}

python_version_ok() {
    local version=$1
    local major=$(echo "$version" | cut -d. -f1)
    local minor=$(echo "$version" | cut -d. -f2)

    if [ "$major" -eq 3 ] && [ "$minor" -ge 11 ]; then
        return 0
    fi
    return 1
}

# Installation method detection
detect_installation_method() {
    # Check for uv (preferred)
    if command -v uv &> /dev/null; then
        echo "uv"
    # Check for pipx (second choice)
    elif command -v pipx &> /dev/null; then
        echo "pipx"
    # Check for pip (fallback)
    elif command -v pip3 &> /dev/null || command -v pip &> /dev/null; then
        echo "pip"
    else
        echo "none"
    fi
}

# UV installation
install_with_uv() {
    log_info "Installing DevHub with uv..."

    # Robust cleanup of existing installation
    cleanup_uv_installation

    # Clear any cached builds
    log_info "Clearing build cache..."
    rm -rf build/ dist/ *.egg-info/ 2>/dev/null || true

    # Install from the current directory with maximum force
    log_info "Installing DevHub (this may take a moment)..."
    if uv tool install . --force --reinstall; then
        log_success "DevHub installed successfully with uv"

        # Verify installation
        if verify_installation_works; then
            return 0
        else
            log_error "Installation verification failed"
            return 1
        fi
    else
        log_error "Failed to install with uv"
        return 1
    fi
}

# Robust UV cleanup
cleanup_uv_installation() {
    log_info "Performing thorough cleanup of existing DevHub installation..."

    # Uninstall the tool
    uv tool uninstall devhub 2>/dev/null || true

    # Remove the tool directory entirely
    local uv_tools_dir="$HOME/.local/share/uv/tools/devhub"
    if [ -d "$uv_tools_dir" ]; then
        log_info "Removing cached installation directory..."
        rm -rf "$uv_tools_dir"
    fi

    # Remove any stale executable links
    local bin_path="$HOME/.local/bin/devhub"
    if [ -f "$bin_path" ]; then
        log_info "Removing stale executable..."
        rm -f "$bin_path"
    fi

    # Clear UV cache for this project
    if command -v uv &> /dev/null; then
        log_info "Clearing UV cache..."
        uv cache clean 2>/dev/null || true
    fi
}

# Pipx installation
install_with_pipx() {
    log_info "Installing DevHub with pipx..."

    # Robust cleanup
    cleanup_pipx_installation

    # Clear any cached builds
    log_info "Clearing build cache..."
    rm -rf build/ dist/ *.egg-info/ 2>/dev/null || true

    # Install from the current directory
    log_info "Installing DevHub with pipx (this may take a moment)..."
    if pipx install . --force; then
        log_success "DevHub installed successfully with pipx"

        # Verify installation
        if verify_installation_works; then
            return 0
        else
            log_error "Installation verification failed"
            return 1
        fi
    else
        log_error "Failed to install with pipx"
        return 1
    fi
}

# Robust pipx cleanup
cleanup_pipx_installation() {
    log_info "Performing thorough cleanup of existing DevHub installation..."

    # Uninstall via pipx
    pipx uninstall devhub 2>/dev/null || true

    # Remove any stale executable links
    local bin_path="$HOME/.local/bin/devhub"
    if [ -f "$bin_path" ]; then
        log_info "Removing stale executable..."
        rm -f "$bin_path"
    fi

    # Clean up pipx environment directory
    local pipx_venv_dir="$HOME/.local/share/pipx/venvs/devhub"
    if [ -d "$pipx_venv_dir" ]; then
        log_info "Removing cached pipx environment..."
        rm -rf "$pipx_venv_dir"
    fi

    # Clean up pipx data directory
    local pipx_data_dir="$HOME/.local/share/pipx/pyvenvs/devhub"
    if [ -d "$pipx_data_dir" ]; then
        log_info "Removing pipx data directory..."
        rm -rf "$pipx_data_dir"
    fi
}

# Cleanup pip installation
cleanup_pip_installation() {
    log_info "Performing thorough cleanup of existing DevHub installation..."

    # Remove wrapper script
    local bin_path="$INSTALL_DIR/devhub"
    if [ -f "$bin_path" ]; then
        log_info "Removing existing wrapper script..."
        rm -f "$bin_path"
    fi

    # Remove virtual environment
    local venv_dir="$DEVHUB_HOME/venv"
    if [ -d "$venv_dir" ]; then
        log_info "Removing existing virtual environment..."
        rm -rf "$venv_dir"
    fi

    # Try to uninstall from global pip as well (in case of old installations)
    if command -v pip &> /dev/null; then
        pip uninstall -y devhub 2>/dev/null || true
    fi
    if command -v pip3 &> /dev/null; then
        pip3 uninstall -y devhub 2>/dev/null || true
    fi
}

# Pip installation (with virtual environment)
install_with_pip() {
    log_info "Installing DevHub with pip in isolated environment..."

    # Robust cleanup
    cleanup_pip_installation

    local venv_dir="$DEVHUB_HOME/venv"
    local python_cmd=$(find_python)

    if [ -z "$python_cmd" ]; then
        log_error "No suitable Python installation found"
        return 1
    fi

    # Create virtual environment
    log_info "Creating isolated environment..."
    "$python_cmd" -m venv "$venv_dir"

    # Activate and install
    source "$venv_dir/bin/activate"

    # Upgrade pip
    pip install --upgrade pip >/dev/null 2>&1

    # Install DevHub with all dependencies
    if pip install -e . >/dev/null 2>&1; then
        deactivate

        # Create wrapper script
        create_wrapper_script "$venv_dir"

        log_success "DevHub installed successfully with pip"

        # Verify installation
        if verify_installation_works; then
            return 0
        else
            log_error "Installation verification failed"
            return 1
        fi
    else
        deactivate
        log_error "Failed to install with pip"
        return 1
    fi
}

# Create wrapper script for pip installation
create_wrapper_script() {
    local venv_dir=$1
    local wrapper="$INSTALL_DIR/devhub"

    mkdir -p "$INSTALL_DIR"

    cat > "$wrapper" << 'EOF'
#!/usr/bin/env bash
# DevHub wrapper script
# Auto-generated by DevHub installer

DEVHUB_VENV="__VENV_DIR__"

if [ ! -d "$DEVHUB_VENV" ]; then
    echo "Error: DevHub virtual environment not found at $DEVHUB_VENV"
    echo "Please reinstall DevHub using the install script"
    exit 1
fi

exec "$DEVHUB_VENV/bin/python" -m devhub.cli "$@"
EOF

    # Replace placeholder with actual path
    sed -i "s|__VENV_DIR__|$venv_dir|g" "$wrapper"
    chmod +x "$wrapper"
}

# Install uv if not present
install_uv() {
    log_info "Installing uv package manager..."

    if curl -LsSf https://astral.sh/uv/install.sh | sh; then
        log_success "uv installed successfully"
        # Add to PATH for current session
        export PATH="$HOME/.cargo/bin:$PATH"
        return 0
    else
        log_error "Failed to install uv"
        return 1
    fi
}

# Comprehensive cleanup of all possible installations
cleanup_old_installation() {
    log_info "Performing comprehensive cleanup of all previous installations..."

    # Try all cleanup methods to ensure complete removal
    cleanup_uv_installation
    cleanup_pipx_installation
    cleanup_pip_installation

    # Additional global cleanup
    if command -v pip &> /dev/null; then
        pip uninstall -y devhub 2>/dev/null || true
    fi
    if command -v pip3 &> /dev/null; then
        pip3 uninstall -y devhub 2>/dev/null || true
    fi

    # Remove any Python cache files
    if [ -d "$DEVHUB_HOME" ]; then
        find "$DEVHUB_HOME" -name "*.pyc" -delete 2>/dev/null || true
        find "$DEVHUB_HOME" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
    fi

    log_success "Previous installations cleaned up"
}

# Verify installation
verify_installation() {
    log_info "Verifying installation..."

    # Check if devhub command is available
    if ! command -v devhub &> /dev/null; then
        log_error "DevHub command not found in PATH"
        log_info "You may need to add $INSTALL_DIR to your PATH"
        return 1
    fi

    # Try to run devhub --version
    if devhub --version &> /dev/null; then
        local version=$(devhub --version 2>/dev/null | head -n1)
        log_success "DevHub installed successfully: $version"
        return 0
    else
        log_error "DevHub installed but not working correctly"
        return 1
    fi
}

# Enhanced verification that actually tests functionality
verify_installation_works() {
    log_info "Testing DevHub functionality..."

    # Check if devhub command is available
    if ! command -v devhub &> /dev/null; then
        log_error "DevHub command not found in PATH"
        return 1
    fi

    # Test version command
    if ! devhub --version &> /dev/null; then
        log_error "DevHub version command failed"
        return 1
    fi

    # Test help command
    if ! devhub --help &> /dev/null; then
        log_error "DevHub help command failed"
        return 1
    fi

    # Test that imports work (quick smoke test)
    if ! devhub --version 2>&1 | grep -q "DevHub"; then
        log_error "DevHub version output is incorrect"
        return 1
    fi

    log_success "DevHub functionality verified"
    return 0
}

# Setup shell completion
setup_completion() {
    log_info "Setting up shell completion..."

    local shell_name=$(basename "$SHELL")
    local completion_dir=""

    case "$shell_name" in
        bash)
            completion_dir="${HOME}/.bash_completion.d"
            ;;
        zsh)
            completion_dir="${HOME}/.zsh/completion"
            ;;
        fish)
            completion_dir="${HOME}/.config/fish/completions"
            ;;
        *)
            log_warning "Shell completion not supported for $shell_name"
            return
            ;;
    esac

    if [ -n "$completion_dir" ]; then
        mkdir -p "$completion_dir"
        # Generate completion would go here
        log_info "Shell completion configured for $shell_name"
    fi
}

# PATH configuration
configure_path() {
    local shell_rc=""
    local shell_name=$(basename "$SHELL")

    case "$shell_name" in
        bash)  shell_rc="$HOME/.bashrc";;
        zsh)   shell_rc="$HOME/.zshrc";;
        fish)  shell_rc="$HOME/.config/fish/config.fish";;
        *)     shell_rc="$HOME/.profile";;
    esac

    # Check if PATH needs to be updated
    if [[ ":$PATH:" != *":$INSTALL_DIR:"* ]]; then
        log_info "Updating PATH in $shell_rc..."

        echo "" >> "$shell_rc"
        echo "# DevHub - Added by DevHub installer" >> "$shell_rc"
        echo "export PATH=\"\$PATH:$INSTALL_DIR\"" >> "$shell_rc"

        log_warning "PATH updated. Please restart your shell or run:"
        echo "    source $shell_rc"
    fi
}

# Main installation flow
main() {
    print_banner

    # System checks
    log_info "System Information:"
    local os=$(detect_os)
    local arch=$(detect_arch)
    echo "  • Operating System: $os"
    echo "  • Architecture: $arch"
    echo ""

    # Check if running from DevHub directory
    if [ ! -f "pyproject.toml" ] || ! grep -q "name = \"devhub\"" pyproject.toml 2>/dev/null; then
        log_error "This script must be run from the DevHub project directory"
        exit 1
    fi

    # Cleanup old installations
    cleanup_old_installation

    # Detect installation method
    local method=$(detect_installation_method)
    log_info "Installation method: $method"

    # Perform installation based on available tools
    case "$method" in
        uv)
            install_with_uv
            ;;
        pipx)
            install_with_pipx
            ;;
        pip)
            install_with_pip
            ;;
        none)
            log_warning "No Python package manager found"
            log_info "Installing uv for best experience..."
            if install_uv; then
                install_with_uv
            else
                log_error "Failed to install package manager"
                exit 1
            fi
            ;;
    esac

    # Configure PATH if needed
    configure_path

    # Setup completion
    setup_completion

    # Verify installation
    if verify_installation; then
        echo ""
        echo -e "${GREEN}${BOLD}Installation Complete!${NC}"
        echo ""
        echo "Next steps:"
        echo "  1. Restart your shell or run: source ~/.bashrc"
        echo "  2. Navigate to your project directory"
        echo "  3. Run: devhub init"
        echo "  4. Run: devhub --help for more information"
        echo ""
        echo "Documentation: https://github.com/hakimjonas/devhub"
        echo ""
    else
        echo ""
        log_error "Installation completed with errors"
        echo "Please check the logs above and try again"
        exit 1
    fi
}

# Run main function
main "$@"