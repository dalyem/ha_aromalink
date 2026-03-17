#!/usr/bin/env python3
"""Standalone Aroma-Link probe script for local endpoint debugging."""

from __future__ import annotations

import argparse
import hashlib
import http.cookiejar
import json
import os
import ssl
import uuid
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import HTTPCookieProcessor, HTTPHandler, HTTPSHandler, Request, build_opener


USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/91.0.4472.124 Safari/537.36"
)


@dataclass
class ProbeConfig:
    username: str
    password: str
    user_id: str | None
    device_id: str | None
    verify_ssl: bool
    switch_state: str | None


@dataclass
class ProbeResponse:
    method: str
    url: str
    status: int
    headers: dict[str, str]
    body: str


class ProbeClient:
    """Minimal cookie-aware HTTP client using only the stdlib."""

    def __init__(self, verify_ssl: bool):
        self.cookie_jar = http.cookiejar.CookieJar()
        ssl_context = None
        if not verify_ssl:
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE

        handlers = [
            HTTPCookieProcessor(self.cookie_jar),
            HTTPHandler(),
        ]
        if ssl_context is not None:
            handlers.append(HTTPSHandler(context=ssl_context))
        else:
            handlers.append(HTTPSHandler())
        self.opener = build_opener(*handlers)

    def request(
        self,
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        data: bytes | None = None,
        timeout: int = 15,
    ) -> ProbeResponse:
        request = Request(url, data=data, headers=headers or {}, method=method)
        try:
            response = self.opener.open(request, timeout=timeout)
            status = response.status
            response_headers = dict(response.headers.items())
            body = response.read().decode("utf-8", errors="replace")
            return ProbeResponse(method, url, status, response_headers, body)
        except HTTPError as err:
            body = err.read().decode("utf-8", errors="replace")
            return ProbeResponse(method, url, err.code, dict(err.headers.items()), body)
        except URLError as err:
            return ProbeResponse(method, url, 0, {}, f"URL error: {err}")

    def get_cookie(self, name: str) -> str | None:
        for cookie in self.cookie_jar:
            if cookie.name == name:
                return cookie.value
        return None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Probe Aroma-Link endpoints locally.")
    parser.add_argument("--env-file", default=".env.aromalink", help="Path to env file. Default: .env.aromalink")
    parser.add_argument("--device-id", help="Override device ID from env file.")
    parser.add_argument("--user-id", help="Override user ID from env file.")
    parser.add_argument("--switch", choices=("on", "off"), help="Optionally send a real app switch command.")
    parser.add_argument("--skip-web", action="store_true", help="Skip the legacy website probes.")
    parser.add_argument("--skip-app", action="store_true", help="Skip the mobile app probes.")
    return parser.parse_args()


def load_env_file(path: str) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path or not os.path.exists(path):
        return env

    with open(path, "r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            env[key.strip()] = value.strip().strip("'").strip('"')
    return env


def env_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


def build_config(args: argparse.Namespace) -> ProbeConfig:
    file_env = load_env_file(args.env_file)

    def get_value(name: str, default: str | None = None) -> str | None:
        return os.environ.get(name, file_env.get(name, default))

    username = get_value("AROMALINK_USERNAME")
    password = get_value("AROMALINK_PASSWORD")
    if not username or not password:
        raise SystemExit(
            "Missing AROMALINK_USERNAME or AROMALINK_PASSWORD. "
            "Set them in the environment or your env file."
        )

    return ProbeConfig(
        username=username,
        password=password,
        user_id=args.user_id or get_value("AROMALINK_USER_ID"),
        device_id=args.device_id or get_value("AROMALINK_DEVICE_ID"),
        verify_ssl=env_bool(get_value("AROMALINK_VERIFY_SSL"), default=False),
        switch_state=args.switch,
    )


def pretty_body(text: str, limit: int = 2000) -> str:
    return text if len(text) <= limit else f"{text[:limit]}...<truncated>"


def mask_token(token: str | None) -> str | None:
    if not token:
        return None
    if len(token) <= 12:
        return token
    return f"{token[:6]}...{token[-6:]}"


def find_nested_value(value: Any, keys: set[str]) -> Any:
    if isinstance(value, dict):
        for key, nested in value.items():
            if key.replace("-", "_").lower() in keys:
                return nested
            found = find_nested_value(nested, keys)
            if found is not None:
                return found
    if isinstance(value, list):
        for item in value:
            found = find_nested_value(item, keys)
            if found is not None:
                return found
    return None


def parse_json(text: str) -> Any | None:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def print_response(label: str, response: ProbeResponse) -> Any | None:
    print(f"\n[{label}] {response.method} {response.url}")
    print(f"status: {response.status}")
    interesting_headers = {
        key: value
        for key, value in response.headers.items()
        if key.lower() in {"content-type", "access-token", "authorization", "set-cookie"}
    }
    if interesting_headers:
        print(f"headers: {json.dumps(interesting_headers, indent=2)}")
    print(f"body: {pretty_body(response.body)}")
    return parse_json(response.body)


def form_multipart(fields: dict[str, str]) -> tuple[bytes, str]:
    boundary = f"Boundary+{uuid.uuid4().hex.upper()}"
    lines: list[bytes] = []
    for name, value in fields.items():
        lines.append(f"--{boundary}\r\n".encode())
        lines.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        lines.append(f"{value}\r\n".encode())
    lines.append(f"--{boundary}--\r\n".encode())
    body = b"".join(lines)
    return body, f"multipart/form-data; boundary={boundary}"


def app_login(client: ProbeClient, config: ProbeConfig) -> tuple[str | None, str | None, str | None]:
    user_id = config.user_id
    access_token = None
    refresh_token = None
    hashed_password = hashlib.md5(config.password.encode("utf-8")).hexdigest()
    base_headers = {"User-Agent": USER_AGENT}

    login_body, login_content_type = form_multipart(
        {"userName": config.username, "password": hashed_password}
    )
    response = client.request(
        "POST",
        "http://www.aroma-link.com/v1/app/user/newLogin",
        headers={**base_headers, "Content-Type": login_content_type},
        data=login_body,
    )
    payload = print_response("app_new_login", response)
    found_user_id = find_nested_value(payload, {"userid", "user_id", "uid"}) if payload else None
    if found_user_id is not None:
        user_id = str(found_user_id)

    token_body, token_content_type = form_multipart(
        {"userName": config.username, "password": hashed_password}
    )
    response = client.request(
        "POST",
        "http://www.aroma-link.com/v2/app/token",
        headers={**base_headers, "Content-Type": token_content_type},
        data=token_body,
    )
    payload = print_response("app_token", response)
    if payload:
        token = find_nested_value(payload, {"accesstoken", "access_token", "token", "authorization"})
        if isinstance(token, str) and token.lower().startswith("bearer "):
            token = token[7:]
        access_token = token if isinstance(token, str) else access_token
        refresh = find_nested_value(payload, {"refreshtoken", "refresh_token"})
        refresh_token = refresh if isinstance(refresh, str) else refresh_token
        found_user_id = find_nested_value(payload, {"userid", "user_id", "uid"})
        if found_user_id is not None:
            user_id = str(found_user_id)

    if refresh_token:
        refresh_body, refresh_content_type = form_multipart({"refreshToken": refresh_token})
        response = client.request(
            "POST",
            "http://www.aroma-link.com/v2/app/refresh/token",
            headers={**base_headers, "Content-Type": refresh_content_type},
            data=refresh_body,
        )
        payload = print_response("app_refresh_token", response)
        if payload:
            token = find_nested_value(payload, {"accesstoken", "access_token", "token", "authorization"})
            if isinstance(token, str) and token.lower().startswith("bearer "):
                token = token[7:]
            access_token = token if isinstance(token, str) else access_token
            found_user_id = find_nested_value(payload, {"userid", "user_id", "uid"})
            if found_user_id is not None:
                user_id = str(found_user_id)

    print(
        f"\n[app_auth_summary] user_id={user_id} "
        f"access_token={mask_token(access_token)} refresh_token={mask_token(refresh_token)}"
    )
    return user_id, access_token, refresh_token


def build_app_headers(access_token: str | None) -> dict[str, str] | None:
    if not access_token:
        return None
    return {
        "User-Agent": USER_AGENT,
        "Accept": "application/json, text/plain, */*",
        "Access-Token": access_token,
        "access-token": access_token,
        "accessToken": access_token,
        "accesstoken": access_token,
        "token": access_token,
        "Authorization": access_token,
        "Bearer": access_token,
    }


def probe_app_endpoints(client: ProbeClient, config: ProbeConfig) -> tuple[str | None, str | None]:
    user_id, access_token, _ = app_login(client, config)
    headers = build_app_headers(access_token)
    if not user_id or not headers:
        print("\n[app_probe] Missing user_id or access_token, skipping app probes.")
        return user_id, access_token

    response = client.request(
        "GET",
        f"http://www.aroma-link.com/v1/app/user/{user_id}?email={quote(config.username)}&language=EN",
        headers=headers,
    )
    print_response("app_user_profile", response)

    response = client.request(
        "GET",
        f"http://www.aroma-link.com/v1/app/device/listAll/{user_id}?pageNum=1&pageSize=10",
        headers=headers,
    )
    payload = print_response("app_device_list_all", response)
    if not config.device_id and payload:
        groups = find_nested_value(payload, {"data"})
        if isinstance(groups, list):
            for group in groups:
                if not isinstance(group, dict):
                    continue
                children = group.get("children")
                if not isinstance(children, list):
                    continue
                for child in children:
                    if isinstance(child, dict) and child.get("type") == "device" and child.get("id"):
                        config.device_id = str(child["id"])
                        break
                if config.device_id:
                    break

    if config.device_id:
        for is_open_page in (0, 1):
            response = client.request(
                "GET",
                f"http://www.aroma-link.com/v1/app/device/newWork/{config.device_id}?isOpenPage={is_open_page}&userId={user_id}",
                headers=headers,
            )
            print_response(f"app_new_work_isOpenPage_{is_open_page}", response)

        if config.switch_state:
            switch_body, switch_content_type = form_multipart(
                {
                    "deviceId": config.device_id,
                    "onOff": "1" if config.switch_state == "on" else "0",
                    "userId": user_id,
                }
            )
            response = client.request(
                "POST",
                "http://www.aroma-link.com/v1/app/data/newSwitch",
                headers={**headers, "Content-Type": switch_content_type},
                data=switch_body,
            )
            print_response(f"app_switch_{config.switch_state}", response)

    response = client.request(
        "GET",
        "http://www.aroma-link.com/v1/app/version/deviceType/config",
        headers=headers,
    )
    print_response("app_device_type_config", response)
    return user_id, access_token


def web_login(client: ProbeClient, config: ProbeConfig) -> bool:
    response = client.request("GET", "https://www.aroma-link.com/")
    print_response("web_home", response)

    headers = {
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "X-Requested-With": "XMLHttpRequest",
        "Origin": "https://www.aroma-link.com",
        "Referer": "https://www.aroma-link.com/",
        "User-Agent": USER_AGENT,
    }
    data = urlencode({"username": config.username, "password": config.password}).encode()
    response = client.request("POST", "https://www.aroma-link.com/login", headers=headers, data=data)
    print_response("web_login", response)
    return response.status == 200


def probe_web_endpoints(client: ProbeClient, config: ProbeConfig) -> None:
    if not web_login(client, config):
        print("\n[web_probe] Web login failed, skipping web probes.")
        return

    jsessionid = client.get_cookie("JSESSIONID")
    print(f"\n[web_auth_summary] jsessionid={mask_token(jsessionid)}")

    response = client.request("GET", "https://www.aroma-link.com/device/list")
    print_response("web_device_list_page", response)

    response = client.request(
        "GET",
        "https://www.aroma-link.com/device/list/v2?limit=10&offset=0&selectUserId=&groupId=&deviceName=&imei=&deviceNo=&workStatus=&continentId=&countryId=&areaId=&sort=&order=",
    )
    print_response("web_device_list_api", response)

    if not config.device_id:
        return

    headers = {
        "User-Agent": USER_AGENT,
        "X-Requested-With": "XMLHttpRequest",
        "Origin": "https://www.aroma-link.com",
        "Referer": f"https://www.aroma-link.com/device/command/{config.device_id}",
    }
    if jsessionid:
        headers["Cookie"] = f"languagecode=EN; JSESSIONID={jsessionid}"

    response = client.request(
        "GET",
        f"https://www.aroma-link.com/device/command/{config.device_id}",
        headers=headers,
    )
    print_response("web_device_command_page", response)

    response = client.request(
        "GET",
        f"https://www.aroma-link.com/device/deviceInfo/now/{config.device_id}?timeout=1000",
        headers=headers,
    )
    print_response("web_device_info_now", response)

    response = client.request(
        "GET",
        f"https://www.aroma-link.com/device/workTime/{config.device_id}?week=0",
        headers=headers,
    )
    print_response("web_work_time", response)


def main() -> None:
    args = parse_args()
    config = build_config(args)
    client = ProbeClient(verify_ssl=config.verify_ssl)

    if not args.skip_app:
        probe_app_endpoints(client, config)
    if not args.skip_web:
        probe_web_endpoints(client, config)


if __name__ == "__main__":
    main()
