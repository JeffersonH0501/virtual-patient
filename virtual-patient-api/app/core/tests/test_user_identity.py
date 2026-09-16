"""Validation checks for the email-based account contract."""

import unittest
from pydantic import ValidationError
from app.models.user import UserCreate, UserUpdate
from app.routers.auth import TokenRequest


class UserIdentityTests(unittest.TestCase):
    def payload(self):
        return dict(email="Student@example.org", name="Ana Maria De la Cruz", password=" secret ")

    def test_registration_normalizes_email_and_preserves_compound_names(self):
        request = UserCreate(**self.payload())
        self.assertEqual(request.email, "student@example.org")
        self.assertEqual(request.name, "Ana Maria De la Cruz")
        self.assertEqual(request.password, " secret ")

    def test_registration_requires_name_and_email(self):
        # The registration form uses a single "Name" value; name and email stay
        # mandatory and reject empty or whitespace-only values.
        for field in ("name", "email"):
            for value in (None, "", "   "):
                payload = self.payload()
                payload[field] = value
                with self.subTest(field=field, value=value), self.assertRaises(ValidationError):
                    UserCreate(**payload)

    def test_registration_rejects_privilege_and_retired_fields(self):
        for field, value in (
            ("role", "superuser"),
            ("organization_id", 99),
            ("username", "retired"),
            ("full_name", "Retired Name"),
            ("first_name", "Ana"),
            ("last_name", "De la Cruz"),
        ):
            payload = self.payload()
            payload[field] = value
            with self.subTest(field=field), self.assertRaises(ValidationError):
                UserCreate(**payload)

    def test_login_uses_email_only(self):
        request = TokenRequest(email=" STUDENT@example.org ", password="secret")
        self.assertEqual(request.email, "student@example.org")
        with self.assertRaises(ValidationError):
            TokenRequest(username="retired", password="secret")

    def test_profile_update_rejects_null_names_email_and_privileges(self):
        for field in ("email", "name", "role", "organization_id"):
            with self.subTest(field=field), self.assertRaises(ValidationError):
                UserUpdate.model_validate({field: None})
        self.assertEqual(UserUpdate(preferred_language="es").model_dump(exclude_unset=True), {"preferred_language": "es"})
