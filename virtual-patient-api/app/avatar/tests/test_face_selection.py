import unittest

from app.avatar.face_selection import age_group, parse_face_map, select_face_id


class FaceSelectionTests(unittest.TestCase):
    def test_age_groups(self):
        self.assertIsNone(age_group(None))
        self.assertEqual(age_group(25), "young")
        self.assertEqual(age_group(39), "young")
        self.assertEqual(age_group(40), "adult")
        self.assertEqual(age_group(64), "adult")
        self.assertEqual(age_group(65), "senior")

    def test_parse_rejects_invalid_input(self):
        self.assertEqual(parse_face_map(None), {})
        self.assertEqual(parse_face_map("not json"), {})
        self.assertEqual(parse_face_map("[1]"), {})
        self.assertEqual(parse_face_map('{"Male:Young": " a ", "x": ""}'), {"male:young": "a"})

    def test_most_specific_key_wins(self):
        face_map = {
            "male": "m",
            "male:adult": "m-adult",
            "male:anxious": "m-anx",
            "male:adult:anxious": "m-adult-anx",
        }
        self.assertEqual(select_face_id(face_map, "male", 50, "anxious"), "m-adult-anx")
        self.assertEqual(select_face_id(face_map, "male", 50, "calm"), "m-adult")
        self.assertEqual(select_face_id(face_map, "male", 20, "anxious"), "m-anx")
        self.assertEqual(select_face_id(face_map, "male", None, None), "m")

    def test_no_match(self):
        self.assertIsNone(select_face_id({"male": "m"}, "female", 30, None))
        self.assertIsNone(select_face_id({"male": "m"}, None, 30, None))
        self.assertIsNone(select_face_id({}, "male", 30, None))


if __name__ == "__main__":
    unittest.main()
