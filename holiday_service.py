"""中国法定节假日查询服务：在线拉取 + 本地缓存 + 断网回退到周末规则。

数据源：timor.tech 公共节假日 API（返回 type 0-3 区分工作日/周末/节日/调休补班）。
缓存位置：配置目录下 cache/holidays.json，成功缓存 7 天、失败短期缓存避免频繁请求。
"""

import json
import time
import urllib.request
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional

API_DAY_URL = "http://timor.tech/api/holiday/info/{iso}"
API_YEAR_URL = "http://timor.tech/api/holiday/year/{year}"
SUCCESS_TTL_SECONDS = 7 * 24 * 3600
FAILURE_TTL_SECONDS = 6 * 3600
REQUEST_TIMEOUT = 5.0

TYPE_WORKDAY = 0
TYPE_WEEKEND = 1
TYPE_HOLIDAY = 2
TYPE_MAKEUP_WORKDAY = 3

SOURCE_API = "api"
SOURCE_CACHE = "cache"
SOURCE_HEURISTIC = "heuristic"


@dataclass
class DayInfo:
    day: str
    kind: str  # workday / weekend / holiday / makeup-workday / unknown
    name: str
    is_break: bool  # 当天是否放假（节日或普通周末；调休补班不算）
    source: str  # api / cache / heuristic


class HolidayService:
    def __init__(self, cache_path: Path) -> None:
        self.cache_path = Path(cache_path)
        self.last_error: str = ""
        self._cache = self._read_cache()

    def _read_cache(self) -> dict:
        try:
            raw = json.loads(self.cache_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                return raw
        except Exception:
            pass
        return {}

    def _write_cache(self) -> None:
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            self.cache_path.write_text(
                json.dumps(self._cache, ensure_ascii=False, indent=1), encoding="utf-8"
            )
        except Exception:
            pass

    def _cached_entry(self, iso: str) -> Optional[dict]:
        entry = self._cache.get(iso)
        if not isinstance(entry, dict):
            return None
        if entry.get("fetched_at", 0) + entry.get("ttl", 0) < time.time():
            return None
        return entry

    def get_day_info(self, day: date) -> DayInfo:
        iso = day.isoformat()
        entry = self._cached_entry(iso)
        if entry is not None:
            return DayInfo(
                day=iso,
                kind=entry.get("kind", "unknown"),
                name=entry.get("name", ""),
                is_break=bool(entry.get("is_break", day.weekday() >= 5)),
                source=SOURCE_CACHE,
            )
        info = self._fetch_day(iso)
        if info is not None:
            self._store(iso, info, ttl=SUCCESS_TTL_SECONDS, ok=True)
            return DayInfo(day=iso, **info, source=SOURCE_API)
        return self._heuristic(day)

    def is_statutory_holiday(self, day: date) -> bool:
        """当天是否为法定节假日休息日（含调休放假；调休补班日返回 False）。"""
        return self.get_day_info(day).is_break

    def is_workday(self, day: date) -> bool:
        """当天是否要上课：周末与法定节假日为 False，调休补班日为 True。"""
        return not self.get_day_info(day).is_break

    def workday_label(self, day: date) -> str:
        info = self.get_day_info(day)
        if info.is_break:
            return f"休息日（{info.name}）" if info.name else ("周末" if info.kind == TYPE_WEEKEND else "休息日")
        if info.kind == TYPE_MAKEUP_WORKDAY:
            return f"调休补班（{info.name}）" if info.name else "调休补班"
        return "上课日"

    def warm_year(self, year: int) -> int:
        """一次性拉取全年节假日表并写入缓存，返回写入条目数。"""
        try:
            data = self._get_json(API_YEAR_URL.format(year=year))
        except Exception as exc:
            self.last_error = f"拉取 {year} 年节假日失败: {exc}"
            return 0
        holidays = data.get("holiday") if isinstance(data, dict) else None
        if not isinstance(holidays, dict):
            self.last_error = f"{year} 年节假日数据格式异常。"
            return 0
        count = 0
        for value in holidays.values():
            if not isinstance(value, dict):
                continue
            iso = str(value.get("date", ""))[:10]
            try:
                parsed = date.fromisoformat(iso)
            except ValueError:
                continue
            is_holiday = bool(value.get("holiday", True))
            info = {
                "kind": TYPE_HOLIDAY if is_holiday else TYPE_MAKEUP_WORKDAY,
                "name": str(value.get("name", "")),
                "is_break": is_holiday,
            }
            self._store(parsed.isoformat(), info, ttl=SUCCESS_TTL_SECONDS, ok=True)
            count += 1
        self._write_cache()
        return count

    def describe(self, day: date) -> str:
        info = self.get_day_info(day)
        labels = {
            TYPE_WORKDAY: "工作日",
            TYPE_WEEKEND: "周末",
            TYPE_HOLIDAY: f"节假日（{info.name}）" if info.name else "节假日",
            TYPE_MAKEUP_WORKDAY: f"调休补班（{info.name}）" if info.name else "调休补班",
        }
        kind = labels.get(info.kind, "未知（按周末规则推断）")
        source = {SOURCE_API: "在线", SOURCE_CACHE: "缓存", SOURCE_HEURISTIC: "本地推断"}.get(info.source, "")
        return f"{info.day}：{kind}（{source}）"

    def status_text(self) -> str:
        cached = sum(1 for v in self._cache.values() if isinstance(v, dict) and v.get("ok"))
        if self.last_error:
            return f"已缓存 {cached} 天数据；最近错误：{self.last_error}"
        return f"已缓存 {cached} 天数据。"

    # ---- 内部 ----

    def _store(self, iso: str, info: dict, ttl: int, ok: bool) -> None:
        self._cache[iso] = {"fetched_at": time.time(), "ttl": ttl, "ok": ok, **info}
        self._write_cache()

    def _fetch_day(self, iso: str) -> Optional[dict]:
        try:
            data = self._get_json(API_DAY_URL.format(iso=iso))
        except Exception as exc:
            self.last_error = f"节假日接口请求失败: {exc}"
            self._store(iso, {"kind": "unknown", "name": "", "is_break": date.fromisoformat(iso).weekday() >= 5}, ttl=FAILURE_TTL_SECONDS, ok=False)
            return None
        type_info = data.get("type") if isinstance(data, dict) else None
        if not isinstance(type_info, dict) or "type" not in type_info:
            self.last_error = "节假日接口返回格式异常。"
            return None
        kind = int(type_info.get("type", -1))
        holiday = data.get("holiday")
        name = ""
        if isinstance(holiday, dict):
            name = str(holiday.get("name", ""))
        is_break = kind in (TYPE_WEEKEND, TYPE_HOLIDAY)
        if kind == TYPE_MAKEUP_WORKDAY:
            is_break = False
        return {"kind": kind, "name": name, "is_break": is_break}

    def _heuristic(self, day: date) -> DayInfo:
        return DayInfo(
            day=day.isoformat(),
            kind=TYPE_WEEKEND if day.weekday() >= 5 else TYPE_WORKDAY,
            name="",
            is_break=day.weekday() >= 5,
            source=SOURCE_HEURISTIC,
        )

    @staticmethod
    def _get_json(url: str) -> dict:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) CampusCheckinKit/1.0",
            },
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
