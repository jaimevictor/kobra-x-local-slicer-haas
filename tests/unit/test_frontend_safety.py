from pathlib import Path


def test_ingress_frontend_does_not_insert_external_data_as_html():
    source = (
        Path(__file__).parents[2]
        / "kobra_x_local_slicer"
        / "app"
        / "static"
        / "app.js"
    ).read_text(encoding="utf-8")

    assert "innerHTML" not in source
    assert "textContent" in source
    assert "createElement" in source
