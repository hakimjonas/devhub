#!/usr/bin/env bash
# DevHub Enterprise Uninstaller
# Safely removes DevHub from your system

set -e

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
BOLD='\033[1m'
NC='\033[0m'

# Configuration
DEVHUB_HOME="${DEVHUB_HOME:-$HOME/.devhub}"
INSTALL_DIR="$HOME/.local/bin"

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
    echo "║          DevHub Uninstaller                ║"
    echo "╚════════════════════════════════════════════╝"
    echo -e "${NC}"
}

# Detect installation method
detect_installation() {
    if command -v devhub &> /dev/null; then
        local devhub_path=$(which devhub)

        # Check if installed with uv
        if uv tool list 2>/dev/null | grep -q devhub; then
            echo "uv"
        # Check if installed with pipx
        elif pipx list 2>/dev/null | grep -q devhub; then
            echo "pipx"
        # Check if it's our wrapper script
        elif [ -f "$devhub_path" ] && grep -q "DevHub wrapper script" "$devhub_path" 2>/dev/null; then
            echo "pip"
        else
            echo "unknown"
        fi
    else
        echo "none"
    fi
}

# Remove uv installation
remove_uv_installation() {
    log_info "Removing DevHub installed with uv..."

    # Uninstall the tool
    local uninstall_success=true
    if ! uv tool uninstall devhub 2>/dev/null; then
        log_warning "uv tool uninstall failed, continuing with manual cleanup..."
        uninstall_success=false
    fi

    # Remove the tool directory entirely
    local uv_tools_dir="$HOME/.local/share/uv/tools/devhub"
    if [ -d "$uv_tools_dir" ]; then
        log_info "Removing installation directory..."
        rm -rf "$uv_tools_dir"
    fi

    # Remove any stale executable links
    local bin_path="$HOME/.local/bin/devhub"
    if [ -f "$bin_path" ]; then
        log_info "Removing executable..."
        rm -f "$bin_path"
    fi

    # Clear UV cache
    if command -v uv &> /dev/null; then
        log_info "Clearing UV cache..."
        uv cache clean 2>/dev/null || true
    fi

    if $uninstall_success; then
        log_success "DevHub completely removed from uv"
        return 0
    else
        log_warning "DevHub manually cleaned up (uv uninstall failed)"
        return 0  # Still return success since we cleaned up manually
    fi
}

# Remove pipx installation
remove_pipx_installation() {
    log_info "Removing DevHub installed with pipx..."

    # Uninstall the tool
    local uninstall_success=true
    if ! pipx uninstall devhub 2>/dev/null; then
        log_warning "pipx uninstall failed, continuing with manual cleanup..."
        uninstall_success=false
    fi

    # Remove any stale executable links
    local bin_path="$HOME/.local/bin/devhub"
    if [ -f "$bin_path" ]; then
        log_info "Removing executable..."
        rm -f "$bin_path"
    fi

    # Clean up pipx environment directory
    local pipx_venv_dir="$HOME/.local/share/pipx/venvs/devhub"
    if [ -d "$pipx_venv_dir" ]; then
        log_info "Removing pipx virtual environment..."
        rm -rf "$pipx_venv_dir"
    fi

    # Clean up pipx data directory
    local pipx_data_dir="$HOME/.local/share/pipx/pyvenvs/devhub"
    if [ -d "$pipx_data_dir" ]; then
        log_info "Removing pipx data directory..."
        rm -rf "$pipx_data_dir"
    fi

    if $uninstall_success; then
        log_success "DevHub completely removed from pipx"
        return 0
    else
        log_warning "DevHub manually cleaned up (pipx uninstall failed)"
        return 0  # Still return success since we cleaned up manually
    fi
}

# Remove pip installation
remove_pip_installation() {
    log_info "Removing DevHub installed with pip..."

    # Remove wrapper script
    if [ -f "$INSTALL_DIR/devhub" ]; then
        rm -f "$INSTALL_DIR/devhub"
        log_success "Removed DevHub command"
    fi

    # Remove virtual environment
    if [ -d "$DEVHUB_HOME/venv" ]; then
        rm -rf "$DEVHUB_HOME/venv"
        log_success "Removed DevHub virtual environment"
    fi

    # Try to uninstall from global pip as well (in case of old installations)
    if command -v pip &> /dev/null; then
        pip uninstall -y devhub 2>/dev/null || true
    fi
    if command -v pip3 &> /dev/null; then
        pip3 uninstall -y devhub 2>/dev/null || true
    fi

    # Clean up any Python cache files
    if [ -d "$DEVHUB_HOME" ]; then
        find "$DEVHUB_HOME" -name "*.pyc" -delete 2>/dev/null || true
        find "$DEVHUB_HOME" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
    fi

    return 0
}

# Clean up configuration
cleanup_config() {
    log_info "Cleaning up configuration..."

    # Ask about keeping config
    echo -n "Do you want to remove DevHub configuration and cache? (y/N): "
    read -r response

    if [[ "$response" =~ ^[Yy]$ ]]; then
        if [ -d "$DEVHUB_HOME" ]; then
            # Keep a backup just in case
            local backup_dir="$HOME/.devhub-backup-$(date +%Y%m%d-%H%M%S)"
            mv "$DEVHUB_HOME" "$backup_dir"
            log_success "Configuration backed up to $backup_dir"
            log_info "You can safely delete this backup after verifying everything works"
        fi
    else
        log_info "Configuration preserved at $DEVHUB_HOME"
    fi
}

# Remove PATH entries
cleanup_path() {
    log_info "Cleaning up PATH entries..."

    local shells=(".bashrc" ".zshrc" ".profile" ".bash_profile")
    local cleaned=0

    for shell_rc in "${shells[@]}"; do
        local rc_file="$HOME/$shell_rc"
        if [ -f "$rc_file" ]; then
            # Create backup
            cp "$rc_file" "$rc_file.devhub-backup"

            # Remove DevHub PATH entries
            if grep -q "# DevHub - Added by DevHub installer" "$rc_file"; then
                sed -i '/# DevHub - Added by DevHub installer/,+1d' "$rc_file"
                cleaned=1
                log_success "Cleaned PATH from $shell_rc"
            fi
        fi
    done

    if [ $cleaned -eq 1 ]; then
        log_warning "PATH cleaned. Please restart your shell for changes to take effect"
    fi
}

# Main uninstall flow
main() {
    print_banner

    # Detect installation
    local method=$(detect_installation)

    if [ "$method" = "none" ]; then
        log_warning "DevHub is not installed on this system"
        exit 0
    fi

    log_info "DevHub installation detected: $method"
    echo ""

    # Confirm uninstallation
    echo -e "${YELLOW}Warning: This will remove DevHub from your system${NC}"
    echo -n "Are you sure you want to continue? (y/N): "
    read -r response

    if [[ ! "$response" =~ ^[Yy]$ ]]; then
        log_info "Uninstallation cancelled"
        exit 0
    fi

    echo ""

    # Remove based on installation method
    case "$method" in
        uv)
            remove_uv_installation
            ;;
        pipx)
            remove_pipx_installation
            ;;
        pip)
            remove_pip_installation
            ;;
        unknown)
            log_warning "Unknown installation method"
            log_info "Attempting manual cleanup..."
            # Try all methods
            remove_uv_installation 2>/dev/null || true
            remove_pipx_installation 2>/dev/null || true
            remove_pip_installation 2>/dev/null || true
            ;;
    esac

    # Clean up configuration
    cleanup_config

    # Clean up PATH
    cleanup_path

    echo ""
    echo -e "${GREEN}${BOLD}Uninstallation Complete!${NC}"
    echo ""
    echo "DevHub has been removed from your system."
    echo "Thank you for using DevHub!"
    echo ""
}

# Run main function
main "$@"