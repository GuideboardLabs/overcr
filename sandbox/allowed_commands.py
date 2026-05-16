"""
OverCR v2.6.0 — Allowed Commands

The canonical allowlist for sandbox command execution. Only these
commands may execute inside the sandbox. The allowlist is intentionally
minimal and security-conservative — new commands require explicit
operator approval to add.

Allowed categories:
  - Read:  ls, pwd, cat, head, tail, grep, find
  - Write: echo, cp, mv, mkdir, rm, touch, diff
  - VCS:   git status, git diff

Explicitly forbidden (non-exhaustive — anything not on the list):
  - sudo, doas, pkexec, su
  - curl, wget, ssh, nc, telnet
  - apt, pip, npm, cargo, gem, go
  - bash -c, sh -c, python, node, perl, ruby
  - git commit, git push, git pull, git clone
  - systemctl, service, initctl
  - chmod, chown, setfacl
"""

# ── Allowed commands ──────────────────────────────────────

ALLOWED_COMMANDS = {
    "ls",
    "pwd",
    "cat",
    "head",
    "tail",
    "grep",
    "find",
    "echo",
    "cp",
    "mv",
    "mkdir",
    "rm",
    "touch",
    "diff",
}

# ── Git sub-commands (allowed only in specific forms) ─────

ALLOWED_GIT_SUBCOMMANDS = {"status", "diff"}

# ── Blocked command patterns (non-exhaustive enumeration) ──

BLOCKED_COMMANDS = {
    "sudo", "doas", "pkexec", "su",
    "curl", "wget", "ssh", "nc", "ncat", "telnet", "ftp",
    "apt", "apt-get", "dpkg", "yum", "dnf", "pacman", "snap",
    "pip", "pip3", "npm", "yarn", "cargo", "gem", "go",
    "bash", "sh", "zsh", "dash", "ksh",
    "python", "python3", "node", "nodejs", "perl", "ruby", "php", "lua",
    "systemctl", "service", "initctl", "rc-service",
    "chmod", "chown", "chgrp", "setfacl", "getfacl",
    "kill", "pkill", "killall",
    "mount", "umount", "losetup",
    "iptables", "nft", "ufw", "firewall-cmd",
    "docker", "podman", "containerd",
    "cron", "crontab", "at", "batch",
    "git",  # Blocked as bare command; only specific sub-commands allowed
}

# ── Blocked token patterns (checked in argv) ────────────────

BLOCKED_TOKENS = {
    # Shell metacharacters
    ";", "&&", "||", "|", "$(", "${", "`",
    # Redirections
    ">", ">>", "<", "<<<", "<<",
    # Wildcard abuse patterns
    "../", "..\\",
    # Environment injection
    "PATH=", "HOME=", "LD_PRELOAD", "LD_LIBRARY_PATH",
    # Subshell invocation
    "bash -c", "sh -c", "python -c",
}

# ── Path boundaries ─────────────────────────────────────────

# Paths that are always outside sandbox (never writable)
PROTECTED_PATHS = [
    "/etc/", "/boot/", "/sys/", "/proc/", "/dev/",
    "/usr/bin/", "/usr/sbin/", "/usr/lib/", "/usr/lib64/",
    "/usr/local/bin/", "/usr/local/sbin/",
    "/lib/", "/lib64/", "/sbin/", "/bin/",
    "/root/", "/home/.ssh/",
]

# ── Helper functions ────────────────────────────────────────

def is_command_allowed(executable_name: str) -> bool:
    """Check if an executable name is on the allowlist."""
    return executable_name in ALLOWED_COMMANDS

def is_command_blocked(executable_name: str) -> bool:
    """Check if a command is explicitly blocked."""
    return executable_name.lower() in BLOCKED_COMMANDS

def is_git_subcommand_allowed(subcommand: str) -> bool:
    """Check if a git sub-command is allowed."""
    return subcommand in ALLOWED_GIT_SUBCOMMANDS

def token_is_blocked(token: str) -> bool:
    """Check if a token appears in the blocked list."""
    token_lower = token.lower()
    for blocked in BLOCKED_TOKENS:
        if blocked.lower() in token_lower:
            return True
    return False

def path_is_protected(path: str) -> bool:
    """Check if a filesystem path is protected (never writable from sandbox)."""
    normalized = path.rstrip("/") + "/"
    for protected in PROTECTED_PATHS:
        if normalized.startswith(protected):
            return True
    return False
