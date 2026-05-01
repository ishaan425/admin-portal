from services.settings import AppSettings


def test_settings_load_from_env_file(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "APP_ENV=production",
                "DATABASE_URL=postgresql://example/prod",
                "API_CORS_ORIGINS=https://admin.growqr.com,https://app.growqr.com",
                "AUTH_ALLOW_LOCAL_HEADERS=false",
            ]
        ),
        encoding="utf-8",
    )

    settings = AppSettings(_env_file=env_file)

    assert settings.is_production
    assert settings.database_url == "postgresql://example/prod"
    assert settings.cors_origin_list == [
        "https://admin.growqr.com",
        "https://app.growqr.com",
    ]
    assert settings.auth_allow_local_headers is False
