"""Exercise login identifier resolution against an isolated SQLite database."""

import unittest
from unittest.mock import patch

from sqlalchemy import Boolean, Column, Integer, String, create_engine
from sqlalchemy.orm import declarative_base, Session

from app.core import auth


TestBase = declarative_base()


class Account(TestBase):
    __tablename__ = "test_accounts"
    id = Column(Integer, primary_key=True)
    disabled = Column(Boolean, default=False)
    email = Column(String)
    hashed_password = Column(String)


class AuthenticationIdentifierTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        TestBase.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.account = Account(
            email="Student@example.org",
            hashed_password="test-hash",
        )
        self.db.add(self.account)
        self.db.commit()
        self.model_patch = patch.object(auth, "UserDB", Account)
        self.model_patch.start()
        self.password_patch = patch.object(auth, "verify_password", return_value=True)
        self.verify = self.password_patch.start()

    def tearDown(self):
        self.password_patch.stop()
        self.model_patch.stop()
        self.db.close()
        self.engine.dispose()

    def test_email_case_and_whitespace_resolve_to_same_account(self):
        for identifier in ("Student@example.org", "STUDENT@EXAMPLE.ORG", " student@example.org "):
            with self.subTest(identifier=identifier):
                result = auth.authenticate_user(self.db, identifier, " password ")
                self.assertEqual(result.id, self.account.id)
                self.verify.assert_called_with(" password ", "test-hash")

    def test_unknown_and_empty_identifiers_do_not_verify_passwords(self):
        for identifier in ("missing", "", "   ", "studentone"):
            self.assertIsNone(auth.authenticate_user(self.db, identifier, "password"))
        self.verify.assert_not_called()

    def test_wrong_password_is_rejected(self):
        self.verify.return_value = False
        self.assertIsNone(auth.authenticate_user(self.db, "student@example.org", "wrong"))

    def test_disabled_account_is_rejected(self):
        self.account.disabled = True
        self.db.commit()
        self.assertIsNone(auth.authenticate_user(self.db, "student@example.org", "password"))
        self.verify.assert_not_called()

    def test_tokens_keep_identity_after_email_change(self):
        token = auth.create_access_token({"sub": str(self.account.id)})
        self.account.email = "new@example.org"
        self.db.commit()
        self.assertEqual(auth.get_current_user_from_token(token, self.db).id, self.account.id)

    def test_legacy_numeric_subject_does_not_impersonate_user_id(self):
        from jose import jwt
        token = jwt.encode({"sub": str(self.account.id)}, auth.SECRET_KEY, algorithm=auth.ALGORITHM)
        self.assertIsNone(auth.get_current_user_from_token(token, self.db))

    def test_refresh_token_is_not_an_access_token(self):
        token = auth.create_refresh_token({"sub": str(self.account.id)})
        self.assertIsNone(auth.get_current_user_from_token(token, self.db))

    def test_case_variant_email_collision_is_rejected(self):
        self.db.add(Account(email="STUDENT@example.org"))
        self.db.commit()
        self.assertIsNone(auth.authenticate_user(self.db, "student@example.org", "password"))
        self.verify.assert_not_called()
