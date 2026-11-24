"""Unit tests for ImageKitStorage and image validation/cleanup utilities."""

from io import BytesIO
from unittest.mock import MagicMock, patch

import requests
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase, override_settings
from PIL import Image

from catalog.image_storage import (
    MAX_IMAGE_BYTES,
    _cleanup_old_image,
    _require_durable_storage,
    _validate_image,
    delete_image,
    handle_image_deletion,
    handle_image_replacement,
    save_image,
)
from catalog.imagekit_storage import FILES_ENDPOINT, UPLOAD_ENDPOINT, ImageKitStorage
from catalog.models import Category


def _make_image_file(
    name="sample.png",
    size=(200, 200),
    fmt="PNG",
    content_type="image/png",
    color=(120, 80, 160),
):
    buf = BytesIO()
    img = Image.new("RGB", size, color=color)
    img.save(buf, format=fmt)
    return SimpleUploadedFile(name, buf.getvalue(), content_type=content_type)


def _mock_response(status_code=200, json_data=None, text=""):
    resp = MagicMock(spec=requests.Response)
    resp.status_code = status_code
    resp.text = text
    resp.json.return_value = json_data if json_data is not None else {}
    if status_code >= 400:
        resp.raise_for_status.side_effect = requests.HTTPError(
            f"{status_code} Error", response=resp
        )
    else:
        resp.raise_for_status.return_value = None
    return resp


@override_settings(
    IMAGEKIT_PRIVATE_KEY="  private_test_secret_key  ",
    IMAGEKIT_URL_ENDPOINT=" https://ik.imagekit.io/demo/ ",
)
class ImageKitStorageTests(SimpleTestCase):
    def setUp(self):
        self.storage = ImageKitStorage()

    def test_init_strips_whitespace_and_trailing_slash(self):
        self.assertEqual(self.storage.private_key, "private_test_secret_key")
        self.assertEqual(self.storage.url_endpoint, "https://ik.imagekit.io/demo")
        self.assertEqual(self.storage._auth, ("private_test_secret_key", ""))

    @patch("catalog.imagekit_storage.requests.post")
    def test_save_splits_folder_and_filename_and_uses_filepath(self, mock_post):
        mock_post.return_value = _mock_response(
            200,
            json_data={
                "fileId": "file_123",
                "name": "abc123.jpg",
                "filePath": "/categorys/abc123.jpg",
            },
        )
        upload = _make_image_file(
            name="abc123.jpg", fmt="JPEG", content_type="image/jpeg"
        )

        stored = self.storage._save("categorys/abc123.jpg", upload)

        self.assertEqual(stored, "categorys/abc123.jpg")
        mock_post.assert_called_once()
        _, kwargs = mock_post.call_args
        self.assertEqual(mock_post.call_args.args[0], UPLOAD_ENDPOINT)
        self.assertEqual(
            kwargs["data"],
            {
                "fileName": "abc123.jpg",
                "useUniqueFileName": "false",
                "folder": "/categorys",
            },
        )
        self.assertEqual(kwargs["files"]["file"][0], "abc123.jpg")
        self.assertEqual(kwargs["files"]["file"][2], "image/jpeg")
        self.assertEqual(kwargs["auth"], ("private_test_secret_key", ""))
        self.assertEqual(kwargs["timeout"], 60)

    @patch("catalog.imagekit_storage.requests.post")
    def test_save_root_level_file_omits_folder_param(self, mock_post):
        mock_post.return_value = _mock_response(
            200, json_data={"name": "plain.png"}
        )
        upload = _make_image_file(name="plain.png")

        stored = self.storage._save("plain.png", upload)

        self.assertEqual(stored, "plain.png")
        _, kwargs = mock_post.call_args
        self.assertEqual(
            kwargs["data"],
            {"fileName": "plain.png", "useUniqueFileName": "false"},
        )

    @patch("catalog.imagekit_storage.requests.post")
    def test_save_fallback_preserves_folder_when_filepath_missing(self, mock_post):
        mock_post.return_value = _mock_response(
            200, json_data={"name": "item.png"}
        )
        upload = _make_image_file(name="item.png")

        stored = self.storage._save("products/item.png", upload)
        self.assertEqual(stored, "products/item.png")

    @patch("catalog.imagekit_storage.requests.post")
    def test_save_http_errors_log_sanitized_body_without_secret(self, mock_post):
        for status_code in (401, 403, 500):
            with self.subTest(status_code=status_code):
                mock_post.return_value = _mock_response(
                    status_code,
                    text=(
                        f'{{"message":"Denied for private_test_secret_key","code":{status_code}}}'
                    ),
                )
                upload = _make_image_file(name="fail.png")
                with (
                    self.assertLogs("catalog.imagekit_storage", level="ERROR") as logs,
                    self.assertRaises(requests.HTTPError),
                ):
                    self.storage._save("categorys/fail.png", upload)

                joined = "\n".join(logs.output)
                self.assertIn(f"status={status_code}", joined)
                self.assertIn("categorys/fail.png", joined)
                self.assertNotIn("private_test_secret_key", joined)
                self.assertIn("[REDACTED]", joined)

    @patch("catalog.imagekit_storage.requests.post")
    def test_save_timeout_propagates(self, mock_post):
        mock_post.side_effect = requests.Timeout("upload timed out")
        upload = _make_image_file(name="slow.png")
        with self.assertRaises(requests.Timeout):
            self.storage._save("products/slow.png", upload)

    def test_url_preserves_slashes_and_quotes_special_chars(self):
        self.assertEqual(
            self.storage.url("categorys/abc123.jpg"),
            "https://ik.imagekit.io/demo/categorys/abc123.jpg",
        )
        self.assertEqual(
            self.storage.url("/products/my image.png"),
            "https://ik.imagekit.io/demo/products/my%20image.png",
        )

    @patch("catalog.imagekit_storage.requests.get")
    def test_find_and_exists_with_folder_and_root(self, mock_get):
        mock_get.return_value = _mock_response(200, json_data=[{"fileId": "fid_1"}])

        self.assertEqual(self.storage._find("products/a.jpg"), "fid_1")
        mock_get.assert_called_with(
            FILES_ENDPOINT,
            params={"name": "a.jpg", "path": "/products"},
            auth=("private_test_secret_key", ""),
            timeout=30,
        )
        self.assertTrue(self.storage.exists("products/a.jpg"))

        mock_get.return_value = _mock_response(200, json_data=[])
        self.assertFalse(self.storage.exists("plain.jpg"))
        mock_get.assert_called_with(
            FILES_ENDPOINT,
            params={"name": "plain.jpg"},
            auth=("private_test_secret_key", ""),
            timeout=30,
        )

    @patch("catalog.imagekit_storage.requests.get")
    def test_find_returns_none_and_logs_on_non_200(self, mock_get):
        mock_get.return_value = _mock_response(403, text="Forbidden")
        with self.assertLogs("catalog.imagekit_storage", level="ERROR") as logs:
            self.assertIsNone(self.storage._find("categorys/a.jpg"))
        self.assertIn("status=403", "\n".join(logs.output))

    @patch("catalog.imagekit_storage.requests.delete")
    @patch("catalog.imagekit_storage.requests.get")
    def test_delete_found_and_not_found(self, mock_get, mock_delete):
        mock_get.return_value = _mock_response(200, json_data=[{"fileId": "fid_9"}])
        mock_delete.return_value = _mock_response(204)

        self.storage.delete("categorys/old.jpg")
        mock_delete.assert_called_once_with(
            f"{FILES_ENDPOINT}/fid_9",
            auth=("private_test_secret_key", ""),
            timeout=30,
        )

        mock_delete.reset_mock()
        mock_get.return_value = _mock_response(200, json_data=[])
        self.storage.delete("categorys/missing.jpg")
        mock_delete.assert_not_called()

    @patch("catalog.imagekit_storage.requests.delete")
    @patch("catalog.imagekit_storage.requests.get")
    def test_delete_http_error_logs_and_raises(self, mock_get, mock_delete):
        mock_get.return_value = _mock_response(200, json_data=[{"fileId": "fid_9"}])
        mock_delete.return_value = _mock_response(500, text="Server Error")
        with (
            self.assertLogs("catalog.imagekit_storage", level="ERROR") as logs,
            self.assertRaises(requests.HTTPError),
        ):
            self.storage.delete("categorys/old.jpg")
        self.assertIn("status=500", "\n".join(logs.output))

    @patch.object(ImageKitStorage, "exists")
    def test_get_available_name_skips_exists(self, mock_exists):
        self.assertEqual(
            self.storage.get_available_name("products/uuid.jpg"), "products/uuid.jpg"
        )
        mock_exists.assert_not_called()

    def test_size_and_open_not_implemented(self):
        with self.assertRaises(NotImplementedError):
            self.storage.size("products/uuid.jpg")
        with self.assertRaises(NotImplementedError):
            self.storage.open("products/uuid.jpg")


class ImageValidationTests(SimpleTestCase):
    def test_valid_jpeg_png_webp_pass_and_seek_zero(self):
        cases = [
            ("photo.jpg", "JPEG", "image/jpeg"),
            ("photo.jpeg", "JPEG", "image/jpeg"),
            ("photo.png", "PNG", "image/png"),
            ("photo.webp", "WEBP", "image/webp"),
        ]
        for filename, fmt, ctype in cases:
            with self.subTest(filename=filename):
                upload = _make_image_file(
                    name=filename, size=(200, 200), fmt=fmt, content_type=ctype
                )
                _validate_image(upload)
                self.assertEqual(upload.tell(), 0)

    def test_invalid_extensions_rejected(self):
        for filename in ("anim.gif", "vector.svg", "malware.exe"):
            with self.subTest(filename=filename):
                upload = SimpleUploadedFile(
                    filename, b"fakebytes", content_type="application/octet-stream"
                )
                with self.assertRaises(ValidationError):
                    _validate_image(upload)

    def test_oversized_file_rejected(self):
        upload = _make_image_file(name="big.png")
        upload.size = MAX_IMAGE_BYTES + 1
        with self.assertRaises(ValidationError):
            _validate_image(upload)

    def test_too_small_dimensions_rejected(self):
        upload = _make_image_file(name="tiny.png", size=(50, 50))
        with self.assertRaises(ValidationError):
            _validate_image(upload)

    def test_too_large_dimensions_rejected(self):
        upload = _make_image_file(name="huge.png", size=(4097, 200))
        with self.assertRaises(ValidationError):
            _validate_image(upload)

    def test_content_type_extension_mismatch_rejected(self):
        upload = _make_image_file(
            name="actually_png.jpg", fmt="PNG", content_type="image/png"
        )
        with self.assertRaises(ValidationError):
            _validate_image(upload)

    def test_corrupt_image_bytes_rejected(self):
        upload = SimpleUploadedFile(
            "broken.jpg", b"not-a-valid-image-payload", content_type="image/jpeg"
        )
        with self.assertRaises(ValidationError):
            _validate_image(upload)


class DurableStorageTests(SimpleTestCase):
    @override_settings(DEBUG=False, MEDIA_ROOT="/tmp/uploads", IMAGEKIT_PRIVATE_KEY="")
    def test_tmp_rejected_in_production_without_imagekit(self):
        with self.assertRaises(RuntimeError):
            _require_durable_storage()

    @override_settings(
        DEBUG=False, MEDIA_ROOT="/var/folders/uploads", IMAGEKIT_PRIVATE_KEY=""
    )
    def test_var_folders_rejected_in_production_without_imagekit(self):
        with self.assertRaises(RuntimeError):
            _require_durable_storage()

    @override_settings(
        DEBUG=False, MEDIA_ROOT="/tmp/uploads", IMAGEKIT_PRIVATE_KEY="private_ok"
    )
    def test_allowed_in_production_when_imagekit_configured(self):
        _require_durable_storage()

    @override_settings(DEBUG=True, MEDIA_ROOT="/tmp/uploads", IMAGEKIT_PRIVATE_KEY="")
    def test_allowed_in_debug_mode(self):
        _require_durable_storage()


class ImageStorageOperationsTests(TestCase):
    @patch("catalog.image_storage.default_storage")
    @override_settings(DEBUG=True)
    def test_save_image_handles_subdir_and_empty_subdir(self, mock_storage):
        mock_storage.save.side_effect = lambda path, _: path
        upload1 = _make_image_file(name="one.png")
        upload2 = _make_image_file(name="two.png")

        self.assertEqual(save_image(upload1, "products"), "products/one.png")
        self.assertEqual(save_image(upload2, ""), "two.png")

    @patch("catalog.image_storage.default_storage")
    def test_delete_image_behavior(self, mock_storage):
        delete_image("")
        mock_storage.exists.assert_not_called()

        mock_storage.exists.return_value = True
        delete_image("products/old.png")
        mock_storage.delete.assert_called_once_with("products/old.png")

        mock_storage.delete.reset_mock()
        mock_storage.exists.return_value = False
        delete_image("products/missing.png")
        mock_storage.delete.assert_not_called()

        mock_storage.exists.side_effect = OSError("boom")
        with self.assertLogs("catalog.image_storage", level="ERROR"):
            delete_image("products/err.png")

    @patch("catalog.image_storage.delete_image")
    @patch("catalog.image_storage.save_image")
    def test_handle_image_replacement_deletes_unreferenced_old_image(
        self, mock_save, mock_delete
    ):
        cat = Category.objects.create(
            name_ar="عطور", slug="perfumes", image="categorys/old.png"
        )
        mock_save.return_value = "categorys/new.png"
        new_file = _make_image_file(name="new.png")

        result = handle_image_replacement(cat, new_file)

        self.assertEqual(result, "categorys/new.png")
        cat.refresh_from_db()
        self.assertEqual(cat.image.name, "categorys/new.png")
        mock_delete.assert_called_once_with("categorys/old.png")

    @patch("catalog.image_storage.delete_image")
    @patch("catalog.image_storage.save_image")
    def test_handle_image_replacement_preserves_shared_old_image(
        self, mock_save, mock_delete
    ):
        cat1 = Category.objects.create(
            name_ar="عطور ١", slug="perfumes-1", image="categorys/shared.png"
        )
        Category.objects.create(
            name_ar="عطور ٢", slug="perfumes-2", image="categorys/shared.png"
        )
        mock_save.return_value = "categorys/new2.png"

        handle_image_replacement(cat1, _make_image_file(name="new2.png"))

        mock_delete.assert_not_called()

    @patch("catalog.image_storage.delete_image")
    @patch("catalog.image_storage.save_image")
    def test_handle_image_replacement_failure_keeps_db_and_old_image(
        self, mock_save, mock_delete
    ):
        cat = Category.objects.create(
            name_ar="بخور", slug="incense", image="categorys/keep.png"
        )
        mock_save.side_effect = requests.HTTPError("403 Forbidden")

        with (
            self.assertLogs("catalog.image_storage", level="ERROR"),
            self.assertRaises(requests.HTTPError),
        ):
            handle_image_replacement(cat, _make_image_file(name="bad.png"))

        cat.refresh_from_db()
        self.assertEqual(cat.image.name, "categorys/keep.png")
        mock_delete.assert_not_called()

    def test_handle_image_replacement_noop_when_no_file(self):
        cat = Category.objects.create(
            name_ar="عود", slug="oud", image="categorys/oud.png"
        )
        self.assertIsNone(handle_image_replacement(cat, None))

    @patch("catalog.image_storage.delete_image")
    def test_handle_image_deletion_and_cleanup_respect_references(self, mock_delete):
        cat_sole = Category.objects.create(
            name_ar="وحيد", slug="sole", image="categorys/sole.png"
        )
        # Even when called before cat_sole.delete(), exclude_pk allows deletion.
        handle_image_deletion(cat_sole)
        mock_delete.assert_called_once_with("categorys/sole.png")

        mock_delete.reset_mock()
        cat_a = Category.objects.create(
            name_ar="مشترك ١", slug="shared-a", image="categorys/shared_del.png"
        )
        Category.objects.create(
            name_ar="مشترك ٢", slug="shared-b", image="categorys/shared_del.png"
        )
        handle_image_deletion(cat_a)
        mock_delete.assert_not_called()

        # Same old_name and new_name is a no-op
        _cleanup_old_image("categorys/same.png", "categorys/same.png", Category)
        mock_delete.assert_not_called()
