from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse


class FoundationTests(TestCase):
    def test_home_redirects_anonymous_users_to_login(self):
        response = self.client.get(reverse("home"))

        self.assertRedirects(response, f"{reverse('login')}?next={reverse('home')}")

    def test_valid_user_can_log_in_and_view_home(self):
        user = get_user_model().objects.create_user(
            username="student",
            email="student@example.edu",
            password="a-long-test-password",
        )

        response = self.client.post(
            reverse("login"),
            {"username": user.username, "password": "a-long-test-password"},
        )

        self.assertRedirects(response, reverse("home"))
        self.assertEqual(self.client.get(reverse("home")).status_code, 200)

    def test_logout_is_post_only(self):
        self.assertEqual(self.client.get(reverse("logout")).status_code, 405)

    def test_email_address_is_unique(self):
        user_model = get_user_model()
        user_model.objects.create_user(
            username="first",
            email="same@example.edu",
            password="a-long-test-password",
        )

        with self.assertRaises(IntegrityError), transaction.atomic():
            user_model.objects.create_user(
                username="second",
                email="same@example.edu",
                password="another-long-test-password",
            )
