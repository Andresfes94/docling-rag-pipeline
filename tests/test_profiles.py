from __future__ import annotations

from src.ingestion.profiles import load_profiles, list_profiles, create_converter


class TestProfiles:
    def test_load_all_profiles(self, profiles_path):
        profiles = load_profiles(profiles_path)
        assert len(profiles) >= 6
        assert "standard" in profiles
        assert "ocr_easyocr" in profiles
        assert "vlm_granite" in profiles

    def test_list_profiles(self, profiles_path):
        profiles = list_profiles(profiles_path)
        names = [p["name"] for p in profiles]
        assert "standard" in names
        assert all("description" in p for p in profiles)

    def test_create_standard_converter(self, profiles_path):
        converter = create_converter("standard", profiles_path=profiles_path)
        assert converter is not None

    def test_create_ocr_converter(self, profiles_path):
        converter = create_converter("ocr_easyocr", profiles_path=profiles_path)
        assert converter is not None

    def test_create_vlm_converter(self, profiles_path):
        converter = create_converter("vlm_granite", profiles_path=profiles_path)
        assert converter is not None

    def test_unknown_profile_raises(self, profiles_path):
        import pytest
        with pytest.raises(ValueError, match="Unknown profile"):
            create_converter("nonexistent", profiles_path=profiles_path)

    def test_missing_profiles_file(self):
        import pytest
        with pytest.raises(FileNotFoundError):
            load_profiles("/nonexistent/path/profiles.yaml")
