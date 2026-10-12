from __future__ import annotations

from dataclasses import dataclass, field



@dataclass(frozen=True)
class SandboxPolicy:
    """Immutable policy governing sandbox behavior."""

    max_runtime_seconds: int = 120
    max_memory_mb: int = 512
    max_output_bytes: int = 1_000_000
    allow_network: bool = False
    allow_file_writes: bool = False
    allow_spawn: bool = True
    allowed_test_runners: list[str] = field(default_factory=lambda: ["pytest"])

    def validate_command(self, command: list[str]) -> list[str]:
        """Return the command if it passes policy, else raise ValueError."""
        if not self.allow_network and "-network" in " ".join(command):
            msg = "Network access not allowed in sandbox."
            raise ValueError(msg)
        if not self.allow_spawn and any("&" in str(c) for c in command):
            msg = "Shell metacharacters not allowed; use argument arrays."
            raise ValueError(msg)
        return command


@dataclass(frozen=True)
class RunnerConfig:
    """Configuration for a test runner instance."""

    policy: SandboxPolicy = field(default_factory=SandboxPolicy)
    timeout_seconds: int = 120
    image: str | None = None  # Docker image if using Docker runner