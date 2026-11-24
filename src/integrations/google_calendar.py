"""Google Calendar and Google Meet async client operations."""

import asyncio
import uuid
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo


def _ensure_rfc3339(dt_str: str, timezone_name: str) -> str:
    """Normalize an ISO 8601 datetime string to include timezone offset."""
    parsed = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ZoneInfo(timezone_name))
    return parsed.isoformat()


def _extract_meet_link(event_payload: dict[str, Any]) -> str:
    """Extract the Google Meet link from an event payload if present."""
    hangout_link = str(event_payload.get("hangoutLink") or "")
    if hangout_link:
        return hangout_link

    conference_data = event_payload.get("conferenceData") or {}
    for entry_point in conference_data.get("entryPoints", []):
        if entry_point.get("entryPointType") == "video" and entry_point.get("uri"):
            return str(entry_point["uri"])
    return ""


def _serialize_event(item: dict[str, Any]) -> dict[str, Any]:
    """Normalize a Google Calendar event resource into a concise dictionary."""
    start_obj = item.get("start") or {}
    end_obj = item.get("end") or {}
    meet_link = _extract_meet_link(item)
    return {
        "id": str(item.get("id", "")),
        "summary": str(item.get("summary") or "(Sem título)"),
        "start": str(start_obj.get("dateTime") or start_obj.get("date") or ""),
        "end": str(end_obj.get("dateTime") or end_obj.get("date") or ""),
        "location": str(item.get("location") or ""),
        "description": str(item.get("description") or ""),
        "meet_link": meet_link,
        "hangoutLink": meet_link,
        "attendees": [
            str(attendee["email"])
            for attendee in item.get("attendees", [])
            if attendee.get("email")
        ],
        "html_link": str(item.get("htmlLink") or ""),
    }


class GoogleCalendarService:
    """Async wrapper over Google Calendar API v3."""

    def __init__(
        self,
        *,
        service: Any,
        timezone_name: str = "America/Sao_Paulo",
        calendar_id: str = "primary",
    ) -> None:
        self._service = service
        self._timezone_name = timezone_name
        self._calendar_id = calendar_id

    async def list_events(
        self,
        start_iso: str,
        end_iso: str,
        query: str | None = None,
        max_results: int = 20,
    ) -> dict[str, Any]:
        """List calendar events within `[start_iso, end_iso]`."""
        time_min = _ensure_rfc3339(start_iso, self._timezone_name)
        time_max = _ensure_rfc3339(end_iso, self._timezone_name)

        def _run() -> dict[str, Any]:
            kwargs: dict[str, Any] = {
                "calendarId": self._calendar_id,
                "timeMin": time_min,
                "timeMax": time_max,
                "singleEvents": True,
                "orderBy": "startTime",
                "maxResults": max_results,
            }
            if query:
                kwargs["q"] = query
            return self._service.events().list(**kwargs).execute()

        response = await asyncio.to_thread(_run)
        items = response.get("items", [])
        events = [_serialize_event(item) for item in items]
        return {
            "status": "ok",
            "count": len(events),
            "events": events,
        }

    async def create_event(
        self,
        *,
        summary: str,
        start_iso: str,
        end_iso: str,
        description: str | None = None,
        location: str | None = None,
        attendees: list[str] | None = None,
        create_meet: bool = False,
        recurrence: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create a calendar event, optionally generating a Google Meet link."""
        clean_attendees = [email.strip() for email in (attendees or []) if email.strip()]
        body: dict[str, Any] = {
            "summary": summary,
            "start": {
                "dateTime": _ensure_rfc3339(start_iso, self._timezone_name),
                "timeZone": self._timezone_name,
            },
            "end": {
                "dateTime": _ensure_rfc3339(end_iso, self._timezone_name),
                "timeZone": self._timezone_name,
            },
        }
        if description:
            body["description"] = description
        if location:
            body["location"] = location
        if clean_attendees:
            body["attendees"] = [{"email": email} for email in clean_attendees]
        if recurrence:
            body["recurrence"] = recurrence
        if create_meet:
            body["conferenceData"] = {
                "createRequest": {
                    "requestId": uuid.uuid4().hex,
                    "conferenceSolutionKey": {"type": "hangoutsMeet"},
                }
            }

        def _run() -> dict[str, Any]:
            return (
                self._service.events()
                .insert(
                    calendarId=self._calendar_id,
                    body=body,
                    conferenceDataVersion=1 if create_meet else 0,
                    sendUpdates="all" if clean_attendees else "none",
                )
                .execute()
            )

        created = await asyncio.to_thread(_run)
        serialized = _serialize_event(created)
        return {
            "status": "ok",
            "event_id": serialized["id"],
            "summary": serialized["summary"],
            "start": serialized["start"],
            "end": serialized["end"],
            "location": serialized["location"],
            "meet_link": serialized["meet_link"],
            "hangoutLink": serialized["hangoutLink"],
            "html_link": serialized["html_link"],
            "attendees": serialized["attendees"],
        }

    async def update_event(
        self,
        *,
        event_id: str,
        summary: str | None = None,
        start_iso: str | None = None,
        end_iso: str | None = None,
        description: str | None = None,
        location: str | None = None,
    ) -> dict[str, Any]:
        """Patch fields of an existing calendar event."""
        body: dict[str, Any] = {}
        if summary is not None:
            body["summary"] = summary
        if description is not None:
            body["description"] = description
        if location is not None:
            body["location"] = location
        if start_iso is not None:
            body["start"] = {
                "dateTime": _ensure_rfc3339(start_iso, self._timezone_name),
                "timeZone": self._timezone_name,
            }
        if end_iso is not None:
            body["end"] = {
                "dateTime": _ensure_rfc3339(end_iso, self._timezone_name),
                "timeZone": self._timezone_name,
            }

        if not body:
            return {"status": "error", "error": "Nenhum campo informado para atualização."}

        def _run() -> dict[str, Any]:
            return (
                self._service.events()
                .patch(
                    calendarId=self._calendar_id,
                    eventId=event_id,
                    body=body,
                )
                .execute()
            )

        updated = await asyncio.to_thread(_run)
        serialized = _serialize_event(updated)
        return {
            "status": "ok",
            "event_id": serialized["id"] or event_id,
            "summary": serialized["summary"],
            "start": serialized["start"],
            "end": serialized["end"],
            "location": serialized["location"],
            "meet_link": serialized["meet_link"],
            "html_link": serialized["html_link"],
        }

    async def delete_event(self, event_id: str) -> dict[str, Any]:
        """Delete an event from Google Calendar."""

        def _run() -> None:
            self._service.events().delete(
                calendarId=self._calendar_id,
                eventId=event_id,
            ).execute()

        await asyncio.to_thread(_run)
        return {
            "status": "ok",
            "event_id": event_id,
            "deleted": True,
        }
