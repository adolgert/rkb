"""Tests for XMP metadata extractor."""

from rkb.extractors.metadata.xmp import XMPExtractor


def test_parse_xmp_with_title_and_authors():
    """Parse XMP with Dublin Core title and creators."""
    xml = """\
<?xml version="1.0" encoding="UTF-8"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/">
  <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
           xmlns:dc="http://purl.org/dc/elements/1.1/">
    <rdf:Description>
      <dc:title>
        <rdf:Alt><rdf:li>My Paper Title</rdf:li></rdf:Alt>
      </dc:title>
      <dc:creator>
        <rdf:Seq>
          <rdf:li>Alice Smith</rdf:li>
          <rdf:li>Bob Jones</rdf:li>
        </rdf:Seq>
      </dc:creator>
    </rdf:Description>
  </rdf:RDF>
</x:xmpmeta>"""
    ext = XMPExtractor()
    result = ext._parse_xmp(xml)
    assert result.metadata.title == "My Paper Title"
    assert result.metadata.authors == ["Alice Smith", "Bob Jones"]
    assert result.doi is None
    assert result.arxiv_id is None


def test_parse_xmp_with_arxiv_identifier():
    """Parse XMP with arXiv URL in dc:identifier."""
    xml = """\
<?xml version="1.0" encoding="UTF-8"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/">
  <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
           xmlns:dc="http://purl.org/dc/elements/1.1/">
    <rdf:Description>
      <dc:title>
        <rdf:Alt><rdf:li>ArXiv Paper</rdf:li></rdf:Alt>
      </dc:title>
      <dc:identifier>http://arxiv.org/abs/2301.12345</dc:identifier>
    </rdf:Description>
  </rdf:RDF>
</x:xmpmeta>"""
    ext = XMPExtractor()
    result = ext._parse_xmp(xml)
    assert result.metadata.title == "ArXiv Paper"
    assert result.arxiv_id == "2301.12345"


def test_parse_xmp_with_doi_identifier():
    """Parse XMP with DOI in dc:identifier."""
    xml = """\
<?xml version="1.0" encoding="UTF-8"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/">
  <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
           xmlns:dc="http://purl.org/dc/elements/1.1/">
    <rdf:Description>
      <dc:identifier>10.1234/test.5678</dc:identifier>
    </rdf:Description>
  </rdf:RDF>
</x:xmpmeta>"""
    ext = XMPExtractor()
    result = ext._parse_xmp(xml)
    assert result.doi == "10.1234/test.5678"


def test_parse_xmp_empty():
    """Parse empty/minimal XMP returns empty metadata."""
    xml = '<?xml version="1.0"?><x:xmpmeta xmlns:x="adobe:ns:meta/"/>'
    ext = XMPExtractor()
    result = ext._parse_xmp(xml)
    assert result.metadata.title is None
    assert result.metadata.authors is None


def test_parse_xmp_invalid_xml():
    """Invalid XML returns empty result."""
    ext = XMPExtractor()
    result = ext._parse_xmp("not xml at all")
    assert result.metadata.title is None
