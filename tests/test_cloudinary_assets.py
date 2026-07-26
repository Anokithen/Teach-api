"""Cloudinary asset tests use mocks only; no live network calls."""

import io
import os
import tempfile
import unittest
from itertools import count
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from flask_jwt_extended import create_access_token

from app import create_app
from app.config import Config
from app.extensions import db
from app.models.asset_model import Asset, USER_PROFILE_IMAGE
from app.models.book_model import Book
from app.models.child_model import Child
from app.models.parent_model import Parent, ROLE_ADMIN, ROLE_PARENT
from app.services.cloudinary_path_service import (
    get_book_video_folder,
    get_child_profile_folder,
    get_generated_book_audio_folder,
    get_user_profile_folder,
    get_voice_profile_folder,
    sanitize_folder_segment,
)
from app.services.cloudinary_service import upload_asset


PNG = b"\x89PNG\r\n\x1a\n" + b"\0" * 64
MP4 = b"\0\0\0\x18ftypisom" + b"\0" * 64
WAV = b"RIFF" + b"\0\0\0\0" + b"WAVEfmt " + b"\0" * 64


class PathServiceTests(unittest.TestCase):
    def test_folder_mappings_include_ids(self):
        self.assertEqual(get_user_profile_folder(7), "teachalike/7/Image/Profile")
        self.assertEqual(
            get_child_profile_folder(7, 4, "Sam Lee"),
            "teachalike/7/Image/Children_profile/4_sam_lee",
        )
        self.assertEqual(
            get_voice_profile_folder(7), "teachalike/7/Audio/Voice_profiles"
        )
        self.assertEqual(
            get_generated_book_audio_folder(7, 9, "A Book"),
            "teachalike/7/Audio/Generated_Books_Audio/9_a_book",
        )
        self.assertEqual(
            get_book_video_folder(7, 2, 9, "A Book"),
            "teachalike/7/Video/2/9_a_book",
        )

    def test_sanitization_blocks_traversal_and_caps_length(self):
        result = sanitize_folder_segment("../../A\\B / C")
        self.assertNotIn("..", result)
        self.assertNotIn("/", result)
        self.assertNotIn("\\", result)
        self.assertEqual(result, "a_b_c")
        self.assertLessEqual(len(sanitize_folder_segment("x" * 500)), 80)
        self.assertEqual(sanitize_folder_segment("///"), "unnamed")

    def test_duplicate_names_still_have_distinct_paths(self):
        self.assertNotEqual(
            get_child_profile_folder(1, 10, "Alex"),
            get_child_profile_folder(1, 11, "Alex"),
        )
        self.assertNotEqual(
            get_generated_book_audio_folder(1, 10, "Same"),
            get_generated_book_audio_folder(1, 11, "Same"),
        )


class AssetEndpointTests(unittest.TestCase):
    def setUp(self):
        handle, self.database_path = tempfile.mkstemp(suffix=".sqlite")
        os.close(handle)
        Config.SQLALCHEMY_DATABASE_URI = f"sqlite:///{self.database_path}"
        Config.SQLALCHEMY_ENGINE_OPTIONS = {}
        Config.CLOUDINARY_CLOUD_NAME = "test"
        Config.CLOUDINARY_API_KEY = "test"
        Config.CLOUDINARY_API_SECRET = "test"
        self.app = create_app()
        self.app.config.update(TESTING=True)
        self.context = self.app.app_context()
        self.context.push()
        db.drop_all()
        db.create_all()
        self.owner = Parent(
            name="Owner", email="owner@example.test", password="hash", role=ROLE_PARENT
        )
        self.other = Parent(
            name="Other", email="other@example.test", password="hash", role=ROLE_PARENT
        )
        self.admin = Parent(
            name="Admin", email="admin@example.test", password="hash", role=ROLE_ADMIN
        )
        db.session.add_all([self.owner, self.other, self.admin])
        db.session.flush()
        self.child = Child(
            parent_id=self.owner.id,
            created_by_id=self.owner.id,
            name="Same Name",
            age=8,
        )
        self.book = Book(title="Same Name", age_group="7-9")
        db.session.add_all([self.child, self.book])
        db.session.commit()
        self.client = self.app.test_client()
        self.ids = count(1)

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()
        os.unlink(self.database_path)

    def _headers(self, user):
        return {"Authorization": f"Bearer {create_access_token(identity=user.id)}"}

    def _upload_result(self, _file, folder, resource_type="auto", public_id=None, **_kwargs):
        number = next(self.ids)
        return {
            "asset_id": f"asset-{number}",
            "public_id": public_id or f"unique-{number}",
            "secure_url": f"https://res.cloudinary.test/{number}",
            "resource_type": resource_type,
            "delivery_type": "upload",
            "format": "png" if resource_type == "image" else "mp4",
            "bytes": 72,
            "width": 10 if resource_type != "raw" else None,
            "height": 10 if resource_type != "raw" else None,
            "duration": 1.5 if resource_type == "video" else None,
            "asset_folder": folder,
            "original_filename": "upload",
        }

    @patch("app.controllers.asset_controller.upload_asset")
    def test_profile_upload_and_replacement(self, upload):
        upload.side_effect = self._upload_result
        for _ in range(2):
            response = self.client.post(
                "/api/assets/profile-image",
                headers=self._headers(self.owner),
                data={"file": (io.BytesIO(PNG), "photo.png")},
                content_type="multipart/form-data",
            )
            self.assertEqual(response.status_code, 201, response.json)
        self.assertEqual(
            Asset.query.filter_by(owner_user_id=self.owner.id, deleted_at=None).count(),
            1,
        )
        self.assertTrue(upload.call_args.kwargs["public_id"].endswith("/profile"))

    @patch("app.controllers.asset_controller.upload_asset")
    def test_same_filename_different_users_has_distinct_public_ids(self, upload):
        upload.side_effect = self._upload_result
        public_ids = []
        for user in (self.owner, self.other):
            response = self.client.post(
                "/api/assets/profile-image",
                headers=self._headers(user),
                data={"file": (io.BytesIO(PNG), "same.png")},
                content_type="multipart/form-data",
            )
            self.assertEqual(response.status_code, 201, response.json)
            public_ids.append(upload.call_args.kwargs["public_id"])
        self.assertNotEqual(*public_ids)

    @patch("app.controllers.asset_controller.delete_asset")
    @patch("app.controllers.asset_controller.upload_asset")
    def test_child_rename_replacement_cleans_previous_public_id(
        self, upload, destroy
    ):
        upload.side_effect = self._upload_result
        first = self.client.post(
            f"/api/assets/children/{self.child.id}/profile-image",
            headers=self._headers(self.owner),
            data={"file": (io.BytesIO(PNG), "photo.png")},
            content_type="multipart/form-data",
        )
        self.assertEqual(first.status_code, 201, first.json)
        old_public_id = db.session.get(
            Asset, first.json["data"]["id"]
        ).cloudinary_public_id
        self.child.name = "Renamed Child"
        db.session.commit()
        second = self.client.post(
            f"/api/assets/children/{self.child.id}/profile-image",
            headers=self._headers(self.owner),
            data={"file": (io.BytesIO(PNG), "photo.png")},
            content_type="multipart/form-data",
        )
        self.assertEqual(second.status_code, 201, second.json)
        new_public_id = db.session.get(
            Asset, second.json["data"]["id"]
        ).cloudinary_public_id
        self.assertNotEqual(old_public_id, new_public_id)
        destroy.assert_called_once()

    def test_bad_type_returns_415(self):
        response = self.client.post(
            "/api/assets/profile-image",
            headers=self._headers(self.owner),
            data={"file": (io.BytesIO(b"not an image"), "bad.txt")},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 415)

    def test_oversized_upload_returns_413(self):
        self.app.config["MAX_PROFILE_IMAGE_SIZE_MB"] = 0
        response = self.client.post(
            "/api/assets/profile-image",
            headers=self._headers(self.owner),
            data={"file": (io.BytesIO(PNG), "photo.png")},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 413)

    @patch("app.controllers.asset_controller.upload_asset")
    def test_child_ownership_is_enforced(self, upload):
        upload.side_effect = self._upload_result
        response = self.client.post(
            f"/api/assets/children/{self.child.id}/profile-image",
            headers=self._headers(self.other),
            data={"file": (io.BytesIO(PNG), "photo.png")},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 403)
        upload.assert_not_called()

    @patch("app.controllers.asset_controller.upload_asset")
    def test_cloudinary_failure_is_sanitized(self, upload):
        from app.services.cloudinary_service import CloudinaryUploadError

        upload.side_effect = CloudinaryUploadError("sdk secret detail")
        response = self.client.post(
            "/api/assets/profile-image",
            headers=self._headers(self.owner),
            data={"file": (io.BytesIO(PNG), "photo.png")},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("sdk secret detail", response.get_data(as_text=True))

    @patch("app.controllers.asset_controller.delete_asset")
    @patch("app.controllers.asset_controller.upload_asset")
    def test_initial_profile_database_failure_cleans_upload(
        self, upload, destroy
    ):
        from sqlalchemy.exc import SQLAlchemyError

        upload.side_effect = self._upload_result
        with patch.object(db.session, "commit", side_effect=SQLAlchemyError("db down")):
            response = self.client.post(
                "/api/assets/profile-image",
                headers=self._headers(self.owner),
                data={"file": (io.BytesIO(PNG), "photo.png")},
                content_type="multipart/form-data",
            )
        self.assertEqual(response.status_code, 500)
        destroy.assert_called_once()

    @patch("app.controllers.asset_controller.delete_asset")
    @patch("app.controllers.asset_controller.upload_asset")
    def test_replacement_database_failure_preserves_confirmed_replacement(
        self, upload, destroy
    ):
        from sqlalchemy.exc import SQLAlchemyError

        upload.side_effect = self._upload_result
        first = self.client.post(
            "/api/assets/profile-image",
            headers=self._headers(self.owner),
            data={"file": (io.BytesIO(PNG), "first.png")},
            content_type="multipart/form-data",
        )
        self.assertEqual(first.status_code, 201, first.json)
        with patch.object(db.session, "commit", side_effect=SQLAlchemyError("db down")):
            second = self.client.post(
                "/api/assets/profile-image",
                headers=self._headers(self.owner),
                data={"file": (io.BytesIO(PNG), "second.png")},
                content_type="multipart/form-data",
            )
        self.assertEqual(second.status_code, 500)
        destroy.assert_not_called()

    @patch("app.controllers.asset_controller.upload_asset")
    def test_voice_and_narration_upload_endpoints(self, upload):
        upload.side_effect = self._upload_result
        voice_response = self.client.post(
            "/api/assets/voice-profiles",
            headers=self._headers(self.owner),
            data={"file": (io.BytesIO(WAV), "voice.wav"), "label": "My voice"},
            content_type="multipart/form-data",
        )
        self.assertEqual(voice_response.status_code, 201, voice_response.json)
        voice_id = voice_response.json["data"]["voice_profile_id"]
        narration_response = self.client.post(
            f"/api/assets/books/{self.book.id}/narrations",
            headers=self._headers(self.owner),
            data={
                "file": (io.BytesIO(WAV), "narration.wav"),
                "voice_profile_id": str(voice_id),
            },
            content_type="multipart/form-data",
        )
        self.assertEqual(
            narration_response.status_code, 201, narration_response.json
        )
        self.assertIsNotNone(narration_response.json["data"]["generation_id"])

    @patch("app.controllers.asset_controller.upload_asset")
    def test_admin_video_upload_validates_book(self, upload):
        upload.side_effect = self._upload_result
        missing = self.client.post(
            "/api/admin/books/999/videos",
            headers=self._headers(self.admin),
            data={"file": (io.BytesIO(MP4), "video.mp4")},
            content_type="multipart/form-data",
        )
        self.assertEqual(missing.status_code, 404)
        response = self.client.post(
            f"/api/admin/books/{self.book.id}/videos",
            headers=self._headers(self.admin),
            data={"file": (io.BytesIO(MP4), "video.mp4")},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 201, response.json)

    def test_legacy_book_media_endpoint_rejects_unscoped_video(self):
        response = self.client.post(
            "/api/admin/book-media",
            headers=self._headers(self.admin),
            data={
                "file": (io.BytesIO(MP4), "video.mp4"),
                "media_type": "video",
            },
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 422, response.json)

    @patch("app.services.cloudinary_service._cloudinary_modules")
    def test_authenticated_delivery_option_reaches_sdk(self, modules):
        uploader = MagicMock()
        uploader.upload.return_value = {
            "asset_id": "sdk-asset",
            "public_id": "voice_profile_1",
            "secure_url": "https://res.cloudinary.test/authenticated/file.wav",
            "resource_type": "video",
            "type": "authenticated",
            "asset_folder": "teachalike/1/Audio/Voice_profiles",
        }
        modules.return_value = SimpleNamespace(
            config=MagicMock(), uploader=uploader
        )
        result = upload_asset(
            io.BytesIO(WAV),
            "teachalike/1/Audio/Voice_profiles",
            resource_type="video",
            public_id="voice_profile_1",
            delivery_type="authenticated",
        )
        self.assertEqual(result["delivery_type"], "authenticated")
        self.assertEqual(
            uploader.upload.call_args.kwargs["type"], "authenticated"
        )

    def test_cross_user_asset_read_is_hidden(self):
        asset = Asset(
            owner_user_id=self.owner.id,
            asset_category=USER_PROFILE_IMAGE,
            cloudinary_asset_id="asset-private",
            cloudinary_public_id="private",
            cloudinary_secure_url="https://example.test/private",
            cloudinary_resource_type="image",
            cloudinary_delivery_type="upload",
            cloudinary_asset_folder="teachalike/1/Image/Profile",
        )
        db.session.add(asset)
        db.session.commit()
        response = self.client.get(
            f"/api/assets/{asset.id}", headers=self._headers(self.other)
        )
        self.assertEqual(response.status_code, 404)

    @patch("app.controllers.asset_controller.delete_asset")
    def test_delete_is_idempotent_upstream_and_marks_row(self, destroy):
        destroy.return_value = "not found"
        asset = Asset(
            owner_user_id=self.owner.id,
            asset_category=USER_PROFILE_IMAGE,
            cloudinary_asset_id="asset-delete",
            cloudinary_public_id="delete-me",
            cloudinary_secure_url="https://example.test/delete",
            cloudinary_resource_type="image",
            cloudinary_delivery_type="upload",
            cloudinary_asset_folder="teachalike/1/Image/Profile",
        )
        db.session.add(asset)
        db.session.commit()
        response = self.client.delete(
            f"/api/assets/{asset.id}", headers=self._headers(self.owner)
        )
        self.assertEqual(response.status_code, 200, response.json)
        self.assertIsNotNone(db.session.get(Asset, asset.id).deleted_at)
        second = self.client.delete(
            f"/api/assets/{asset.id}", headers=self._headers(self.owner)
        )
        self.assertEqual(second.status_code, 200, second.json)
        destroy.assert_called_once()

    @patch("app.controllers.asset_controller.delete_asset")
    def test_profile_asset_delete_clears_related_account_fields(self, destroy):
        destroy.return_value = "ok"
        self.owner.profile_image_url = "https://example.test/profile"
        self.owner.profile_image_public_id = "profile-public-id"
        asset = Asset(
            owner_user_id=self.owner.id,
            asset_category=USER_PROFILE_IMAGE,
            active_slot=f"user:{self.owner.id}:profile",
            cloudinary_asset_id="asset-profile-delete",
            cloudinary_public_id="profile-public-id",
            cloudinary_secure_url="https://example.test/profile",
            cloudinary_resource_type="image",
            cloudinary_delivery_type="upload",
            cloudinary_asset_folder=f"teachalike/{self.owner.id}/Image/Profile",
        )
        db.session.add(asset)
        db.session.commit()
        response = self.client.delete(
            f"/api/assets/{asset.id}", headers=self._headers(self.owner)
        )
        self.assertEqual(response.status_code, 200, response.json)
        db.session.refresh(self.owner)
        self.assertIsNone(self.owner.profile_image_url)
        self.assertIsNone(self.owner.profile_image_public_id)
        self.assertIsNone(db.session.get(Asset, asset.id).active_slot)


if __name__ == "__main__":
    unittest.main()
