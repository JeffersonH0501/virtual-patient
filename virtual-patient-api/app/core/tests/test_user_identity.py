"""Validation checks for the email-based account contract."""

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from pydantic import ValidationError
from app.models.user import AdminUserCreate, UserCreate, UserUpdate
from app.routers.auth import TokenRequest
from app.routers.users import persist_user


class UserIdentityTests(unittest.TestCase):
    def payload(self):
        return dict(email="Student@example.org", name="Ana Maria De la Cruz", password=" secret ")

    def test_registration_normalizes_email_and_preserves_compound_names(self):
        request = UserCreate(**self.payload())
        self.assertEqual(request.email, "student@example.org")
        self.assertEqual(request.name, "Ana Maria De la Cruz")
        self.assertEqual(request.password, " secret ")

    def test_new_accounts_default_to_spanish_and_keep_an_explicit_language(self):
        for schema in (UserCreate, AdminUserCreate):
            for supplied, expected in (({}, "es"), ({"preferred_language": None}, "es"),
                                       ({"preferred_language": "en"}, "en")):
                with self.subTest(schema=schema.__name__, supplied=supplied):
                    db = MagicMock()
                    account_query, organization_query = MagicMock(), MagicMock()
                    db.query.side_effect = [account_query, organization_query]
                    account_query.filter.return_value.first.return_value = None
                    organization_query.filter.return_value.order_by.return_value.first.return_value = SimpleNamespace(id=1)
                    with patch("app.routers.users.get_password_hash", return_value="test-hash"):
                        account = persist_user(schema(**self.payload(), **supplied), db)
                    self.assertEqual(account.preferred_language, expected)

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
