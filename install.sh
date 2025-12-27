#!/bin/bash
#
# Chitter Installer
# Real-time coordination for Claude Code agents
#
# Usage:
#   ./install.sh           Install Chitter
#   ./install.sh --update  Update existing installation
#   ./install.sh --uninstall  Remove Chitter
#

set -e

VERSION="1.0.0"
CHITTER_DIR="$HOME/.chitter"
CLAUDE_DIR="$HOME/.claude"
MCP_CONFIG="$CLAUDE_DIR/claude.json"
CLAUDE_MD="$CLAUDE_DIR/CLAUDE.md"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_header() {
    echo ""
    echo -e "${BLUE}╔════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║${NC}  ${GREEN}Chitter${NC} - Agent Coordination          ${BLUE}║${NC}"
    echo -e "${BLUE}║${NC}  v${VERSION}                                ${BLUE}║${NC}"
    echo -e "${BLUE}╚════════════════════════════════════════╝${NC}"
    echo ""
}

print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}!${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

print_info() {
    echo -e "${BLUE}→${NC} $1"
}

# Check Python version
check_python() {
    if command -v python3 &> /dev/null; then
        PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
        MAJOR=$(echo $PYTHON_VERSION | cut -d. -f1)
        MINOR=$(echo $PYTHON_VERSION | cut -d. -f2)

        if [ "$MAJOR" -ge 3 ] && [ "$MINOR" -ge 10 ]; then
            print_success "Python $PYTHON_VERSION found"
            return 0
        else
            print_error "Python 3.10+ required, found $PYTHON_VERSION"
            return 1
        fi
    else
        print_error "Python 3 not found. Please install Python 3.10+"
        return 1
    fi
}

# Install uv (Python package manager)
install_uv() {
    if command -v uvx &> /dev/null; then
        print_success "uv already installed"
        return 0
    fi

    print_info "Installing uv (Python package manager)..."
    if curl -LsSf https://astral.sh/uv/install.sh | sh 2>/dev/null; then
        # Add to PATH for current session
        export PATH="$HOME/.local/bin:$PATH"
        print_success "uv installed"
    else
        print_error "Failed to install uv. Install manually: https://docs.astral.sh/uv/"
        return 1
    fi
}

# Create directory structure
create_directories() {
    print_info "Creating directories..."
    mkdir -p "$CHITTER_DIR/workflows"
    mkdir -p "$CHITTER_DIR/hooks"
    mkdir -p "$CLAUDE_DIR"
    print_success "Created $CHITTER_DIR"
}

# Download or copy server.py
install_server() {
    print_info "Installing Chitter server..."

    # If running from repo, copy local file
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    if [ -f "$SCRIPT_DIR/server.py" ]; then
        cp "$SCRIPT_DIR/server.py" "$CHITTER_DIR/server.py"
        print_success "Server installed from local source"
    else
        # Download from GitHub
        REPO_URL="https://raw.githubusercontent.com/raydawg88/chitter/main/server.py"
        if curl -fsSL "$REPO_URL" -o "$CHITTER_DIR/server.py" 2>/dev/null; then
            print_success "Server downloaded from GitHub"
        else
            print_error "Failed to download server. Check your internet connection."
            exit 1
        fi
    fi

    chmod +x "$CHITTER_DIR/server.py"

    # Write version file
    echo "$VERSION" > "$CHITTER_DIR/version"
}

# Install hooks
install_hooks() {
    print_info "Installing coordination hooks..."

    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

    # Copy hook helper
    if [ -f "$SCRIPT_DIR/hook.py" ]; then
        cp "$SCRIPT_DIR/hook.py" "$CHITTER_DIR/hook.py"
    else
        REPO_URL="https://raw.githubusercontent.com/raydawg88/chitter/main/hook.py"
        curl -fsSL "$REPO_URL" -o "$CHITTER_DIR/hook.py" 2>/dev/null
    fi

    # Copy hook scripts
    if [ -f "$SCRIPT_DIR/hooks/pre-task.sh" ]; then
        cp "$SCRIPT_DIR/hooks/pre-task.sh" "$CHITTER_DIR/hooks/pre-task.sh"
        cp "$SCRIPT_DIR/hooks/post-task.sh" "$CHITTER_DIR/hooks/post-task.sh"
    else
        # Create inline
        cat > "$CHITTER_DIR/hooks/pre-task.sh" << 'HOOK'
#!/bin/bash
python3 ~/.chitter/hook.py pre
HOOK
        cat > "$CHITTER_DIR/hooks/post-task.sh" << 'HOOK'
#!/bin/bash
python3 ~/.chitter/hook.py post
HOOK
    fi

    chmod +x "$CHITTER_DIR/hooks/pre-task.sh"
    chmod +x "$CHITTER_DIR/hooks/post-task.sh"

    # Create default config
    cat > "$CHITTER_DIR/config.json" << 'CONFIG'
{
  "mode": "nudge"
}
CONFIG

    print_success "Hooks installed"
}

# Configure hooks in Claude settings
configure_hooks() {
    print_info "Configuring Claude Code hooks..."

    SETTINGS_FILE="$CLAUDE_DIR/settings.local.json"

    # Create or update settings
    python3 << EOF
import json
from pathlib import Path

settings_path = Path("$SETTINGS_FILE")

# Load existing settings or create new
if settings_path.exists():
    try:
        settings = json.loads(settings_path.read_text())
    except:
        settings = {}
else:
    settings = {}

# Ensure hooks structure exists
if "hooks" not in settings:
    settings["hooks"] = {}

# Add PreToolUse hook for Task
if "PreToolUse" not in settings["hooks"]:
    settings["hooks"]["PreToolUse"] = []

# Check if chitter hook already exists
pre_hooks = settings["hooks"]["PreToolUse"]
chitter_pre = [h for h in pre_hooks if "chitter" in h.get("command", "")]
if not chitter_pre:
    pre_hooks.append({
        "matcher": "Task",
        "command": "bash $CHITTER_DIR/hooks/pre-task.sh"
    })

# Add PostToolUse hook for Task
if "PostToolUse" not in settings["hooks"]:
    settings["hooks"]["PostToolUse"] = []

post_hooks = settings["hooks"]["PostToolUse"]
chitter_post = [h for h in post_hooks if "chitter" in h.get("command", "")]
if not chitter_post:
    post_hooks.append({
        "matcher": "Task",
        "command": "bash $CHITTER_DIR/hooks/post-task.sh"
    })

settings_path.write_text(json.dumps(settings, indent=2))
EOF

    print_success "Hooks configured in Claude Code"
}

# Update MCP configuration
configure_mcp() {
    print_info "Configuring MCP..."

    # Determine uv path (use uv run for scripts, not uvx)
    UV_PATH=$(which uv 2>/dev/null || echo "$HOME/.local/bin/uv")

    # Create mcp.json if it doesn't exist
    if [ ! -f "$MCP_CONFIG" ]; then
        echo '{"mcpServers": {}}' > "$MCP_CONFIG"
    fi

    # Check if Chitter is already configured
    if grep -q '"chitter"' "$MCP_CONFIG" 2>/dev/null; then
        print_warning "Chitter already in MCP config, updating..."
    fi

    # Use Python to safely update JSON
    python3 << EOF
import json
from pathlib import Path

config_path = Path("$MCP_CONFIG")
config = json.loads(config_path.read_text()) if config_path.exists() else {}

if "mcpServers" not in config:
    config["mcpServers"] = {}

config["mcpServers"]["chitter"] = {
    "type": "stdio",
    "command": "$UV_PATH",
    "args": ["run", "$CHITTER_DIR/server.py"],
    "description": "Real-time coordination for parallel agents. Check status, start workflows, review for conflicts."
}

config_path.write_text(json.dumps(config, indent=2))
EOF

    print_success "MCP configuration updated"
}

# Inject protocol into CLAUDE.md
inject_protocol() {
    print_info "Updating CLAUDE.md..."

    PROTOCOL_START="<!-- CHITTER:START -->"
    PROTOCOL_END="<!-- CHITTER:END -->"

    # Read protocol content
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    if [ -f "$SCRIPT_DIR/PROTOCOL.md" ]; then
        PROTOCOL_CONTENT=$(cat "$SCRIPT_DIR/PROTOCOL.md")
    else
        # Inline protocol if not available locally
        PROTOCOL_CONTENT='## CHITTER PROTOCOL (Real-Time Agent Coordination)

Chitter enables parallel agents to coordinate without conflicts.

**Before spawning parallel agents:**
1. Call `chitter_status` to check for active workflows
2. Call `chitter_workflow_start` with goal and planned agents
3. Inject the returned context into each agent task prompt

**After all agents complete:**
1. Call `chitter_workflow_review` to check for conflicts
2. Resolve any conflicts before presenting to user
3. Call `chitter_workflow_close` to clear workflow

**Chitter vs Goldfish:**
- Goldfish = persistent memory (across sessions)
- Chitter = ephemeral coordination (within workflows)'
    fi

    # Create CLAUDE.md if it doesn't exist
    if [ ! -f "$CLAUDE_MD" ]; then
        echo "# Claude Code Instructions" > "$CLAUDE_MD"
        echo "" >> "$CLAUDE_MD"
    fi

    # Check if protocol already exists
    if grep -q "$PROTOCOL_START" "$CLAUDE_MD" 2>/dev/null; then
        # Replace existing protocol section
        python3 << EOF
import re
from pathlib import Path

claude_md = Path("$CLAUDE_MD")
content = claude_md.read_text()

protocol = '''$PROTOCOL_START
$PROTOCOL_CONTENT
$PROTOCOL_END'''

# Replace between markers
pattern = r'$PROTOCOL_START.*?$PROTOCOL_END'
if re.search(pattern, content, re.DOTALL):
    content = re.sub(pattern, protocol, content, flags=re.DOTALL)
    claude_md.write_text(content)
EOF
        print_success "Updated existing Chitter protocol in CLAUDE.md"
    else
        # Append protocol section
        echo "" >> "$CLAUDE_MD"
        echo "$PROTOCOL_START" >> "$CLAUDE_MD"
        cat "$SCRIPT_DIR/PROTOCOL.md" >> "$CLAUDE_MD" 2>/dev/null || echo "$PROTOCOL_CONTENT" >> "$CLAUDE_MD"
        echo "$PROTOCOL_END" >> "$CLAUDE_MD"
        print_success "Added Chitter protocol to CLAUDE.md"
    fi
}

# Verify installation
verify_install() {
    print_info "Verifying installation..."

    # Check server syntax
    if python3 -m py_compile "$CHITTER_DIR/server.py" 2>/dev/null; then
        print_success "Server syntax OK"
    else
        print_error "Server has syntax errors"
        return 1
    fi

    # Check MCP config
    if python3 -c "import json; json.load(open('$MCP_CONFIG'))" 2>/dev/null; then
        print_success "MCP config valid"
    else
        print_error "MCP config is invalid JSON"
        return 1
    fi

    # Check uv is available
    UV_PATH=$(which uv 2>/dev/null || echo "$HOME/.local/bin/uv")
    if [ -x "$UV_PATH" ]; then
        print_success "uv available at $UV_PATH"
    else
        print_warning "uv not found in PATH. You may need to restart your shell."
    fi

    print_success "Installation verified"
}

# Uninstall Chitter
uninstall() {
    print_header
    echo "Uninstalling Chitter..."
    echo ""

    # Remove hooks from settings
    SETTINGS_FILE="$CLAUDE_DIR/settings.local.json"
    if [ -f "$SETTINGS_FILE" ]; then
        print_info "Removing hooks from settings..."
        python3 << EOF
import json
from pathlib import Path

settings_path = Path("$SETTINGS_FILE")
if settings_path.exists():
    settings = json.loads(settings_path.read_text())
    if "hooks" in settings:
        # Remove chitter hooks from PreToolUse
        if "PreToolUse" in settings["hooks"]:
            settings["hooks"]["PreToolUse"] = [
                h for h in settings["hooks"]["PreToolUse"]
                if "chitter" not in h.get("command", "")
            ]
        # Remove chitter hooks from PostToolUse
        if "PostToolUse" in settings["hooks"]:
            settings["hooks"]["PostToolUse"] = [
                h for h in settings["hooks"]["PostToolUse"]
                if "chitter" not in h.get("command", "")
            ]
    settings_path.write_text(json.dumps(settings, indent=2))
EOF
        print_success "Removed hooks"
    fi

    # Remove from MCP config
    if [ -f "$MCP_CONFIG" ]; then
        print_info "Removing from MCP config..."
        python3 << EOF
import json
from pathlib import Path

config_path = Path("$MCP_CONFIG")
if config_path.exists():
    config = json.loads(config_path.read_text())
    if "mcpServers" in config and "chitter" in config["mcpServers"]:
        del config["mcpServers"]["chitter"]
        config_path.write_text(json.dumps(config, indent=2))
EOF
        print_success "Removed from MCP config"
    fi

    # Remove from CLAUDE.md
    if [ -f "$CLAUDE_MD" ]; then
        print_info "Removing from CLAUDE.md..."
        python3 << EOF
import re
from pathlib import Path

claude_md = Path("$CLAUDE_MD")
if claude_md.exists():
    content = claude_md.read_text()
    # Remove protocol section including markers and surrounding newlines
    pattern = r'\n*<!-- CHITTER:START -->.*?<!-- CHITTER:END -->\n*'
    content = re.sub(pattern, '\n', content, flags=re.DOTALL)
    claude_md.write_text(content.strip() + '\n')
EOF
        print_success "Removed from CLAUDE.md"
    fi

    # Remove directory
    if [ -d "$CHITTER_DIR" ]; then
        print_info "Removing $CHITTER_DIR..."
        rm -rf "$CHITTER_DIR"
        print_success "Removed Chitter directory"
    fi

    echo ""
    print_success "Chitter uninstalled successfully"
    echo ""
    echo "Restart Claude Code to apply changes."
}

# Main install function
install() {
    print_header

    echo "Installing Chitter..."
    echo ""

    check_python || exit 1
    install_uv || exit 1
    create_directories
    install_server
    install_hooks
    configure_hooks
    configure_mcp
    inject_protocol
    verify_install

    echo ""
    echo -e "${GREEN}════════════════════════════════════════${NC}"
    echo -e "${GREEN}  Chitter installed successfully!${NC}"
    echo -e "${GREEN}════════════════════════════════════════${NC}"
    echo ""
    echo "Next steps:"
    echo "  1. Restart Claude Code"
    echo "  2. Test with: chitter_status"
    echo ""
    echo "Usage:"
    echo "  Before parallel agents: chitter_workflow_start"
    echo "  After agents complete:  chitter_workflow_review"
    echo ""
}

# Parse arguments
case "${1:-}" in
    --uninstall|-u)
        uninstall
        ;;
    --update|-U)
        echo "Updating Chitter..."
        install
        ;;
    --help|-h)
        print_header
        echo "Usage:"
        echo "  ./install.sh            Install Chitter"
        echo "  ./install.sh --update   Update existing installation"
        echo "  ./install.sh --uninstall Remove Chitter"
        echo "  ./install.sh --help     Show this help"
        echo ""
        ;;
    *)
        install
        ;;
esac
