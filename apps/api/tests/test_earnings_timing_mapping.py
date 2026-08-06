"""BEFORE_OPEN and AFTER_CLOSE entry/exit session-mapping tests
(Revision Prompt 4's required test #3)."""

from __future__ import annotations

from tradingos_api.services.earnings_timing import map_earnings_timing_to_sessions


class TestBeforeOpenMapping:
    def test_pre_event_session_is_prior_close(self) -> None:
        mapping = map_earnings_timing_to_sessions("BEFORE_OPEN")
        assert mapping.pre_event_session == "PRIOR_SESSION_CLOSE"

    def test_post_event_session_is_todays_open(self) -> None:
        mapping = map_earnings_timing_to_sessions("BEFORE_OPEN")
        assert mapping.post_event_session == "TODAY_OPEN"


class TestAfterCloseMapping:
    def test_pre_event_session_is_todays_close(self) -> None:
        mapping = map_earnings_timing_to_sessions("AFTER_CLOSE")
        assert mapping.pre_event_session == "TODAY_SESSION_CLOSE"

    def test_post_event_session_is_next_sessions_open(self) -> None:
        mapping = map_earnings_timing_to_sessions("AFTER_CLOSE")
        assert mapping.post_event_session == "NEXT_SESSION_OPEN"


class TestBeforeOpenAndAfterCloseNeverShareAMapping:
    def test_the_two_mappings_are_distinct(self) -> None:
        before = map_earnings_timing_to_sessions("BEFORE_OPEN")
        after = map_earnings_timing_to_sessions("AFTER_CLOSE")
        assert before != after
        assert before.post_event_session != after.post_event_session


class TestUnresolvedTimingsNeverGuess:
    def test_time_not_supplied_is_unresolved(self) -> None:
        mapping = map_earnings_timing_to_sessions("TIME_NOT_SUPPLIED")
        assert mapping.pre_event_session == "UNRESOLVED"
        assert mapping.post_event_session == "UNRESOLVED"

    def test_date_unconfirmed_is_unresolved(self) -> None:
        mapping = map_earnings_timing_to_sessions("DATE_UNCONFIRMED")
        assert mapping.pre_event_session == "UNRESOLVED"
        assert mapping.post_event_session == "UNRESOLVED"

    def test_unknown_is_unresolved(self) -> None:
        mapping = map_earnings_timing_to_sessions("UNKNOWN")
        assert mapping.pre_event_session == "UNRESOLVED"
        assert mapping.post_event_session == "UNRESOLVED"
