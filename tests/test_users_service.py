import unittest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi import HTTPException

from app.core.config import get_settings
from app.core.database import Base
from app.domains.registry import *  # register all ORM models for SQLAlchemy relationships
from app.domains.users.models import User, UserRole
from app.domains.users.schemas import UserProfileUpdateIn, UserPreferencesUpdateIn
from app.domains.users.service import (
    update_profile,
    update_preferences,
    get_default_preferences,
)

settings = get_settings()


class TestUsersService(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(settings.database_url)
        self.TestingSessionLocal = sessionmaker(
            autocommit=False, autoflush=False, bind=self.engine
        )
        # Ensure database tables exist
        Base.metadata.create_all(bind=self.engine)
        self.db = self.TestingSessionLocal()

        # Clean any potential leftovers from previous runs
        self.db.query(User).filter(
            User.phone_normalized.in_(["8107891549", "9012345678"])
        ).delete(synchronize_session=False)
        self.db.commit()

        # Seed the main test user
        self.user = User(
            phone_normalized="8107891549",
            phone_display="08107891549",
            email="divine.obinali@elizade.com",
            first_name="Divine",
            last_name="Obinali",
            city="Lagos",
            state="Lagos",
            role=UserRole.customer,
            preferences={
                "push_enabled": True,
                "sms_enabled": True,
                "email_enabled": True,
                "marketing_opt_in": False,
            },
        )
        self.db.add(self.user)
        self.db.commit()
        self.db.refresh(self.user)

    def tearDown(self):
        # Remove seeded test users to leave the DB clean
        self.db.query(User).filter(
            User.phone_normalized.in_(["8107891549", "9012345678"])
        ).delete(synchronize_session=False)
        self.db.commit()
        self.db.close()

    def test_update_profile_partial_city(self):
        payload = UserProfileUpdateIn(city="Ibadan")
        result = update_profile(self.db, self.user, payload)

        self.assertEqual(result.city, "Ibadan")
        self.assertEqual(result.firstName, "Divine")
        self.assertEqual(result.lastName, "Obinali")
        self.assertEqual(result.email, "divine.obinali@elizade.com")

    def test_update_profile_multiple_fields(self):
        payload = UserProfileUpdateIn(
            firstName="Divine-Edit",
            lastName="Obinali-Edit",
            state="Oyo",
            department="Engineering",
        )
        result = update_profile(self.db, self.user, payload)

        self.assertEqual(result.firstName, "Divine-Edit")
        self.assertEqual(result.lastName, "Obinali-Edit")
        self.assertEqual(result.state, "Oyo")
        self.assertEqual(result.department, "Engineering")

    def test_update_profile_duplicate_email_raises_error(self):
        # Create another user
        another_user = User(
            phone_normalized="9012345678",
            phone_display="09012345678",
            email="other@elizade.com",
            first_name="Other",
            last_name="User",
            role=UserRole.customer,
        )
        self.db.add(another_user)
        self.db.commit()

        # Try to steal email
        payload = UserProfileUpdateIn(email="other@elizade.com")
        with self.assertRaises(HTTPException) as ctx:
            update_profile(self.db, self.user, payload)

        self.assertEqual(ctx.exception.status_code, 409)
        self.assertIn("Email already in use", ctx.exception.detail)

    def test_update_profile_duplicate_phone_raises_error(self):
        # Create another user
        another_user = User(
            phone_normalized="9012345678",
            phone_display="09012345678",
            email="other@elizade.com",
            first_name="Other",
            last_name="User",
            role=UserRole.customer,
        )
        self.db.add(another_user)
        self.db.commit()

        # Try to steal phone
        payload = UserProfileUpdateIn(phone="09012345678")
        with self.assertRaises(HTTPException) as ctx:
            update_profile(self.db, self.user, payload)

        self.assertEqual(ctx.exception.status_code, 409)
        self.assertIn(
            "Phone number already registered by another user",
            ctx.exception.detail,
        )

    def test_update_preferences_success(self):
        payload = UserPreferencesUpdateIn(
            pushEnabled=False,
            marketingOptIn=True,
        )
        result = update_preferences(self.db, self.user, payload)

        self.assertEqual(result.pushEnabled, False)
        self.assertEqual(result.marketingOptIn, True)
        self.assertEqual(result.smsEnabled, True)
        self.assertEqual(result.emailEnabled, True)

    def test_get_default_preferences(self):
        result = get_default_preferences()
        self.assertEqual(result.pushEnabled, True)
        self.assertEqual(result.smsEnabled, True)
        self.assertEqual(result.emailEnabled, True)
        self.assertEqual(result.marketingOptIn, False)


if __name__ == "__main__":
    unittest.main()
