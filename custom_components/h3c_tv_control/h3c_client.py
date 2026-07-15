"""H3C S5550 Telnet client for TV internet ACL control."""

from __future__ import annotations

from contextlib import suppress
import re
import socket
import time
from types import TracebackType
from typing import Any, Self

from .const import DEFAULT_ACL_ID, TVS, TVConfig

IAC = 255
DONT = 254
DO = 253
WONT = 252
WILL = 251
H3C_PROMPT_PATTERN = re.compile(r"<[^>\r\n]+>|\[[^\]\r\n]+\]")


class H3CClientError(Exception):
    """Base exception for H3C client errors."""


class H3CConnectionError(H3CClientError):
    """Raised when the switch cannot be reached or its prompt is invalid."""


class H3CAuthenticationError(H3CClientError):
    """Raised when the switch rejects the supplied credentials."""


class H3CResponseError(H3CClientError):
    """Raised when the switch returns an unexpected response."""


class H3CTelnetClient:
    """Minimal Telnet client for H3C Comware switches."""

    def __init__(
        self,
        host: str,
        username: str,
        password: str,
        port: int = 23,
        timeout: int = 5,
    ) -> None:
        """Initialize a Telnet connection definition."""
        self.host = host
        self.username = username
        self.password = password
        self.port = port
        self.timeout = timeout
        self.sock: socket.socket | None = None

    def __enter__(self) -> Self:
        """Connect and return this client."""
        self.connect()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close the Telnet connection."""
        self.close()

    def connect(self) -> str:
        """Connect and authenticate to the switch."""
        try:
            self.sock = socket.create_connection(
                (self.host, self.port), timeout=self.timeout
            )
        except OSError as err:
            raise H3CConnectionError(
                f"无法连接交换机 {self.host}:{self.port}"
            ) from err
        self.sock.settimeout(1)
        login_prompt = self.read_until_any(
            ["login:", "username:", "user name:"], timeout=8
        )
        if not self._contains_any(
            login_prompt, ["login:", "username:", "user name:"]
        ):
            raise H3CConnectionError("交换机未返回用户名提示")
        self.send_line(self.username)
        password_prompt = self.read_until_any(["password:"], timeout=8)
        if not self._contains_any(password_prompt, ["password:"]):
            raise H3CConnectionError("交换机未返回密码提示")
        self.send_line(self.password)
        response = self.read_until_prompt(timeout=8)
        if self._contains_any(
            response,
            [
                "password:",
                "login:",
                "authentication failed",
                "login failed",
                "invalid password",
            ],
        ):
            raise H3CAuthenticationError("交换机用户名或密码错误")
        if not H3C_PROMPT_PATTERN.search(response):
            raise H3CAuthenticationError("登录后未检测到 H3C 命令提示符")
        return response

    def close(self) -> None:
        """Close the active socket."""
        if self.sock:
            with suppress(OSError):
                self.send_line("quit")
            self.sock.close()
            self.sock = None

    def run_commands(self, commands: list[str], wait: float = 0.8) -> str:
        """Run commands sequentially and return their combined output."""
        output: list[str] = []
        for command in commands:
            self.send_line(command)
            time.sleep(wait)
            output.append(self.read_available(timeout=2))
        return "\n".join(output)

    def send_line(self, text: str) -> None:
        """Send one command line to the switch."""
        if self.sock:
            self.sock.sendall(text.encode("ascii") + b"\r\n")

    def read_until_any(self, keywords: list[str], timeout: int = 5) -> str:
        """Read until one of the supplied keywords appears."""
        end_time = time.time() + timeout
        output = ""
        while time.time() < end_time:
            output += self.read_available(timeout=0.8)
            lower_output = output.lower()
            if any(keyword.lower() in lower_output for keyword in keywords):
                return output
        return output

    def read_until_prompt(self, timeout: int = 8) -> str:
        """Read until an H3C command prompt appears."""
        end_time = time.monotonic() + timeout
        output = ""
        while time.monotonic() < end_time:
            output += self.read_available(timeout=0.8)
            if H3C_PROMPT_PATTERN.search(output):
                return output
            time.sleep(0.1)
        return output

    @staticmethod
    def _contains_any(output: str, keywords: list[str]) -> bool:
        lower_output = output.lower()
        return any(keyword.lower() in lower_output for keyword in keywords)

    def read_available(self, timeout: float = 1) -> str:
        """Read all currently available Telnet output."""
        end_time = time.time() + timeout
        chunks: list[bytes] = []
        while time.time() < end_time and self.sock:
            try:
                data = self.sock.recv(4096)
            except TimeoutError:
                break
            if not data:
                break
            chunks.append(self._negotiate_telnet(data))
            self.sock.settimeout(0.2)
        if self.sock:
            self.sock.settimeout(1)
        return b"".join(chunks).decode("utf-8", errors="ignore").replace("\x00", "")

    def _negotiate_telnet(self, data: bytes) -> bytes:
        clean = bytearray()
        i = 0
        while i < len(data):
            byte = data[i]
            if byte != IAC:
                clean.append(byte)
                i += 1
                continue
            if i + 2 >= len(data):
                break
            command = data[i + 1]
            option = data[i + 2]
            if command == WILL and self.sock:
                self.sock.sendall(bytes([IAC, DONT, option]))
                i += 3
            elif command == DO and self.sock:
                self.sock.sendall(bytes([IAC, WONT, option]))
                i += 3
            elif command in (WONT, DONT):
                i += 3
            else:
                i += 2
        return bytes(clean)


class H3CTVClient:
    """High-level client for TV internet ACL operations."""

    def __init__(
        self,
        host: str,
        username: str,
        password: str,
        port: int = 23,
        acl_id: int = DEFAULT_ACL_ID,
    ) -> None:
        """Initialize the high-level ACL client."""
        if not password:
            raise ValueError("交换机密码不能为空")
        self.host = host
        self.username = username
        self.password = password
        self.port = port
        self.acl_id = acl_id
        self.tvs = TVS

    def enable_internet(self, tv_key: str) -> str:
        """Allow one TV to access the internet."""
        tv = self._get_tv(tv_key)
        commands = [
            "system-view",
            f"acl advanced {self.acl_id}",
            f"undo rule {tv['deny_rule']}",
            "quit",
            "quit",
        ]
        output = self._run(commands)
        self._ensure_no_command_error(output)
        return output

    def disable_internet(self, tv_key: str) -> str:
        """Block one TV from accessing the internet."""
        tv = self._get_tv(tv_key)
        commands = [
            "system-view",
            f"acl advanced {self.acl_id}",
            f"undo rule {tv['deny_rule']}",
            f"rule {tv['deny_rule']} deny ip source {tv['ip']} 0",
            "quit",
            "quit",
        ]
        output = self._run(commands)
        self._ensure_no_command_error(output)
        return output

    def get_statuses(self) -> dict[str, dict[str, Any]]:
        """Return internet access state for every configured TV."""
        acl_output = self._run(["screen-length disable", "display acl all"])
        lower_output = acl_output.lower()
        if "acl" not in lower_output or str(self.acl_id) not in acl_output:
            raise H3CResponseError(
                f"交换机响应中未找到 ACL {self.acl_id}，无法判断电视状态"
            )
        self._ensure_no_command_error(acl_output)
        statuses: dict[str, dict[str, Any]] = {}
        for key, tv in self.tvs.items():
            deny_rule = re.compile(
                rf"rule\s+{tv['deny_rule']}\s+deny\s+ip\s+source\s+"
                rf"{re.escape(tv['ip'])}\s+0",
                re.IGNORECASE,
            )
            statuses[key] = {
                **tv,
                "internet_enabled": deny_rule.search(acl_output) is None,
            }
        return statuses

    def _run(self, commands: list[str]) -> str:
        try:
            with H3CTelnetClient(
                self.host, self.username, self.password, self.port
            ) as client:
                return client.run_commands(commands)
        except H3CClientError:
            raise
        except OSError as err:
            raise H3CConnectionError("与交换机通信中断") from err

    def _ensure_no_command_error(self, output: str) -> None:
        error_markers = [
            "unrecognized command",
            "too many parameters",
            "no such acl",
            "invalid input",
            "wrong parameter",
            "permission denied",
        ]
        lower_output = output.lower()
        if any(marker in lower_output for marker in error_markers):
            raise H3CResponseError(f"交换机返回命令错误：\n{output}")

    def _get_tv(self, tv_key: str) -> TVConfig:
        if tv_key not in self.tvs:
            valid_keys = ", ".join(self.tvs)
            raise ValueError(f"未知电视: {tv_key}. 可用值: {valid_keys}")
        return self.tvs[tv_key]
