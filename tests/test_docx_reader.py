from zipfile import ZipFile

from docx_reader import read_docx_blocks


def test_word_localized_style_and_cell_paragraphs_are_preserved(tmp_path):
    path = tmp_path / "manual.docx"
    ns = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    with ZipFile(path, "w") as archive:
        archive.writestr("word/styles.xml", f'<w:styles xmlns:w="{ns}"><w:style w:styleId="1"><w:name w:val="heading 1"/></w:style></w:styles>')
        archive.writestr("word/document.xml", f'''<w:document xmlns:w="{ns}"><w:body>
          <w:tbl><w:tr><w:tc>
            <w:p><w:pPr><w:pStyle w:val="1"/></w:pPr><w:r><w:t>Title</w:t></w:r></w:p>
            <w:p><w:r><w:t>Paragraph</w:t></w:r></w:p>
          </w:tc></w:tr></w:tbl>
          <w:tbl><w:tr><w:tc><w:p><w:r><w:t>A</w:t></w:r></w:p><w:p><w:r><w:t>B</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>C</w:t></w:r></w:p></w:tc></w:tr></w:tbl>
        </w:body></w:document>''')
    blocks = read_docx_blocks(str(path))
    assert blocks[0] == {"type": "heading", "level": 2, "text": "Title"}
    assert blocks[1] == {"type": "paragraph", "text": "Paragraph"}
    assert blocks[2]["header"] == ["A\nB", "C"]
