# Deep VCS Security Model

Deep VCS is built with a "Security-First" philosophy, providing robust protection for distributed development, automated pipelines, and community plugins.

## 1. Zero-Trust P2P Verification

In a distributed environment, trust must be earned. Deep implements cryptographic verification for all data received from peers.

- **Commit Signing**: All commits can be cryptographically signed using HMAC-SHA256 (with GPG support in development).
- **Mandatory Verification**: Recieved commits are rejected if they lack a valid signature or if the signing key has been revoked.
- **Merkle Audit Chains**: Repository logs and security actions are recorded in a Merkle-chained audit log, making tampering computationally visible.

## 2. Hardened Sandbox Execution

Automated CI/CD pipelines and external plugins run in a restricted execution environment to protect the host system.

### Isolation Layer
- **Environment Scrubbing**: The sandbox inherits almost no environment variables from the host.
- **Restricted PATH**: The `PATH` is limited to standard system binaries (e.g., `/usr/bin`, `C:\Windows\System32`). Host-specific tools and private binaries are excluded unless explicitly permitted.
- **Filesystem Constraints**: Writes are restricted to specific allowlisted directories (e.g., `.deep_git/tmp`, `.deep_git/wal`).

### Control Plane
- **Timeouts**: Every execution has a mandatory timeout (default 30s) to prevent resource exhaustion (Denial of Service).
- **Operation Logging**: Every system call and significant operation within the sandbox is logged for auditing.

## 3. Secure CI/CD Pipelines

Deep's integrated pipeline engine uses the hardened sandbox for all user-defined jobs.

- **Non-Interactive**: Pipelines run without terminal access.
- **Secure Wrappers**: Shell commands are executed via secure `subprocess` wrappers, avoiding direct `os.system` calls and mitigating command injection risks.

## 4. Role-Based Access Control (RBAC)

For platform-hosted repositories, Deep implements a granular permission model:

- **Owner**: Full control, including repository deletion and permission management.
- **Maintainer**: Can manage branches, merge PRs, and configure pipelines.
- **Contributor**: Can push to specific branches and open PRs.
- **Viewer**: Read-only access to code and metadata.

## 5. Audit Logging

Sensitive operations (permissions changes, key rotation, pipeline configuration) are recorded in the `.deep_git/audit.log`.

- **Integrity**: Each log entry is part of a Merkle chain.
- **Visibility**: Use `deep audit` to view the history of security events.

---

*For vulnerability reports, please contact security@deep-vcs.io.*
