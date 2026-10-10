"""
mt_xpr_webservice.py
====================

Comprehensive Python client for the Mettler Toledo XPR / XSR balance
Web Service (WSDL V03). Wraps 36 of the 61 operations exposed by the
balance, covering 8 of the 13 services. The remaining services
(Authentication, RoutineTest, ToleranceProfile, Feeder, UserInteraction)
are intentionally omitted as they are rarely useful in academic SDL
contexts. The pattern below makes it trivial to add them later if
needed ??every method is 5-10 lines.

Services covered
----------------
| Service                     | Ops covered | Used for                       |
|-----------------------------|-------------|---------------------------------|
| ISessionService             |     3 / 3   | session lifecycle              |
| INotificationService        |     1 / 1   | event polling                  |
| IWeighingService            |     6 / 7   | zero, tare, get weight, units  |
| IWeighingTaskService        |    10 / 14  | methods, tasks, target/tol     |
| IDosingAutomationService    |     4 / 5   | Quantos dosing automation      |
| IBasicService               |     7 / 9   | device info, beep, display     |
| IDraftShieldsService        |     2 / 2   | auto draft shield doors        |
| IAdjustmentService          |     3 / 3   | internal weight calibration    |
| total                       |   36 / 61   |                                |

Architecture
------------
- `_SoapClient` does raw HTTP+XML transport (uses `requests`).
- `decrypt_session_id` mirrors the .NET CryptographyHelper.cs exactly
  (PBKDF2-HMAC-SHA1 1000 iter -> 32-byte key, AES-256-ECB-PKCS7).
- `XprBalance` is the public class. All operations are flat methods.
  Internally organized into sections by service for readability.
- Data classes: `DosingJob`, `DosingResult`, `WeightWithUnit`, `DeviceInfo`.
- `Robot` Protocol + `HumanRobot` fallback for the dosing event loop.

Dependencies
------------
    pip install requests pycryptodome

Usage (minimal)
---------------
    from mt_xpr_webservice import XprBalance, DosingJob, HumanRobot

    bal = XprBalance("192.168.0.68", port=81, client_password="...")
    with bal.session():
        bal.zero()
        bal.start_automated_dosing_method()
        bal.run_dosing_jobs(
            [DosingJob("Sugar", "Vial1", 200, "Milligram")],
            robot=HumanRobot(),
        )

See examples/ folder for 10 runnable demos covering everything from a
session ping all the way to a full SDL cycle with UR robot integration.

Author: drafted for J. Na lab @ Ewha, April 2026
License: MIT (use freely, no warranty)
"""

from __future__ import annotations

import base64
import hashlib
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Iterator, List, Optional, Protocol
from xml.etree import ElementTree as ET

import requests
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad

# ===========================================================================
# 1) Crypto helper ??direct port of CryptographyHelper.cs
# ===========================================================================

def decrypt_session_id(client_password: str, encrypted_b64: str, salt_b64: str) -> str:
    """Decrypt the session id returned by OpenSession.

    Mirrors .NET Rfc2898DeriveBytes(password, salt, 1000) -> 32-byte key,
    then RijndaelManaged AES-256-ECB-PKCS7 decryption."""
    encrypted = base64.b64decode(encrypted_b64)
    salt = base64.b64decode(salt_b64)
    key = hashlib.pbkdf2_hmac("sha1", client_password.encode("utf-8"), salt, 1000, dklen=32)
    cipher = AES.new(key, AES.MODE_ECB)
    plain = unpad(cipher.decrypt(encrypted), AES.block_size)
    return plain.decode("utf-8")


# ===========================================================================
# 2) Data classes
# ===========================================================================

@dataclass
class WeightWithUnit:
    """Mirrors WeightWithUnit complex type from the WSDL."""
    value: float
    unit: str = "Gram"   # "Gram", "Milligram", "Microgram", "Kilogram", "Carat", "Ounce", ...

    def to_xml(self, tag: str = "v03:Weight") -> str:
        return (f"<{tag}>"
                f"<v03:Value>{self.value}</v03:Value>"
                f"<v03:Unit>{self.unit}</v03:Unit>"
                f"</{tag}>")


@dataclass
class DosingJob:
    """Mirrors the WSDL DosingJob complex type.
    Per the CHM: VialName 0..32 chars, SubstanceName 0..20 chars."""
    substance_name: str
    vial_name: str
    target_value: float
    target_unit: str = "Milligram"
    lower_tolerance: Optional[float] = None # USE Tolerance around -1 to +1 (or 0.5/-0.5) .............................................................
    upper_tolerance: Optional[float] = None


@dataclass
class DosingResult:
    job_index: int
    substance_name: str
    vial_name: str
    target_value: float
    target_unit: str
    actual_value: Optional[float] = None
    actual_unit: Optional[str] = None
    success: bool = False
    duration_s: Optional[float] = None
    error: Optional[str] = None


@dataclass
class DeviceInfo:
    """Mirrors GetDeviceInformationResponse fields."""
    serial_number: Optional[str] = None
    type_designation: Optional[str] = None
    software_version: Optional[str] = None
    hardware_version: Optional[str] = None
    extra: dict = field(default_factory=dict)


@dataclass
class WeightSample:
    """Mirrors WeightSample complex type."""
    net_value: Optional[float] = None
    net_unit:  Optional[str]   = None
    gross_value: Optional[float] = None
    gross_unit:  Optional[str]   = None
    tare_value:  Optional[float] = None
    tare_unit:   Optional[str]   = None
    stable: Optional[bool] = None
    status: Optional[str] = None


# ===========================================================================
# 3) Robot Protocol ??for the dosing automation event loop
# ===========================================================================

class Robot(Protocol):
    """Minimal interface a physical robot must implement to drive dosing."""
    def place_vial(self, vial_name: str) -> None: ...
    def remove_vial(self, vial_name: str) -> None: ...
    def place_dosing_head(self, head_name: str) -> None: ...
    def remove_dosing_head(self, head_name: str) -> None: ...


class HumanRobot:
    """Fallback 'robot' that prompts the operator at the terminal.
    Use this for first-time integration tests before wiring up the real robot."""
    def place_vial(self, vial_name: str) -> None:
        input(f"  >> Please PLACE vial '{vial_name}' on the balance, then press Enter...")
    def remove_vial(self, vial_name: str) -> None:
        input(f"  >> Please REMOVE vial '{vial_name}', then press Enter...")
    def place_dosing_head(self, head_name: str) -> None:
        input(f"  >> Please PLACE dosing head '{head_name}', then press Enter...")
    def remove_dosing_head(self, head_name: str) -> None:
        input(f"  >> Please REMOVE dosing head '{head_name}', then press Enter...")


# ===========================================================================
# 4) SOAP transport
# ===========================================================================

NS = {
    "s":   "http://schemas.xmlsoap.org/soap/envelope/",
    "v03": "http://MT/Laboratory/Balance/XprXsr/V03",
    "xsi": "http://www.w3.org/2001/XMLSchema-instance",
}
ET.register_namespace("s",   NS["s"])
ET.register_namespace("v03", NS["v03"])

NS_BASE = "http://MT/Laboratory/Balance/XprXsr/V03"
URL_PATH = "/MT/Laboratory/Balance/XprXsr/V03"   # path component on the balance HTTP server


class _SoapClient:
    """Hand-crafted SOAP 1.1 client. We use raw envelopes (not zeep) because
    the WCF-style WSDL pulls in dozens of XSDs and zeep tends to choke on it,
    while raw SOAP gives full visibility for debugging."""

    def __init__(self, base_url: str, timeout: float = 30.0):
        self.base_url = base_url.rstrip("/") + "/"
        self.timeout = timeout
        self._session = requests.Session()

    def call(self, service_iface: str, operation: str, inner_body_xml: str) -> ET.Element:
        """Send a SOAP request and return the parsed Body element.

        Args:
            service_iface: e.g. "IWeighingService"
            operation:     e.g. "Zero"  (used to build SOAPAction header)
            inner_body_xml: the XML inside <s:Body>...</s:Body>, including
                            the <v03:XxxRequest> wrapper.
        """
        envelope = (
            '<?xml version="1.0" encoding="utf-8"?>'
            '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
                       'xmlns:v03="http://MT/Laboratory/Balance/XprXsr/V03">'
            '<s:Header/>'
            '<s:Body>' + inner_body_xml + '</s:Body>'
            '</s:Envelope>'
        )
        url = self.base_url + service_iface
        headers = {
            "Content-Type": "text/xml; charset=utf-8",
            "SOAPAction":   f'"{NS_BASE}/{service_iface}/{operation}"',
        }
        resp = self._session.post(url, data=envelope.encode("utf-8"),
                                  headers=headers, timeout=self.timeout)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        body = root.find("s:Body", NS)
        if body is None:
            raise RuntimeError("Malformed SOAP response: no Body element")
        fault = body.find("s:Fault", NS)
        if fault is not None:
            reason = "".join(fault.itertext()).strip()
            raise RuntimeError(f"SOAP Fault from balance: {reason}")
        return body


def _find_text(parent: ET.Element, tag: str) -> Optional[str]:
    """Find first descendant element by local name and return its text."""
    el = parent.find(f".//v03:{tag}", NS)
    return el.text if el is not None else None


def _find_float(parent: ET.Element, tag: str) -> Optional[float]:
    txt = _find_text(parent, tag)
    return float(txt) if txt is not None else None


# ===========================================================================
# 5) XprBalance ??high-level client
# ===========================================================================

class XprBalance:
    """Comprehensive Python client for an XPR/XSR balance.

    All operations require an open session except for `open_session` itself
    and `close_session`. Use the `session()` context manager for safety.
    """

    def __init__(self, host: str, port: int = 81, client_password: str = "",
                 use_https: bool = False, timeout: float = 30.0):
        scheme = "https" if use_https else "http"
        self.base_url = f"{scheme}://{host}:{port}{URL_PATH}/"
        self.client_password = client_password
        self._soap = _SoapClient(self.base_url, timeout=timeout)
        self.session_id: Optional[str] = None
        # state mirrors for last-observed values
        self.last_actual_weight_value: Optional[float] = None
        self.last_actual_weight_unit:  Optional[str]   = None

    # -----------------------------------------------------------------------
    # Helper for boilerplate-free SOAP calls
    # -----------------------------------------------------------------------

    def _call(self, service: str, operation: str, *,
              params: str = "", needs_session: bool = True) -> ET.Element:
        """Build standard <v03:{Op}Request><v03:SessionId>...</...>{params}</...>
        and call the balance. Returns the parsed body."""
        if needs_session and not self.session_id:
            raise RuntimeError("No active session. Call open_session() first.")
        sid_xml = f"<v03:SessionId>{self.session_id}</v03:SessionId>" if needs_session else ""
        body = f"<v03:{operation}Request>{sid_xml}{params}</v03:{operation}Request>"
        return self._soap.call(service, operation, body)

    def _check_outcome(self, resp: ET.Element, op_name: str) -> None:
        """Some operations return an <Outcome>Success/Failure</Outcome> field
        instead of throwing a SOAP fault. Raise if it's not Success."""
        outcome = _find_text(resp, "Outcome")
        if outcome and outcome != "Success":
            err = _find_text(resp, "ErrorMessage") or "(no error message)"
            raise RuntimeError(f"{op_name} failed: {outcome} ??{err}")

    # =======================================================================
    # ISessionService (3/3)
    # =======================================================================

    def open_session(self) -> str:
        """Open a SOAP session. Returns the (decrypted) session id."""
        resp = self._soap.call("ISessionService", "OpenSession", "<v03:OpenSessionRequest/>")
        enc = _find_text(resp, "SessionId")
        salt = _find_text(resp, "Salt")
        if not enc or not salt:
            raise RuntimeError("OpenSession response missing SessionId or Salt")
        self.session_id = decrypt_session_id(self.client_password, enc, salt)
        return self.session_id

    def close_session(self) -> None:
        """Close the current session. Idempotent."""
        if not self.session_id:
            return
        try:
            self._call("ISessionService", "CloseSession")
        finally:
            self.session_id = None

    def cancel(self, cancel_type: str = "All") -> None:
        """Cancel pending commands. cancel_type ??{'All', 'Command', 'Notification'}."""
        params = f"<v03:CancelType>{cancel_type}</v03:CancelType>"
        self._call("ISessionService", "Cancel", params=params)

    @contextmanager
    def session(self) -> Iterator["XprBalance"]:
        """Context manager that opens, yields, then guarantees CancelAll + close."""
        self.open_session()
        try:
            yield self
        finally:
            try:
                self.cancel("All")
            except Exception:
                pass
            self.close_session()

    # =======================================================================
    # INotificationService (1/1)
    # =======================================================================

    def get_notifications(self, timeout_ms: int = 500) -> List[ET.Element]:
        """Long-poll for notifications. Returns list of Notification elements
        (raw XML ??caller is expected to dispatch on type)."""
        params = f"<v03:TimeoutInMs>{timeout_ms}</v03:TimeoutInMs>"
        resp = self._call("INotificationService", "GetNotifications", params=params)
        # Find all notification types (not just v03:Notification)
        # Real balance sends: DosingAutomationActionAsyncNotification, etc.
        notifications_elem = resp.find(".//v03:Notifications", NS)
        if notifications_elem is None:
            return []
        return list(notifications_elem)

    # =======================================================================
    # IWeighingService (6/7)
    # =======================================================================

    def zero(self) -> None:
        """Zero the balance (set current load as new zero point)."""
        resp = self._call("IWeighingService", "Zero")
        self._check_outcome(resp, "Zero")

    def tare(self) -> None:
        """Tare the balance (set current load as new tare)."""
        resp = self._call("IWeighingService", "Tare")
        self._check_outcome(resp, "Tare")

    def set_pretare_value(self, weight: WeightWithUnit) -> None:
        """Apply a numeric pretare value (e.g. known vial weight)."""
        params = weight.to_xml("v03:PretareValue")
        resp = self._call("IWeighingService", "SetPretareValue", params=params)
        self._check_outcome(resp, "SetPretareValue")

    def clear_pretare_value(self) -> None:
        resp = self._call("IWeighingService", "ClearPretareValue")
        self._check_outcome(resp, "ClearPretareValue")

    def get_weight(self, wait_for_stable: bool = True) -> WeightSample:
        """Synchronous single-shot weight read. Returns a WeightSample."""
        params = f"<v03:WaitForStable>{'true' if wait_for_stable else 'false'}</v03:WaitForStable>"
        resp = self._call("IWeighingService", "GetWeight", params=params)
        self._check_outcome(resp, "GetWeight")
        return self._parse_weight_sample(resp)

    def get_weight_async(self, wait_for_stable: bool = True) -> None:
        """Async weight read. Result arrives via GetNotifications as a
        GetWeightAsyncNotification element. Use get_notifications() to receive."""
        params = f"<v03:WaitForStable>{'true' if wait_for_stable else 'false'}</v03:WaitForStable>"
        self._call("IWeighingService", "GetWeightAsync", params=params)

    @staticmethod
    def _parse_weight_sample(resp: ET.Element) -> WeightSample:
        ws = WeightSample()
        for which, val_attr, unit_attr in [
            ("NetWeight",   "net_value",   "net_unit"),
            ("GrossWeight", "gross_value", "gross_unit"),
            ("TareWeight",  "tare_value",  "tare_unit"),
        ]:
            v = resp.find(f".//v03:{which}/v03:Value", NS)
            u = resp.find(f".//v03:{which}/v03:Unit",  NS)
            if v is not None: setattr(ws, val_attr, float(v.text))
            if u is not None: setattr(ws, unit_attr, u.text)
        stable = _find_text(resp, "Stable")
        if stable: ws.stable = (stable.lower() == "true")
        ws.status = _find_text(resp, "Status")
        return ws

    # =======================================================================
    # IWeighingTaskService (10/14)
    # =======================================================================

    def get_list_of_methods(self) -> List[dict]:
        """Returns list of dicts with keys 'name' and 'method_type'."""
        resp = self._call("IWeighingTaskService", "GetListOfMethods")
        out = []
        for m in resp.findall(".//v03:MethodDescription", NS):
            name = m.find("v03:Name", NS)
            mtype = m.find("v03:MethodType", NS)
            out.append({
                "name": name.text if name is not None else None,
                "method_type": mtype.text if mtype is not None else None,
            })
        return out

    def start_task(self, method_name: str) -> None:
        """Start a weighing/dosing task by method name (must already exist on terminal)."""
        params = f"<v03:MethodName>{method_name}</v03:MethodName>"
        resp = self._call("IWeighingTaskService", "StartTask", params=params)
        self._check_outcome(resp, "StartTask")

    def cancel_current_task(self) -> None:
        resp = self._call("IWeighingTaskService", "CancelCurrentTask")
        self._check_outcome(resp, "CancelCurrentTask")

    def complete_current_task(self) -> None:
        resp = self._call("IWeighingTaskService", "CompleteCurrentTask")
        self._check_outcome(resp, "CompleteCurrentTask")

    def resume_task(self) -> None:
        resp = self._call("IWeighingTaskService", "ResumeTask")
        self._check_outcome(resp, "ResumeTask")

    def set_target_value_and_tolerances(self, target: WeightWithUnit,
                                         lower: WeightWithUnit,
                                         upper: WeightWithUnit) -> None:
        """Set target weight + tolerance window for the active task. RUNTIME-DYNAMIC.
        This is the call that makes Bayesian-opt-driven SDL workflows possible."""
        params = (target.to_xml("v03:TargetWeight")
                  + lower.to_xml("v03:LowerTolerance")
                  + upper.to_xml("v03:UpperTolerance"))
        resp = self._call("IWeighingTaskService", "SetTargetValueAndTolerances", params=params)
        self._check_outcome(resp, "SetTargetValueAndTolerances")

    def get_target_value_and_tolerances(self) -> dict:
        resp = self._call("IWeighingTaskService", "GetTargetValueAndTolerances")
        return {
            "target": (_find_float(resp, "Value"), _find_text(resp, "Unit")),
        }

    def clear_target_value_and_tolerances(self) -> None:
        resp = self._call("IWeighingTaskService", "ClearTargetValueAndTolerances")
        self._check_outcome(resp, "ClearTargetValueAndTolerances")

    def add_to_protocol(self) -> dict:
        """Record current weight as a result row in the active task.
        Returns a dict with keys 'net_value', 'net_unit', 'alibi_id'."""
        resp = self._call("IWeighingTaskService", "AddToProtocol")
        self._check_outcome(resp, "AddToProtocol")
        return {
            "net_value": _find_float(resp, "Value"),
            "net_unit":  _find_text(resp, "Unit"),
            "alibi_id":  _find_text(resp, "AlibiId"),
        }

    def set_unit(self, unit: str) -> None:
        """Set the active display unit. e.g. 'Gram', 'Milligram'."""
        params = f"<v03:Unit>{unit}</v03:Unit>"
        resp = self._call("IWeighingTaskService", "SetUnit", params=params)
        self._check_outcome(resp, "SetUnit")

    # -- convenience helper that combines several calls -----------------------

    def start_automated_dosing_method(self) -> str:
        """Find the first method on the terminal of type 'AutomatedDosing' and
        start it. Returns the method name actually started.

        The AutomatedDosing method must be created once, manually, on the
        balance touchscreen. It is just a container ??actual dosing parameters
        come from the dosing job list at runtime."""
        for m in self.get_list_of_methods():
            if m["method_type"] == "AutomatedDosing":
                self.start_task(m["name"])
                return m["name"]
        raise RuntimeError(
            "No AutomatedDosing-type method found on the balance terminal. "
            "Create one once via Methods menu on the touchscreen."
        )

    # =======================================================================
    # IDosingAutomationService (4/5)
    # =======================================================================

    def _job_to_xml(self, job: DosingJob) -> str:
        tol = ""
        if job.lower_tolerance is not None:
            tol += (f"<v03:LowerTolerance>"
                    f"<v03:Value>{job.lower_tolerance}</v03:Value>"
                    f"<v03:Unit>{job.target_unit}</v03:Unit>"
                    f"</v03:LowerTolerance>")
        if job.upper_tolerance is not None:
            tol += (f"<v03:UpperTolerance>"
                    f"<v03:Value>{job.upper_tolerance}</v03:Value>"
                    f"<v03:Unit>{job.target_unit}</v03:Unit>"
                    f"</v03:UpperTolerance>")
        return (
            "<v03:DosingJob>"
              f"<v03:VialName>{job.vial_name}</v03:VialName>"
              f"<v03:SubstanceName>{job.substance_name}</v03:SubstanceName>"
              "<v03:TargetWeight>"
                f"<v03:Value>{job.target_value}</v03:Value>"
                f"<v03:Unit>{job.target_unit}</v03:Unit>"
              "</v03:TargetWeight>"
              f"{tol}"
            "</v03:DosingJob>"
        )

    def start_dosing_job_list(self, jobs: List[DosingJob]) -> None:
        if not 1 <= len(jobs) <= 100:
            raise ValueError("Web Service accepts 1..100 dosing jobs per list.")
        jobs_xml = "".join(self._job_to_xml(j) for j in jobs)
        params = f"<v03:DosingJobList>{jobs_xml}</v03:DosingJobList>"
        
        # DEBUG: ?붿껌 ?댁슜 異쒕젰
        print(f"\n{'='*60}")
        print("?뵇 DosingJob XML being sent:")
        print(jobs_xml)
        print('='*60)
        
        resp = self._call("IDosingAutomationService", "StartExecuteDosingJobListAsync",
                          params=params)
        
        # DEBUG: ?묐떟 ?댁슜 異쒕젰
        print(f"\n{'='*60}")
        print("?뱿 SOAP Response:")
        print(ET.tostring(resp, encoding='unicode')[:1000])
        print('='*60)
        
        self._check_outcome(resp, "StartExecuteDosingJobListAsync")
        
        # JobErrors 泥댄겕
        job_errors = resp.findall(".//{http://MT/Laboratory/Balance/XprXsr/V03}DosingJobError")
        if job_errors:
            details = []
            for je in job_errors:
                err_elem = je.find(".//{http://MT/Laboratory/Balance/XprXsr/V03}Error")
                err = err_elem.text if err_elem is not None else "unknown"
                details.append(err)
            print(f"\n??DosingJob validation errors: {details}")
            raise RuntimeError(f"DosingJob validation errors: {details}")

    def confirm_dosing_action(self, action_type: str, action_item: str) -> None:
        """action_type ??{'PlaceVial', 'RemoveVial', 'PlaceDosingHead', 'RemoveDosingHead'}
        
        CRITICAL FIX: The element name MUST be "ExecutedDosingJobAction" not "DosingJobActionType"!
        See WSDL MT.Laboratory.Balance.XprXsr.V03.wsdl line 4407-4430
        """
        # FIXED: ExecutedDosingJobAction (not DosingJobActionType!)
        params = (f"<v03:ExecutedDosingJobAction>{action_type}</v03:ExecutedDosingJobAction>"
                  f"<v03:ActionItem>{action_item or ''}</v03:ActionItem>")
        self._call("IDosingAutomationService", "ConfirmDosingJobAction", params=params)

    def cancel_current_dosing_job_list(self) -> None:
        resp = self._call("IDosingAutomationService", "CancelCurrentDosingJobListAsync")
        self._check_outcome(resp, "CancelCurrentDosingJobListAsync")

    def read_dosing_head(self) -> dict:
        """Read metadata stored on the currently mounted Quantos dosing head
        (substance, lot, expiry, fill level, etc.)."""
        resp = self._call("IDosingAutomationService", "ReadDosingHead")
        # The response has many fields; surface the most useful ones.
        return {
            "substance":      _find_text(resp, "SubstanceName"),
            "lot_id":         _find_text(resp, "LotId"),
            "filling_date":   _find_text(resp, "FillingDate"),
            "expiry_date":    _find_text(resp, "ExpiryDate"),
            "remaining_quantity": _find_float(resp, "RemainingQuantity"),
            "number_of_dosages":  _find_text(resp, "NumberOfDosages"),
        }

    # -- the main dosing event loop ------------------------------------------

    def run_dosing_jobs(self, jobs: List[DosingJob], robot: Robot,
                        max_polls: int = 600, poll_interval_s: float = 0.8
                        ) -> List[DosingResult]:
        """Submit a job list and drive the semi-automatic state machine to
        completion. Blocks until DosingAutomationFinishedAsyncNotification.

        Mirrors DosingAutomationService.StartHandlingDosingAutomationNotifications
        from the Mettler C# sample, but with a real Robot callback instead of
        the C# Thread.Sleep() simulation."""
        self.start_dosing_job_list(jobs)
        results: List[DosingResult] = []
        polls = 0
        while polls < max_polls:
            polls += 1
            for n in self.get_notifications():
                kind = (n.attrib.get(f"{{{NS['xsi']}}}type")
                        or n.tag.split("}")[-1])

                if "DosingAutomationActionAsyncNotification" in kind:
                    action_type = _find_text(n, "DosingJobActionType")
                    action_item = _find_text(n, "ActionItem")
                    print(f"  [balance] requesting {action_type}('{action_item}')")
                    if   action_type == "PlaceVial":        robot.place_vial(action_item)
                    elif action_type == "RemoveVial":       robot.remove_vial(action_item)
                    elif action_type == "PlaceDosingHead":  robot.place_dosing_head(action_item)
                    elif action_type == "RemoveDosingHead": robot.remove_dosing_head(action_item)
                    self.confirm_dosing_action(action_type, action_item)

                elif "DosingAutomationJobFinishedAsyncNotification" in kind:
                    outcome = _find_text(n, "Outcome")
                    success = (outcome == "Success")
                    job_idx_txt = _find_text(n, "JobIndex")
                    job_idx = int(job_idx_txt) if job_idx_txt is not None else len(results)
                    duration = _find_float(n, "DurationInSeconds")
                    av = n.find(".//v03:ActualWeight/v03:Value", NS)
                    au = n.find(".//v03:ActualWeight/v03:Unit",  NS)
                    actual_value = float(av.text) if av is not None else None
                    actual_unit  = au.text if au is not None else None
                    if actual_value is not None:
                        self.last_actual_weight_value = actual_value
                        self.last_actual_weight_unit  = actual_unit
                    src = jobs[job_idx] if 0 <= job_idx < len(jobs) else jobs[len(results) % len(jobs)]
                    results.append(DosingResult(
                        job_index=job_idx,
                        substance_name=src.substance_name,
                        vial_name=src.vial_name,
                        target_value=src.target_value,
                        target_unit=src.target_unit,
                        actual_value=actual_value,
                        actual_unit=actual_unit,
                        success=success,
                        duration_s=duration,
                        error=_find_text(n, "DosingError"),
                    ))
                    print(f"  [balance] job {job_idx} done: success={success}")

                elif "DosingAutomationFinishedAsyncNotification" in kind:
                    print("  [balance] dosing automation finished.")
                    return results

            time.sleep(poll_interval_s)
        raise TimeoutError("Dosing automation did not finish within max_polls.")

    # =======================================================================
    # IBasicService (7/9)
    # =======================================================================

    def get_device_information(self) -> DeviceInfo:
        resp = self._call("IBasicService", "GetDeviceInformation")
        info = DeviceInfo(
            serial_number=_find_text(resp, "SerialNumber"),
            type_designation=_find_text(resp, "TypeDesignation"),
            software_version=_find_text(resp, "SoftwareVersion"),
            hardware_version=_find_text(resp, "HardwareVersion"),
        )
        # collect any other top-level text fields into extra
        for child in resp.iter():
            tag = child.tag.split("}")[-1]
            if tag not in {"SerialNumber", "TypeDesignation", "SoftwareVersion",
                            "HardwareVersion", "GetDeviceInformationResponse",
                            "Outcome", "Body", "Envelope"}:
                if child.text and child.text.strip():
                    info.extra.setdefault(tag, child.text.strip())
        return info

    def beep(self, count: int = 1) -> None:
        """Make the balance beep N times."""
        params = f"<v03:Count>{count}</v03:Count>"
        self._call("IBasicService", "Beep", params=params)

    def show_message_on_display(self, message: str) -> None:
        """Display a custom text on the balance touchscreen.
        Useful as a debug HUD: 'Iter 5/20 ??running BO suggest'."""
        params = f"<v03:CustomText>{message}</v03:CustomText>"
        self._call("IBasicService", "ShowCustomTextOnDisplay", params=params)

    def clear_message_on_display(self) -> None:
        self._call("IBasicService", "ClearCustomTextOnDisplay")

    def go_to_standby(self) -> None:
        self._call("IBasicService", "GoToStandby")

    def wakeup_from_standby(self) -> None:
        self._call("IBasicService", "WakeupFromStandby")

    def set_date_and_time(self, iso_datetime: str) -> None:
        """iso_datetime e.g. '2026-04-09T14:30:00'."""
        params = f"<v03:DateAndTime>{iso_datetime}</v03:DateAndTime>"
        self._call("IBasicService", "SetDateAndTime", params=params)

    # =======================================================================
    # IDraftShieldsService (2/2)
    # =======================================================================

    def get_draft_shield_position(self) -> List[dict]:
        """Returns list of {shield_id, opening_width} dicts."""
        resp = self._call("IDraftShieldsService", "GetPosition")
        out = []
        for pos in resp.findall(".//v03:DraftShieldPosition", NS):
            sid = pos.find("v03:DraftShieldId", NS)
            ow  = pos.find("v03:OpeningWidth",  NS)
            out.append({
                "shield_id":     sid.text if sid is not None else None,
                "opening_width": int(ow.text) if ow is not None else None,
            })
        return out

    def set_draft_shield_position(self, shield_id: str, opening_width: int) -> None:
        """Open / close a single draft shield door.
        shield_id ??{'LeftOuter','RightOuter','LeftInner','RightInner','Top'}
        opening_width: 0 (closed) ~ 100 (fully open) typically.

        Useful for SDL automation: open before vial placement, close before
        actual measurement to avoid air-current vibration on mg-scale weights.
        """
        params = (
            "<v03:DraftShieldsPositions>"
              "<v03:DraftShieldPosition>"
                f"<v03:DraftShieldId>{shield_id}</v03:DraftShieldId>"
                f"<v03:OpeningWidth>{opening_width}</v03:OpeningWidth>"
              "</v03:DraftShieldPosition>"
            "</v03:DraftShieldsPositions>"
        )
        resp = self._call("IDraftShieldsService", "SetPosition", params=params)
        self._check_outcome(resp, "SetPosition")

    # convenience: open/close all sides at once
    def open_all_doors(self, width: int = 100) -> None:
        for sid in ("LeftOuter", "RightOuter", "Top"):
            try: self.set_draft_shield_position(sid, width)
            except Exception: pass

    def close_all_doors(self) -> None:
        for sid in ("LeftOuter", "RightOuter", "Top"):
            try: self.set_draft_shield_position(sid, 0)
            except Exception: pass

    # =======================================================================
    # IAdjustmentService (3/3)
    # =======================================================================

    def get_adjustment_strategy(self) -> str:
        """Returns the current internal-weight adjustment strategy."""
        resp = self._call("IAdjustmentService", "GetAdjustmentStrategy")
        return _find_text(resp, "AdjustmentStrategy") or ""

    def set_adjustment_strategy(self, strategy: str) -> None:
        """strategy is a balance-defined string. Common: 'Internal', 'External', 'Off'."""
        params = f"<v03:AdjustmentStrategy>{strategy}</v03:AdjustmentStrategy>"
        resp = self._call("IAdjustmentService", "SetAdjustmentStrategy", params=params)
        self._check_outcome(resp, "SetAdjustmentStrategy")

    def start_adjustment_async(self) -> None:
        """Trigger an internal-weight adjustment. Result arrives via
        get_notifications() as a StartAdjustmentAsyncNotification.
        Recommended every 8-12 h for 24/7 SDL operation."""
        resp = self._call("IAdjustmentService", "StartAdjustmentAsync")
        self._check_outcome(resp, "StartAdjustmentAsync")

    # =======================================================================
    # Adding new operations not in this file
    # =======================================================================
    #
    # If you need an operation we didn't wrap (see WSDL for the full 61),
    # the pattern is always:
    #
    #     def my_new_method(self, foo: str) -> None:
    #         params = f"<v03:Foo>{foo}</v03:Foo>"
    #         resp = self._call("IXxxService", "OperationName", params=params)
    #         self._check_outcome(resp, "OperationName")
    #
    # Look up the request body shape in the CHM file:
    #     MT.Laboratory.Balance.XprXsr.V03 Web Service.chm
    #     -> Index tab -> search for "OperationName"
    #     -> Method page shows Request Body Parameters table.
