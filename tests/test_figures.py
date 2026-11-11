from pathlib import Path

from ptp.figures import prepare_figures, write_fig_comments


def test_prepare_figures_renames_and_maps_captions(tmp_path: Path):
    source_images = tmp_path / "mineru" / "images"
    source_images.mkdir(parents=True)
    (source_images / "page_1_image_2.jpg").write_bytes(b"figure")
    (source_images / "page_1_equation_3.jpg").write_bytes(b"equation")

    structured = {
        "pages": [
            {
                "page_idx": 0,
                "blocks": [
                    {
                        "type": "image",
                        "image_source": "images/page_1_image_2.jpg",
                        "captions": [{"content": "Figure 1. Test figure."}],
                    },
                    {
                        "type": "equation",
                        "image_source": "images/page_1_equation_3.jpg",
                    },
                ],
            }
        ]
    }
    markdown = (
        "Text with a figure.\n\n![](images/page_1_image_2.jpg)\n\n"
        "And an equation ![](images/page_1_equation_3.jpg).\n"
    )

    output_images = tmp_path / "output" / "image"
    result = prepare_figures(structured, source_images, output_images, markdown)

    assert [figure.filename for figure in result.figures] == ["fig1.jpg"]
    assert result.figures[0].en_caption == "Figure 1. Test figure."
    assert "image/fig1.jpg" in result.markdown
    assert "image/page_1_equation_3.jpg" in result.markdown
    assert "images/" not in result.markdown
    assert (output_images / "fig1.jpg").exists()
    assert (output_images / "page_1_equation_3.jpg").exists()
    assert not (output_images / "page_1_image_2.jpg").exists()


def test_write_fig_comments_bilingual(tmp_path: Path):
    from ptp.figures import FigureEntry

    figures = [
        FigureEntry(
            filename="fig1.jpg",
            source="images/a.jpg",
            en_caption="Figure 1. English.",
            zh_caption="图 1. 中文。",
        )
    ]
    path = tmp_path / "fig_comments.txt"
    write_fig_comments(path, figures)
    text = path.read_text(encoding="utf-8")
    assert "fig1.jpg" in text
    assert "EN: Figure 1. English." in text
    assert "ZH: 图 1. 中文。" in text


def test_write_fig_comments_without_figures(tmp_path: Path):
    path = tmp_path / "fig_comments.txt"
    write_fig_comments(path, [])
    assert "No figure captions found" in path.read_text(encoding="utf-8")
