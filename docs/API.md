# Aroma-Link API Reference

Documented from reverse-engineering `www.aroma-link.com`. Base URLs use `https://` for web endpoints and `http://` for app endpoints (the server redirects HTTP to HTTPS transparently).

All times in seconds unless noted. Device ID used in examples: `406387`, User ID: `175527`.

---

## Table of Contents

- [Authentication](#authentication)
  - [Web Session (JSESSIONID)](#web-session-jsessionid)
  - [App Token Flow](#app-token-flow)
- [Device State Endpoints](#device-state-endpoints)
  - [GET /device/list/v2 — Device List v2](#get-devicelistv2--device-list-v2)
  - [GET /device/list — Device List v1](#get-devicelist--device-list-v1)
  - [GET /device/deviceInfo/now/{id} — Real-time Info (Unreliable)](#get-devicedeviceinfonowid--real-time-info-unreliable)
  - [GET /v1/app/device/newWork/{id} — App Device State](#get-v1appdevicenewworkid--app-device-state)
- [Device Control Endpoints](#device-control-endpoints)
  - [POST /device/switch — Power On/Off and Exhaust Fan Control](#post-deviceswitch--power-onoff-and-exhaust-fan-control)
  - [POST /v1/app/data/newSwitch — App Power Switch](#post-v1appdatanewswitch--app-power-switch)
- [Schedule and Operation Mode Endpoints](#schedule-and-operation-mode-endpoints)
  - [GET /device/workTime/{id} — Work Time Settings](#get-deviceworktimeid--work-time-settings)
  - [POST /device/workSet — Set Scheduler](#post-deviceworkset--set-scheduler)
- [User Endpoints](#user-endpoints)
  - [GET /v1/app/user/{userId} — User Profile](#get-v1appuserid--user-profile)
- [Common Types & Enums](#common-types--enums)
- [Version Capability Matrix](#version-capability-matrix)
- [Known Issues & Observations](#known-issues--observations)

---

## Authentication

Two independent auth systems coexist. They are not interchangeable — web endpoints require JSESSIONID cookies, app endpoints require a JWT access token header.

### Web Session (JSESSIONID)

The website uses a cookie-based session. Login returns `code: 0` on success and sets an HttpOnly `JSESSIONID` cookie.

**Step 1 — GET the login page (optional but recommended for initial cookies)**

```
GET https://www.aroma-link.com/
```

No special headers needed. The server may set a preliminary session cookie.

**Step 2 — POST login**

```
POST https://www.aroma-link.com/login
Content-Type: application/x-www-form-urlencoded; charset=UTF-8
X-Requested-With: XMLHttpRequest
Referer: https://www.aroma-link.com/

username=smellyuser&password=SuperSecret123
```

> **Important**: Field names are `username` and `password` (lowercase). The earlier form used `userName` which returns a 500 HTML error page. Password is sent in **raw plaintext** — not hashed.

**Success response:**

```json
{"code": 0, "msg": "SUCCESS"}
```

Server sets cookie: `Set-Cookie: JSESSIONID=<uuid>; Path=/; HttpOnly`

**Failure response:**

```json
{"code": 500, "msg": "Incorrect account or password"}
```

Returns HTML 500 page body (not JSON). Check status + parse for `"code"` to distinguish.

**Using the session:**

All subsequent web requests include:

```
Cookie: languagecode=EN; JSESSIONID=<uuid>
User-Agent: Mozilla/5.0 ...
X-Requested-With: XMLHttpRequest
Referer: https://www.aroma-link.com/device/list
```

The `languagecode` cookie defaults to `EN`. Session cookies expire server-side (observed timeout ~15-30 min of inactivity). Re-login when endpoints return empty/non-JSON responses.

### App Token Flow

App authentication is a 3-step flow. The token endpoint accepts MD5-hashed passwords.

**Step 1 — newLogin**

```
POST http://www.aroma-link.com/v1/app/user/newLogin
Content-Type: multipart/form-data

userName=smellyuser&password=<md5_hash>
```

Password is the **MD5 hex digest** of the plaintext password (e.g., `SuperSecret123` → `<md5_hash>`).

**Success response:**

```json
{
  "code": 200,
  "msg": "OK",
  "data": {
    "isSuper": 0,
    "userId": 175527,
    "isShowDel": 0,
    "email": ""
  }
}
```

**Step 2 — Get access token**

```
POST http://www.aroma-link.com/v2/app/token
Content-Type: multipart/form-data

userName=smellyuser&password=<md5_hash>
```

**Success response:**

```json
{
  "code": 200,
  "msg": "OK",
  "data": {
    "accessToken": "eyJhbGciOiJIUzI1NiIsInppcCI6IkRFRiJ9...",
    "refreshToken": "eyJhbGciOiJIUzI1NiIsInppcCI6IkRFRiJ9...",
    "accessTokenValidity": 212800000,
    "refreshTokenValidity": 299200000,
    "id": 175527,
    "email": null,
    "resources": null
  }
}
```

The `accessToken` is a JWT with header `{"alg":"HS256","zip":"DEF"}` — payload is DEFLATE-compressed. Token validity values are in milliseconds (~212800s ≈ 2.47 days for access, ~299200s ≈ 3.46 days for refresh).

**Step 3 (optional) — Refresh token**

```
POST http://www.aroma-link.com/v2/app/refresh/token
Content-Type: multipart/form-data

refreshToken=<token_from_step_2>
```

Returns same shape as Step 2 with new tokens.

**Using app auth:**

Send the access token via header on subsequent requests:

```
Access-Token: <accessToken>
User-Agent: Mozilla/5.0 ...
```

> **WARNING**: App endpoints consistently return `code: 13002` ("Unauthorized or Token has expired") in testing, even immediately after token issuance. The JWT uses DEFLATE compression which may indicate a non-standard validation path on the server. Web auth (JSESSIONID) is the reliable authentication method.

---

## Device State Endpoints

### GET /device/list/v2 — Device List v2

**Primary state source.** Returns all devices for the authenticated user. Most fields, but **no count fields** (`runCount`, `airPumpCount` absent).

```
GET https://www.aroma-link.com/device/list/v2?limit=10&offset=0&selectUserId=&groupId=&deviceName=&imei=&deviceNo=&workStatus=&continentId=&countryId=&areaId=&sort=&order=
Cookie: languagecode=EN; JSESSIONID=<uuid>
```

**Response:**

```json
{
  "rows": [
    {
      "deviceId": 406387,
      "deviceName": "Gemini",
      "typeCode": "A6/Pro300",
      "virtualImei": "110083185212163",
      "deviceNo": "289C6E53B9D4",
      "userId": 175527,
      "username": "smellyuser",
      "groupId": 167001,
      "groupName": "default group",
      "continentName": "North America",
      "countryName": "Canada",
      "areaName": "Toronto",
      "activeTime": null,
      "netType": "WIFI",
      "version": "V1.0.20201213",
      "onlineStatus": 1,
      "onlineErrorStatus": 0,
      "workStatus": 0,
      "workInfo": "Sunday:\r\nFirst:00:00-23:59  W 60/ P 90 A Level\r\n...",
      "localTime": "2026-06-10 15:31:03",
      "oilCount": 0,
      "remainOil": null,
      "setCount": 31,
      "salesCount": 0,
      "errorCount": 0,
      "isLock": 0,
      "isError": 0,
      "deviceType": "01",
      "timeZone": "UTC-4",
      "errorDesc": null,
      "email": "",
      "type": 0,
      "hasWeight": 0,
      "ojiShowType": 0,
      "hasOjiWarn": 0
    }
  ]
}
```

**Key fields:**

| Field | Type | Description |
|---|---|---|
| `workStatus` | int | 0=Off/Idle, 1=Diffusing (active), 2=Paused (between cycles) |
| `onlineStatus` | int | 0=Offline, 1=Online |
| `localTime` | string | Device-local timestamp `YYYY-MM-DD HH:MM:SS` |
| `workInfo` | string | Human-readable schedule summary per day |
| `oilCount` | int | Oil level indicator. 0 on models without oil sensor (A6/Pro300) |
| `hasWeight` | int | 1 if device has a weight/oil sensor, 0 otherwise |

**Filtering:** Query params allow filtering by `workStatus`, `groupId`, `deviceName`, etc. Empty values mean "no filter".

### GET /device/list — Device List v1

Legacy endpoint. Fewer descriptive fields but **includes count fields** (`runCount`, `airPumpCount`) that V2 omits.

```
GET https://www.aroma-link.com/device/list?limit=10&offset=0
Cookie: languagecode=EN; JSESSIONID=<uuid>
```

**Response:**

```json
{
  "rows": [
    {
      "deviceId": 406387,
      "deviceName": "Gemini",
      "username": "smellyuser",
      "deviceType": "01",
      "version": "V1.0.20201213",
      "timeZone": "UTC-4",
      "localTime": null,
      "continentId": 118,
      "countryId": 688,
      "areaId": 11618,
      "onlineStatus": 1,
      "workStatus": 0,
      "deviceNo": "289C6E53B9D4",
      "activeTime": null,
      "groupName": "default group",
      "groupId": 167001,
      "runCount": 1569411,
      "airPumpCount": 8531,
      "oilCount": 0,
      "remainOil": null,
      "typeId": null,
      "virtualImei": "110083185212163",
      "isLock": 0,
      "userId": 175527,
      "netType": "WIFI",
      "hasFan": null,
      "hasLamp": null,
      "hasWeight": null,
      "hasBattery": null,
      "hasPump": null,
      "typeCode": "A6/Pro300",
      "setCount": 31,
      "salesCount": 0,
      "errorCount": 0,
      "workInfo": null,
      "statisticsUpdateTime": 1781119858000,
      "useMode": 0,
      "deviceArea": 0,
      "isError": 0
    }
  ]
}
```

**Count fields:**

| Field | Type | Description | Verified Behavior |
|---|---|---|---|
| `runCount` | int | Accumulated work time in **seconds** | +10 after a single 10s diffusion cycle |
| `airPumpCount` | int | Number of pump activations (diffusions) | +1 per completed diffusion cycle |

> **Important**: `runCount` is NOT an activation counter. It tracks total seconds the device has been in work/diffusing state across its lifetime. A value of 1,569,411 = ~26 hours of cumulative operation.

### GET /device/deviceInfo/now/{id} — Real-time Info (Unreliable)

Returns `code: 503` consistently. Likely deprecated or broken server-side. Do not rely on this endpoint.

```
GET https://www.aroma-link.com/device/deviceInfo/now/406387
Cookie: languagecode=EN; JSESSIONID=<uuid>
```

**Response:** `{"code": 503, "msg": "OK"}` — no data payload.

### GET /v1/app/device/newWork/{id} — App Device State

App-only endpoint for device state. Returns richer real-time data including `powerState`, `pumpCount`. Requires valid app access token (unreliable in testing).

```
GET http://www.aroma-link.com/v1/app/device/newWork/406387?isOpenPage=0&userId=175527
Access-Token: <jwt>
```

The `isOpenPage` parameter controls response detail level:
- `0` — basic state
- `1` — enriched with additional fields (`powerState`, detailed schedule)

**Expected fields (from plugin parsing logic, not confirmed live):**
`powerState`, `workStatus`, `pumpCount`, `onOff`, `switchStatus`, `isOpen`, `isOn`, `workRemainTime`, `pauseRemainTime`

---

## Device Control Endpoints

### POST /device/switch — Power On/Off and Exhaust Fan Control

Reliable web endpoint. Sends commands to control device power (oil pumping) and the exhaust fan. Returns immediately; state changes propagate asynchronously (device reporting is delayed/stale).

```
POST https://www.aroma-link.com/device/switch
Content-Type: application/x-www-form-urlencoded; charset=UTF-8
Cookie: languagecode=EN; JSESSIONID=<uuid>
X-Requested-With: XMLHttpRequest
Referer: https://www.aroma-link.com/device/command/406387

deviceId=406387&onOff=1&fan=1
```

**Parameters:**

| Param | Type | Values | Description |
|---|---|---|---|
| `deviceId` | int | — | Target device ID |
| `onOff` | int | 0 or 1 | 0=Power Off, 1=Power On (pumps oil when active) |
| `fan` | int | 0 or 1 | 0=Exhaust fan off, 1=Exhaust fan on |

**Success response:** `{"code": 200, "msg": "OK"}`

**How it works:**

- `onOff=1` powers the device and starts pumping oil using configured work/pause durations. Requires `workDuration > 0` and `pauseDuration > 0`.
- `fan=1` turns on the exhaust fan to accelerate diffused scent out of the unit — this is purely for better scent distribution, not diffusion itself.
- Both parameters are independent: you can pump oil without the fan, run the fan without pumping, or use both together.

**Example flow:**
```
# Power on device (pumps oil with configured durations)
POST /device/switch?deviceId=406387&onOff=1

# Turn on exhaust fan for better scent distribution
POST /device/switch?deviceId=406387&fan=1

# Turn off exhaust fan only (keep pumping)
POST /device/switch?deviceId=406387&fan=0

# Power off completely
POST /device/switch?deviceId=406387&onOff=0
```

**State reporting:** Device state updates are delayed and may not reflect real-time operation. `runCount` increases only after completed work cycles, not during active diffusion.

### POST /v1/app/data/newSwitch — App Power Switch

App-only switch endpoint. Returns `code: 13002` in testing due to app auth issues.

```
POST http://www.aroma-link.com/v1/app/data/newSwitch
Content-Type: multipart/form-data
Access-Token: <jwt>

deviceId=406387&onOff=1&userId=175527
```

---

## Schedule and Operation Mode Endpoints

The device has three independent features:

1. **Power (`onOff`)** — Controls oil pumping. When `onOff=1`, the device pumps oil using configured work/pause durations. Requires `workDuration > 0` and `pauseDuration > 0`.
2. **Exhaust Fan (`fan`)** — Physical fan that accelerates diffused scent out of the unit for better distribution. Independent of pumping.
3. **Schedules** — Weekly automation that controls when to pump oil (`onOff=1`/`onOff=0`) and applies work/pause durations based on active time slots.

A schedule slot is NOT just "when to run." When a slot becomes active, it:
- Sets the power state (`onOff=1` or `onOff=0`)
- Applies its configured work/pause durations

Without an active schedule, you can still manually control power via `/device/switch?onOff=1`. The exhaust fan is always independent and controlled separately.

### GET /device/workTime/{id} — Work Time Settings

Returns time slot configuration for a given day of week. Each device has 5 configurable slots per day, only one can be enabled at a time.

```
GET https://www.aroma-link.com/device/workTime/406387?week=0
Cookie: languagecode=EN; JSESSIONID=<uuid>
```

**Parameters:**

| Param | Type | Values | Description |
|---|---|---|---|
| `week` | int | 0-6 | Day of week (0=Sunday, 1=Monday, ..., 6=Saturday) |

**Response:**

```json
{
  "code": 200,
  "msg": "OK",
  "data": [
    {
      "settingId": 419605,
      "deviceId": 406387,
      "weekDay": 0,
      "startHour": "00:00",
      "endHour": "23:59",
      "workSec": 60,
      "pauseSec": 90,
      "consistenceLevel": 1,
      "createTime": 1781118798890,
      "updateTime": null,
      "enabled": 1,
      "dataId": 0,
      "createUserId": null,
      "updateUserId": null,
      "workInfo": "First:00:00-23:59  W 60/ P 90 A Level\r\n",
      "condition1": "08005036d91f90e74ff124a0def37ad8",
      "manyPumpEnabled": null,
      "selectPump": null
    },
    {
      "settingId": 419607,
      "startHour": "00:00",
      "endHour": "24:00",
      "workSec": 10,
      "pauseSec": 900,
      "enabled": 0,
      ...
    }
  ]
}
```

**Slot fields:**

| Field | Type | Description |
|---|---|---|
| `enabled` | int | 1=active slot, 0=disabled placeholder |
| `workSec` | int | Work duration in seconds — how long to pump oil per cycle when active |
| `pauseSec` | int | Pause duration in seconds — gap between pumping cycles |
| `startHour` / `endHour` | string | Time window for this slot (`HH:MM`) |
| `consistenceLevel` | int | Concentration level (1=A Level, 2=B Level, etc.) |

> **Important**: These durations control oil pumping. If both are > 0 and the device is powered on (`onOff=1`), it will pump scent for `workSec`, pause for `pauseSec`, and repeat.

Only one slot per day should have `enabled=1`. The remaining 4 slots are disabled placeholders.

### POST /device/workSet — Set Scheduler

Sets the work/pause schedule for all days. Sends a full payload with 5 time slots per day across all 7 days (though only the first enabled slot matters).

```
POST https://www.aroma-link.com/device/workSet
Content-Type: application/json;charset=UTF-8
Cookie: languagecode=EN; JSESSIONID=<uuid>
X-Requested-With: XMLHttpRequest
Referer: https://www.aroma-link.com/device/command/406387
```

**Request body:**

```json
{
  "deviceId": "406387",
  "type": "workTime",
  "week": [0, 1, 2, 3, 4, 5, 6],
  "workTimeList": [
    {
      "startTime": "00:00",
      "endTime": "23:59",
      "enabled": 1,
      "consistenceLevel": "1",
      "workDuration": "60",
      "pauseDuration": "90"
    },
    {
      "startTime": "00:00",
      "endTime": "24:00",
      "enabled": 0,
      "consistenceLevel": "1",
      "workDuration": "10",
      "pauseDuration": "90"
    },
    {
      "startTime": "00:00",
      "endTime": "24:00",
      "enabled": 0,
      "consistenceLevel": "1",
      "workDuration": "10",
      "pauseDuration": "90"
    },
    {
      "startTime": "00:00",
      "endTime": "24:00",
      "enabled": 0,
      "consistenceLevel": "1",
      "workDuration": "10",
      "pauseDuration": "90"
    },
    {
      "startTime": "00:00",
      "endTime": "24:00",
      "enabled": 0,
      "consistenceLevel": "1",
      "workDuration": "10",
      "pauseDuration": "90"
    }
  ]
}
```

**Parameters:**

| Field | Type | Description |
|---|---|---|
| `deviceId` | string | Target device ID (sent as string) |
| `type` | string | Always `"workTime"` |
| `week` | int[] | Days of week to apply: `[0..6]` for all days |
| `workTimeList` | array | Exactly 5 slot objects. Only the first with `enabled=1` takes effect per day |

**Per-slot fields:**

| Field | Type | Description |
|---|---|---|
| `startTime` / `endTime` | string | Time window (`HH:MM`) — when this schedule is active |
| `enabled` | int | 1 or 0 |
| `consistenceLevel` | string | Concentration level as string `"1"`-`"4"` |
| `workDuration` | string | Work cycle duration in seconds (sent as **string**) — applied when slot is active |
| `pauseDuration` | string | Pause duration in seconds (sent as **string**) — applied when slot is active |

**Success response:** `{"code": 200, "msg": ""}`

> When a schedule slot becomes active, it automatically sets `onOff=1`, applies its work/pause durations, and starts oil pumping. All slots must be disabled (`enabled=0`) to stop scheduled operation — otherwise the device will auto-toggle power based on time windows.

---

## User Endpoints

### GET /v1/app/user/{userId} — User Profile

App-only user profile lookup. Requires valid app token (unreliable).

```
GET http://www.aroma-link.com/v1/app/user/175527?email=smellyuser&language=EN
Access-Token: <jwt>
```

---

## Common Types & Enums

### workStatus

| Value | Meaning | Behavior |
|---|---|---|
| `0` | Off / Idle | Device is powered off or not actively cycling |
| `1` | Diffusing | Pump is active, currently diffusing oil |
| `2` | Paused | Between work cycles — device will resume after `pauseSec` elapses |

Cycle progression when power is on and durations are set: `0 → 1 (workSec) → 2 (pauseSec) → 1 (workSec) → ...`

> **Note**: State reporting is delayed. The API may return stale values even while the device is actively cycling. Use `runCount` changes between polls to confirm actual operation.

### onlineStatus

| Value | Meaning |
|---|---|
| `0` | Device offline / unreachable |
| `1` | Device online and reporting |

### consistenceLevel (Concentration)

| Value | Label |
|---|---|
| `"1"` | A Level (lightest) |
| `"2"` | B Level |
| `"3"` | C Level |
| `"4"` | D Level (strongest) |

### Response Codes

| Code | Meaning | Context |
|---|---|---|
| `0` | Success | Web login only |
| `200` | OK | All other web + app endpoints |
| `503` | Server error | `/device/deviceInfo/now/*` (endpoint broken) |
| `13002` | Unauthorized / Token expired | App endpoints when token is invalid |

---

## Version Capability Matrix

| Capability | V1 List | V2 List | App newWork | Web Switch | App Switch | WorkTime GET | WorkSet POST |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| Device basic info (name, type, online) | Yes | Yes | Yes* | — | — | — | — |
| `workStatus` (0/1/2) | Yes | Yes | Yes* | — | — | — | — |
| `runCount` (accumulated work seconds) | **Yes** | No | Maybe* | — | — | — | — |
| `airPumpCount` (pump activations) | **Yes** | No | Maybe* | — | — | — | — |
| Schedule info (`workInfo`) | No | Yes | Yes* | — | — | Yes | — |
| Power control | — | — | — | Yes | Yes† | — | — |
| Scheduler read | — | — | — | — | — | Yes | — |
| Scheduler write | — | — | — | — | — | — | Yes |

\* App endpoints not confirmed working (return 13002 in testing)
† App switch returns 13002; use web `/device/switch` instead

**Recommendation**: Use V2 for device listing + state polling, V1 only when count fields are needed. Control exclusively through web endpoints (`/device/switch`, `/device/workSet`).

---

## Known Issues & Observations

### App Auth Token Rejection
All app endpoints return `code: 13002` ("Unauthorized or Token has expired") immediately after token issuance, despite the JWT being freshly minted. The JWT uses DEFLATE-compressed payload (`"zip":"DEF"` in header) which may indicate a non-standard validation path. **Workaround**: use web JSESSIONID auth exclusively.

### Switch Command Latency
After sending `POST /device/switch?onOff=1`, the device takes 15-20 seconds before `workStatus` transitions from 0 to 1. This is not a network delay — it's device-side acknowledgment time. Polling at 60s intervals may miss the initial transition entirely if polling aligns unlucky.

### State Reporting Cadence
- `workStatus` updates near-real-time (observed cycling between 1↔2 within seconds)
- `runCount` and `airPumpCount` only update when the device pushes data upstream on its own schedule — cannot be forced via API
- A device may show `onlineStatus=1` while serving stale cached state (`statisticsUpdateTime` hours old). The mobile app uses a different communication path that can trigger fresh reporting.

### Exhaust Fan Control
The fan parameter controls a physical exhaust fan for scent distribution, independent of oil pumping:
- `onOff=1` powers the device and starts pumping oil (requires work/pause durations > 0)
- `fan=1` turns on the exhaust fan to accelerate diffused scent out of the unit
- Both are independent — you can pump without fan, run fan without pumping, or use both

### Schedules vs Manual Control
Schedules and manual power control are separate features:
- **Manual** (`onOff=1`/`onOff=0`) — controlled directly via `/device/switch`, starts/stops oil pumping immediately
- **Schedules** — weekly automation that auto-toggles `onOff=1`/`onOff=0` and applies work/pause durations when time slots are active
- A schedule is NOT just "when to run" — it controls power state AND sets work/pause values

### workStatus = 2 (Paused) Ambiguity
When `workStatus=2`, the device is between diffusion cycles but still powered. State reporting is delayed and may not reflect real-time operation — use `runCount` changes between polls to confirm actual cycling activity.

### runCount is Seconds, Not Activations
Despite the name, `runCount` accumulates seconds of work time, not number of activations. After a 10s diffusion cycle: `runCount += 10`. Use `airPumpCount` for actual pump activation counts (+1 per cycle).

### deviceInfo/now is Dead
`GET /device/deviceInfo/now/{id}` returns HTTP 200 with `code: 503` and no data. This endpoint should not be used as a state source.

### Oil Count Unreliable on Some Models
Devices without oil sensors (A6/Pro300 has `hasWeight=0`) always report `oilCount=0`. Do not use this field to detect low oil on all device types.

### Session Cookie Expiry
JSESSIONID cookies expire after a period of inactivity (~15-30 min observed). When endpoints return empty responses or non-JSON content, the session has likely expired and requires re-login.
