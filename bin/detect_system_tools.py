#!/usr/bin/env python3

import subprocess
import sys
import json
import platform
import time
from pathlib import Path

# list of common utilities to check for
UTILITIES = [
    # System/Basic
    ["ls", "coreutils"],
    ["cat", "coreutils"],
    ["grep", "grep"],
    ["find", "findutils"],
    ["wc", "coreutils"],
    ["head", "coreutils"],
    ["tail", "coreutils"],
    ["ps", "procps"],
    ["df", "coreutils"],
    ["du", "coreutils"],
    ["which", "debianutils"],
    ["file", "file"],
    ["stat", "coreutils"],
    ["chmod", "coreutils"],
    ["chown", "coreutils"],
    # Development Tools
    ["git", "git"],
    ["jq", "jq"],
    ["python", "python3"],
    ["python3", "python3"],
    ["node", "nodejs"],
    ["npm", "npm"],
    ["pip", "python3-pip"],
    ["pip3", "python3-pip"],
    ["curl", "curl"],
    ["wget", "wget"],
    # Modern Alternatives
    ["fd", "fd-find"],
    ["rg", "ripgrep"],
    ["fzf", "fzf"],
    ["bat", "bat"],
    ["exa", "exa"],
    ["lsd", "lsd"],
    ["dust", "dust"],
    # Compression/Archive
    ["tar", "tar"],
    ["gzip", "gzip"],
    ["unzip", "unzip"],
    ["zip", "zip"],
    ["7z", "p7zip"],
    # Text Editors
    ["vim", "vim"],
    ["nvim", "nvim"],
    ["nano", "nano"],
    ["code", "code"],
    ["emacs", "emacs"],
    # Build Tools
    ["make", "make"],
    ["gcc", "gcc"],
    ["clang", "clang"],
    ["cargo", "cargo"],
    ["rustc", "rustc"],
    ["go", "golang-go"],
    ["java", "openjdk-17-jdk"],
    # Container Tools
    ["docker", "docker.io"],
    ["podman", "podman"],
    ["docker-compose", "docker-compose"],
    # Database Tools
    ["sqlite3", "sqlite3"],
    ["psql", "postgresql-client"],
    ["mysql", "mysql-client"],
    # Network Tools
    ["ping", "iputils-ping"],
    ["ss", "iproute2"],
    ["netstat", "net-tools"],
    ["nslookup", "dnsutils"],
    ["dig", "dnsutils"],
    # Package Managers
    ["apt", "apt"],
    ["apt-get", "apt"],
    ["yum", "yum"],
    ["dnf", "dnf"],
    ["pacman", "pacman"],
    ["brew", "homebrew"],
    # Security Tools
    ["gpg", "gnupg"],
    ["ssh", "openssh-client"],
    ["ssh-keygen", "openssh-client"],
    # System Info
    ["uname", "coreutils"],
    ["lscpu", "util-linux"],
    ["free", "procps"],
    ["uptime", "procps"],
    ["top", "procps"],
    ["htop", "htop"],
]


def check_command(cmd: str, package: str = "") -> bool:
    """Check if a command is available."""
    try:
        subprocess.run(["which", cmd], capture_output=True, check=True, timeout=5)
        return True
    except (
        subprocess.CalledProcessError,
        FileNotFoundError,
        subprocess.TimeoutExpired,
    ):
        return False


def get_package_info(command: str, package: str) -> str:
    """Get installation info for a package."""
    if package == "coreutils":
        return "Usually pre-installed (coreutils)"

    if package.endswith("-find"):
        return "Try: sudo apt install fd-find"

    if command == "code":
        return "Install VS Code from: https://code.visualstudio.com/"

    if package:
        return f"Try: sudo apt install {package}"
    else:
        return f"Command '{command}' - package unknown"


def detect_utilities() -> dict[str, dict]:
    """Detect which utilities are available."""
    results = {}

    for cmd, package in UTILITIES:
        available = check_command(cmd, package)
        results[cmd] = {
            "available": available,
            "package": package,
            "install_info": get_package_info(cmd, package) if not available else "",
        }

    return results


def categorize_utilities(results: dict) -> dict[str, list[str]]:
    """Categorize utilities by type."""
    categories = {
        "System/Basic": [
            "ls",
            "cat",
            "grep",
            "find",
            "wc",
            "head",
            "tail",
            "ps",
            "df",
            "du",
            "which",
            "file",
            "stat",
            "chmod",
            "chown",
        ],
        "Development": [
            "git",
            "jq",
            "python",
            "python3",
            "node",
            "npm",
            "pip",
            "pip3",
            "curl",
            "wget",
        ],
        "Modern Tools": ["fd", "rg", "fzf", "bat", "exa", "lsd", "dust"],
        "Compression": ["tar", "gzip", "unzip", "zip", "7z"],
        "Text Editors": ["vim", "nano", "code", "emacs"],
        "Build Tools": ["make", "gcc", "clang", "cargo", "rustc", "go", "java"],
        "Containers": ["docker", "podman", "docker-compose"],
        "Databases": ["sqlite3", "psql", "mysql"],
        "Network": ["ping", "ss", "netstat", "nslookup", "dig"],
        "Package Managers": ["apt", "apt-get", "yum", "dnf", "pacman", "brew"],
        "Security": ["gpg", "ssh", "ssh-keygen"],
        "System Info": ["uname", "lscpu", "free", "uptime", "top", "htop"],
    }

    categorized = {}
    for category, commands in categories.items():
        available = [
            cmd for cmd in commands if cmd in results and results[cmd]["available"]
        ]
        if available:
            categorized[category] = available

    return categorized


def print_console_output(results: dict, categorized: dict):
    """Print human-readable console output."""
    print("🔍 System Utility Detection Results")
    print("=" * 60)
    print(f"System: {platform.system()} {platform.release()}")
    print(f"Architecture: {platform.machine()}")
    print()

    # Summary
    available_count = sum(1 for r in results.values() if r["available"])
    total_count = len(results)
    print(f"📊 Summary: {available_count}/{total_count} utilities found")
    print()

    # Categorized results
    for category, commands in sorted(categorized.items()):
        print(f"✅ {category}:")
        for cmd in commands:
            print(f"   ✓ {cmd}")
        print()

    # Missing important tools
    important_missing = []
    for cmd in ["jq", "fd", "rg", "git", "docker", "podman"]:
        if cmd in results and not results[cmd]["available"]:
            important_missing.append(cmd)

    if important_missing:
        print("❌ Important Missing Tools:")
        for cmd in important_missing:
            info = results[cmd]["install_info"]
            print(f"   {cmd}: {info}")
        print()

    # Installation suggestions
    if "fd-find" in [r.get("package") for r in results.values()]:
        print("💡 Pro Tip: If you install 'fd-find', you'll get 'fd' command!")

    if any(r["package"] == "ripgrep" for r in results.values()):
        print("💡 Pro Tip: If you install 'ripgrep', you'll get 'rg' command!")


def create_llm_context(results: dict, categorized: dict) -> dict:
    """Create context for LLM."""
    # list of available utilities
    available_commands = [cmd for cmd, info in results.items() if info["available"]]

    # Alternative detection (modern vs classic)
    alternatives = {}
    classic_modern_pairs = [
        ("find", "fd"),
        ("grep", "rg"),
        ("ls", "exa"),
        ("cat", "bat"),
        ("top", "htop"),
        ("du", "dust"),
    ]

    for classic, modern in classic_modern_pairs:
        classic_available = classic in available_commands
        modern_available = modern in available_commands

        if modern_available:
            alternatives[classic] = modern
        elif classic_available:
            alternatives[modern] = classic

    # Create context object
    context = {
        "system_info": {
            "os": platform.system(),
            "release": platform.release(),
            "architecture": platform.machine(),
        },
        "available_utilities": available_commands,
        "categorized_utilities": categorized,
        "alternatives": alternatives,
        "special_features": {
            "has_modern_find": "fd" in available_commands,
            "has_modern_grep": "rg" in available_commands,
            "has_modern_ls": "exa" in available_commands or "lsd" in available_commands,
            "has_containers": any(
                cmd in available_commands for cmd in ["docker", "podman"]
            ),
            "has_git": "git" in available_commands,
            "has_jq": "jq" in available_commands,
        },
        "generated_at": time.time(),
    }

    return context


def save_llm_context(context: dict, output_file: Path):
    """Save LLM context to file."""
    output_file.parent.mkdir(parents=True, exist_ok=True)

    with open(output_file, "w") as f:
        json.dump(context, f, indent=2, sort_keys=True)


def main():
    """Main function."""
    if len(sys.argv) > 1 and sys.argv[1] in ["-h", "--help"]:
        print("Usage: detect_system_tools.py [--output-dir DIR]")
        print("Detects system utilities and creates LLM context")
        return 0

    # Parse arguments
    output_dir = None
    if "--output-dir" in sys.argv:
        try:
            idx = sys.argv.index("--output-dir")
            if idx + 1 < len(sys.argv):
                output_dir = Path(sys.argv[idx + 1])
            else:
                print("Error: --output-dir requires a directory")
                return 1
        except ValueError:
            print("Error: Invalid --output-dir usage")
            return 1

    # Detect utilities
    print("🔍 Detecting system utilities...")
    results = detect_utilities()
    categorized = categorize_utilities(results)

    # Print console output
    print_console_output(results, categorized)

    # Save LLM context if output dir specified
    if output_dir:
        context = create_llm_context(results, categorized)
        context_file = output_dir / "system_capabilities.json"
        save_llm_context(context, context_file)
        print(f"💾 LLM context saved to: {context_file}")
    else:
        # Default to ~/.pulsenode/
        default_dir = Path.home() / ".pulsenode"
        context = create_llm_context(results, categorized)
        context_file = default_dir / "system_capabilities.json"
        save_llm_context(context, context_file)
        print(f"💾 LLM context saved to: {context_file}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
