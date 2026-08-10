"""Unit tests for `src.app.core.notifications`: pure bilingual (en/fr)
notification-copy builders — no Firestore, no network, no mocks needed."""

import pytest

from src.app.core.notifications import (
    agent_notification,
    process_label,
    supervisor_notification,
)
from src.app.globals.enum import DownTimeType, Language, Process


class TestAgentNotification:
    def test_others_selects_monitor_and_close_copy(self):
        title, body = agent_notification(
            DownTimeType.OTHERS, Process.PRODUCTION, Language.EN, "Line A"
        )
        assert "unknown" in title.lower()
        assert "monitor" in body.lower() and "close" in body.lower()

    def test_wip_shortage_selects_shortage_copy(self):
        title, body = agent_notification(
            DownTimeType.WIP_SHORTAGE, Process.PRODUCTION, Language.EN, "Line A"
        )
        assert "wip shortage" in title.lower()
        assert "shortage" in body.lower() and "resume" in body.lower()

    def test_material_shortage_selects_material_shortage_copy_en(self):
        title, body = agent_notification(
            DownTimeType.MATERIAL_SHORTAGE, Process.LOGISTIC, Language.EN, "Line A"
        )
        assert title == "Material shortage — production stopped"
        assert "material" in body.lower() and "supply" in body.lower()
        assert "production team will close the ticket" in body

    def test_material_shortage_selects_material_shortage_copy_fr(self):
        title, body = agent_notification(
            DownTimeType.MATERIAL_SHORTAGE, Process.LOGISTIC, Language.FR, "Line A"
        )
        assert title == "Rupture matière — production arrêtée"
        assert "rupture matière" in body.lower()
        assert "clôturera le ticket" in body

    @pytest.mark.parametrize(
        "down_time_type",
        [
            DownTimeType.BREAKDOWN,
            DownTimeType.QUALITY_ISSUE,
            DownTimeType.ABSENTEEISM,
            DownTimeType.SETUP_CHANGEOVER,
        ],
    )
    def test_every_other_type_selects_default_copy(self, down_time_type):
        title, body = agent_notification(
            down_time_type, Process.MAINTENANCE, Language.EN, "Line A"
        )
        assert title == "New downtime ticket"
        assert "needs attention" in body.lower()

    @pytest.mark.parametrize(
        "down_time_type",
        [
            DownTimeType.OTHERS,
            DownTimeType.WIP_SHORTAGE,
            DownTimeType.MATERIAL_SHORTAGE,
            DownTimeType.BREAKDOWN,
        ],
    )
    def test_en_and_fr_are_non_empty_and_different(self, down_time_type):
        en_title, en_body = agent_notification(
            down_time_type, Process.PRODUCTION, Language.EN, "Line A"
        )
        fr_title, fr_body = agent_notification(
            down_time_type, Process.PRODUCTION, Language.FR, "Line A"
        )
        assert en_title and en_body and fr_title and fr_body
        assert en_title != fr_title
        assert en_body != fr_body

    def test_location_and_process_interpolate_in_default_variant(self):
        _, body = agent_notification(
            DownTimeType.BREAKDOWN, Process.QUALITY, Language.EN, "Workstation 7"
        )
        assert "Workstation 7" in body
        assert "quality" in body

    def test_location_interpolates_in_others_variant(self):
        _, body = agent_notification(
            DownTimeType.OTHERS, Process.PRODUCTION, Language.EN, "Workstation 7"
        )
        assert "Workstation 7" in body

    def test_unrecognized_language_falls_back_to_en(self):
        title, body = agent_notification(
            DownTimeType.BREAKDOWN, Process.MAINTENANCE, "klingon", "Line A"
        )
        en_title, en_body = agent_notification(
            DownTimeType.BREAKDOWN, Process.MAINTENANCE, Language.EN, "Line A"
        )
        assert (title, body) == (en_title, en_body)


class TestSupervisorNotification:
    def test_en_and_fr_are_non_empty_and_different(self):
        en_title, en_body = supervisor_notification(Language.EN, "Line A")
        fr_title, fr_body = supervisor_notification(Language.FR, "Line A")
        assert en_title and en_body and fr_title and fr_body
        assert en_title != fr_title
        assert en_body != fr_body

    def test_location_interpolates_in_title_and_body(self):
        title, body = supervisor_notification(Language.EN, "Workstation 7")
        assert "Workstation 7" in title
        assert "Workstation 7" in body

    def test_unrecognized_language_falls_back_to_en(self):
        title, body = supervisor_notification("klingon", "Line A")
        en_title, en_body = supervisor_notification(Language.EN, "Line A")
        assert (title, body) == (en_title, en_body)


class TestProcessLabel:
    @pytest.mark.parametrize(
        "process,expected_en,expected_fr",
        [
            (Process.PRODUCTION, "production", "production"),
            (Process.MAINTENANCE, "maintenance", "maintenance"),
            (Process.QUALITY, "quality", "qualité"),
            (Process.LOGISTIC, "logistics", "logistique"),
        ],
    )
    def test_localized_label_per_language(self, process, expected_en, expected_fr):
        assert process_label(process, Language.EN) == expected_en
        assert process_label(process, Language.FR) == expected_fr

    def test_unrecognized_language_falls_back_to_en(self):
        assert process_label(Process.QUALITY, "klingon") == "quality"
