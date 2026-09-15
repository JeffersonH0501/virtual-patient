"""Validation checks for the email-based account contract."""

import unittest
from pydantic import ValidationError
from app.models.user import UserCreate, UserUpdate
from app.routers.auth import TokenRequest


class UserIdentityTests(unittest.TestCase):
    def payload(self):
        return dict(email="Student@example.org", first_name="Ana Maria", last_name="De la Cruz", password=" secret ")

    def test_registration_normalizes_email_and_preserves_compound_names(self):
        request = UserCreate(**self.payload())
        self.assertEqual(request.email, "student@example.org")
        self.assertEqual(request.first_name, "Ana Maria")
        self.assertEqual(request.last_name, "De la Cruz")
        self.assertEqual(request.password, " secret ")

    def test_registration_requires_name_and_email(self):
        # The registration form uses a single "Name" value stored in first_name;
        # first_name and email stay mandatory, last_name is optional and may be empty.
        for field in ("first_name", "email"):
            for value in (None, "", "   "):
                payload = self.payload()
                payload[field] = value
                with self.subTest(field=field, value=value), self.assertRaises(ValidationError):
                    UserCreate(**payload)

    def test_registration_accepts_empty_last_name(self):
        payload = self.payload()
        payload["last_name"] = ""
        request = UserCreate(**payload)
        self.assertEqual(request.last_name, "")

    def test_registration_rejects_privilege_and_retired_fields(self):
        for field, value in (("role", "superuser"), ("organization_id", 99), ("username", "retired"), ("full_name", "Retired Name")):
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
        for field in ("email", "first_name", "last_name", "role", "organization_id"):
            with self.subTest(field=field), self.assertRaises(ValidationError):
                UserUpdate.model_validate({field: None})
        self.assertEqual(UserUpdate(preferred_language="es").model_dump(exclude_unset=True), {"preferred_language": "es"})
