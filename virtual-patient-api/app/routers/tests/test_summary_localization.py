"""Unit tests for localized progress-summary caching."""

from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from app.agents.schemas.progress_summary import ProgressSummarySchema
from app.routers import summary as summary_router


class SummaryLocalizationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.canonical = ProgressSummarySchema(
            age=65,
            weight_in_kg=70,
            current_symptoms=[{"symptom": "fatigue", "status": "active"}],
            allergies=["pollen"],
            habits=[{"habit": "walking", "frequency": "daily"}],
            medical_history=[{"type": "hospitalization", "date": "2020"}],
            work_information="Retired teacher",
            summary_text="The patient reports fatigue.",
        )

    async def test_english_uses_canonical_summary_without_translation(self) -> None:
        stored = SimpleNamespace(source_language="en", localized_versions={})
        controller = MagicMock()
        controller.to_schema.return_value = self.canonical

        with patch.object(summary_router, "TranslatorAgent") as translator_type:
            result = await summary_router._resolve_localized_summary(
                9,
                stored,
                "en",
                controller,
            )

        self.assertEqual(result.summary_text, self.canonical.summary_text)
        translator_type.assert_not_called()

    async def test_spanish_translation_is_cached_and_reused(self) -> None:
        stored = SimpleNamespace(source_language="en", localized_versions={})
        translated = self.canonical.model_copy(
            update={"summary_text": "El paciente reporta fatiga."}
        )
        controller = MagicMock()
        controller.to_schema.return_value = self.canonical

        def cache_translation(_interview_id, language, summary_data) -> None:
            stored.localized_versions[language] = summary_data.model_dump()

        controller.cache_localized_summary.side_effect = cache_translation
        translator = MagicMock()
        translator.translate_progress_summary = AsyncMock(return_value=translated)

        with patch.object(summary_router, "TranslatorAgent", return_value=translator):
            first = await summary_router._resolve_localized_summary(
                9,
                stored,
                "es",
                controller,
            )
            second = await summary_router._resolve_localized_summary(
                9,
                stored,
                "es",
                controller,
            )

        self.assertEqual(first.summary_text, "El paciente reporta fatiga.")
        self.assertEqual(second.summary_text, first.summary_text)
        translator.translate_progress_summary.assert_awaited_once()
        controller.cache_localized_summary.assert_called_once()
