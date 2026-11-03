"""Tests for audiovisual profile preparation in the patient workflow."""

import unittest

from app.agents.virtual_patient_workflow import VirtualPatientWorkflow


class AvatarRenderNodeTests(unittest.TestCase):
    def test_render_node_resolves_the_same_profile_used_by_speech(self) -> None:
        workflow = object.__new__(VirtualPatientWorkflow)
        workflow.current_language = "Spanish"
        workflow.personality = "friendly_polite"
        workflow.patient_gender = "female"

        result = workflow.prepare_avatar_render_node({})

        self.assertEqual(
            result["patient_speech_profile"],
            {
                "language": "es",
                "personality_key": "friendly_polite",
                "gender": "female",
                "voice": "nova",
                "vocal_style_key": "friendly_polite",
            },
        )

    def test_graph_runs_avatar_render_preparation_after_translation(self) -> None:
        workflow = object.__new__(VirtualPatientWorkflow)
        graph = workflow._create_workflow().get_graph()
        edges = {(edge.source, edge.target) for edge in graph.edges}

        self.assertIn(("translate_patient_response", "prepare_avatar_render"), edges)
        self.assertIn(("prepare_avatar_render", "finalize"), edges)
