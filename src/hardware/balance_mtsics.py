"""
MOF SDL OS — XPR 저울 MT-SICS 통신 계층
==========================================
METTLER TOLEDO XPR/XPR Essential Reference Manual (MT-SICS Interface Commands)
기준으로 구현. 명령/응답은 전부 이 매뉴얼의 표기를 그대로 따른다.

전송 계층 가정: RS232 시리얼 (requirements.txt 참고).
실물 저울이 이더넷/TCP 포트를 쓴다고 확인되면 MTSICSBalance._send()의
구현부(직렬 read/write)만 socket 기반으로 교체하면 된다 — 명령/파싱 로직은
그대로 재사용 가능 (MT-SICS 프로토콜 자체는 전송 계층과 무관, 매뉴얼 p.4).

설정: .env에 아래 값 필요 (python-dotenv로 로드)
    BALANCE_SERIAL_PORT=/dev/ttyUSB0   (또는 COM3 등)
    BALANCE_BAUDRATE=9600
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Optional

import serial
from dotenv import load_dotenv

load_dotenv()


# ─────────────────────────────────────────────────────────────
# 예외
# ─────────────────────────────────────────────────────────────

class BalanceError(Exception):
    """MT-SICS 통신/응답 관련 공통 예외."""


class BalanceOverloadError(BalanceError):
    """저울이 과부하(+)/저부하(-) 범위. 매뉴얼 p.51 <Status> 참고."""


class BalanceTimeoutError(BalanceError):
    """지정 시간 내 안정(stable) 값을 얻지 못함."""


class BalanceSyntaxError(BalanceError):
    """ES/ET/EL 등 일반 에러 응답. 매뉴얼 p.8 참고."""


# ─────────────────────────────────────────────────────────────
# 응답 파싱 결과
# ─────────────────────────────────────────────────────────────

@dataclass
class WeightReading:
    is_stable: bool          # <Status>가 "S"(stable)면 True, "D"(dynamic)면 False
    value_mg: float
    unit: str


# ─────────────────────────────────────────────────────────────
# 저울 클라이언트
# ─────────────────────────────────────────────────────────────

class MTSICSBalance:
    """
    하나의 XPR 저울과의 RS232 연결을 관리.
    device_id별로 인스턴스 하나씩 두고 재사용하는 걸 권장 (매뉴얼 p.9:
    "명령 응답 기다리지 않고 연속 전송 금지" — 커넥션 하나를 순차적으로만 써야 함).
    """

    def __init__(
        self,
        port: Optional[str] = None,
        baudrate: Optional[int] = None,
        timeout_sec: float = 3.0,
    ):
        self.port = port or os.environ["BALANCE_SERIAL_PORT"]
        self.baudrate = baudrate or int(os.environ.get("BALANCE_BAUDRATE", 9600))
        self._ser = serial.Serial(
            port=self.port,
            baudrate=self.baudrate,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=timeout_sec,
        )
        # 매뉴얼 p.9: 세션 시작 시 Abort로 상태 리셋 권장
        self.abort()

    def close(self) -> None:
        self._ser.close()

    def __enter__(self) -> "MTSICSBalance":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # ── 저수준: 명령 전송 + 원시 응답 한 줄 수신 ──────────────────
    def _send_raw(self, command: str) -> str:
        self._ser.write(f"{command}\r\n".encode("ascii"))
        raw = self._ser.readline().decode("ascii", errors="replace").strip()
        if raw in ("ES", "ET", "EL"):
            raise BalanceSyntaxError(f"'{command}' 명령에 대한 저울 응답: {raw} (매뉴얼 p.8)")
        return raw

    @staticmethod
    def _parse_weight_response(raw: str) -> WeightReading:
        """
        예: "S S       12.345 g" -> stable, 12.345, g
            "S D       12.345 g" -> unstable(dynamic)
            "S +" / "S -"        -> 과부하/저부하 -> 예외
            "S I"                -> 명령 이해했지만 지금 실행 불가(타이밍 등) -> 예외
        (매뉴얼 p.5, p.51)
        """
        parts = raw.split()
        if len(parts) < 2:
            raise BalanceError(f"응답 파싱 실패: '{raw}'")

        status = parts[1]
        if status == "+":
            raise BalanceOverloadError("저울 과부하 범위 (weighing range exceeded)")
        if status == "-":
            raise BalanceOverloadError("저울 저부하 범위 (예: 팬이 안 얹혀 있음)")
        if status == "I":
            raise BalanceTimeoutError("저울이 현재 명령 실행 불가 (다른 명령 처리 중 또는 안정 타임아웃)")
        if status not in ("S", "D"):
            raise BalanceError(f"알 수 없는 상태 코드: '{raw}'")
        if len(parts) < 4:
            raise BalanceError(f"무게 응답 형식 이상: '{raw}'")

        value = float(parts[2])
        unit = parts[3]
        value_mg = _to_mg(value, unit)
        return WeightReading(is_stable=(status == "S"), value_mg=value_mg, unit=unit)

    # ── 명령별 공개 메서드 (매뉴얼의 명령명을 그대로 메서드명으로) ──

    def abort(self) -> None:
        """@ — 진행 중인 프로세스(zero/tare 등) 취소, 세션 리셋 (매뉴얼 p.12)."""
        self._send_raw("@")

    def tare_immediately(self) -> WeightReading:
        """TI — 현재 값(안정 여부 무관)을 즉시 tare로 저장 (매뉴얼 p.76)."""
        raw = self._send_raw("TI")
        return self._parse_weight_response(raw)

    def read_stable(self, timeout_sec: float = 30.0, poll_interval_sec: float = 0.3) -> WeightReading:
        """
        S — 안정된 순중량 요청 (매뉴얼 p.51). 저울 자체도 내부 타임아웃(S I)이 있지만
        기종별로 달라 정확한 값이 문서에 없으므로(p.51 comment), 우리 쪽에서
        timeout_sec 동안 S I 응답을 재시도하는 방식으로 상한을 직접 건다.
        """
        deadline = time.time() + timeout_sec
        while time.time() < deadline:
            try:
                return self._parse_weight_response(self._send_raw("S"))
            except BalanceTimeoutError:
                time.sleep(poll_interval_sec)
                continue
        raise BalanceTimeoutError(f"{timeout_sec}초 내 안정값을 얻지 못함")

    def read_immediate(self) -> WeightReading:
        """SI — 안정 여부 상관없이 현재 값 즉시 반환 (매뉴얼 p.52). STABILIZE 폴링용."""
        return self._parse_weight_response(self._send_raw("SI"))

    def open_door(self, which: int = 1) -> None:
        """
        WS <Door> — 방풍문 열기 (매뉴얼 p.80). which=1: 전체/우측 문
        (기종에 따라 다름 — 정확한 코드값은 실물 확인 필요, 일단 1=열기로 가정).
        WS는 non-blocking이라 open/close 후 위치 재조회로 확인 권장(매뉴얼 comment, p.80).
        """
        self._send_raw(f"WS {which}")
        self._wait_for_door_status(expect_open=True)

    def close_door(self) -> None:
        """WS 0 — 모든 방풍문 닫기 (매뉴얼 p.80)."""
        self._send_raw("WS 0")
        self._wait_for_door_status(expect_open=False)

    def _wait_for_door_status(self, expect_open: bool, timeout_sec: float = 10.0) -> None:
        """WS 쿼리(파라미터 없이 WS)로 문이 목표 상태(0=닫힘 / 그 외=열림)에 도달했는지 확인."""
        deadline = time.time() + timeout_sec
        while time.time() < deadline:
            raw = self._send_raw("WS")
            parts = raw.split()
            if len(parts) == 2 and parts[1].isdigit():
                is_closed = parts[1] == "0"
                if is_closed != expect_open:
                    return
            time.sleep(0.2)
        raise BalanceTimeoutError(f"{timeout_sec}초 내 방풍문 상태 확인 실패 (목표: {'open' if expect_open else 'closed'})")


def _to_mg(value: float, unit: str) -> float:
    """저울 표시 단위가 g가 아닐 수 있으므로(M21 설정) mg로 정규화. 매뉴얼 p.42 단위 표 참고."""
    unit = unit.lower()
    factors = {"mg": 1.0, "g": 1000.0, "kg": 1_000_000.0}
    if unit not in factors:
        raise BalanceError(f"지원하지 않는 단위: '{unit}' — 저울 host unit을 g로 맞춰주세요 (M21 명령).")
    return value * factors[unit]
