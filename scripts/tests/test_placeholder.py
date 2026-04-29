def test_cloudflare_api_mock_returns_zone(mock_cloudflare_api, cloudflare_fixture_data):
    zones = mock_cloudflare_api.zones.list()

    assert zones == [cloudflare_fixture_data.zone]
