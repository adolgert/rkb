# Metadata Extraction Implementation Plan

## Overview
Implement multiple metadata extraction methods for academic PDFs, test them, and create an inspection script to compare outputs on the 30 most recent documents from ~/Zotero/storage.

## Target Metadata Fields
1. Type of document (article, inproceedings, report, book, presentation, notes, supplemental)
2. Title
3. Authors
4. Year
5. Journal/conference
6. Page count

## Output Format
Each PDF will show:
- Line 1: `first_author, "title"`
- Line 2: `year, document_type, journal, page_count`

## Implementation Phases

### Phase 1: Core Metadata Extractors
Location: `rkb/extractors/metadata/`

#### 1.1 PDF Metadata Extractor (`pdf_metadata.py`)
- Use PyPDF2 to extract built-in PDF metadata
- Extract: title, author, creation_date, creator, subject
- Use PyPDF2/pymupdf to count pages
- Return: dict with available fields, mark missing as None
- Document type: unknown (not in PDF metadata)
- **Tests**: `tests/unit/test_extractors/test_metadata/test_pdf_metadata.py`
  - Test with PDF having complete metadata
  - Test with PDF having partial metadata
  - Test with PDF having no metadata
  - Test page count accuracy

#### 1.2 Filename Heuristics Extractor (`filename_extractor.py`)
- Parse patterns from filename:
  - arXiv format: `(\d{4})\.(\d+)v(\d+)` → extract year
  - Year pattern: `(19|20)\d{2}`
  - Author pattern: `^([A-Z][a-z]+)` at start of filename
- Return: dict with extracted fields
- Document type: unknown
- **Tests**: `tests/unit/test_extractors/test_metadata/test_filename_extractor.py`
  - Test arXiv filename patterns
  - Test author-year patterns
  - Test edge cases and malformed filenames

#### 1.3 First Page Parser (`first_page_parser.py`)
- Use pymupdf to extract first page text with font information
- Pattern matching:
  - Title: first 1-3 lines, usually largest font
  - Authors: name patterns (Firstname Lastname, F. Lastname)
  - Year: 4-digit patterns `\d{4}` in header/footer
  - Venue: journal/conference patterns
- Return: dict with extracted fields
- Document type: unknown
- **Tests**: `tests/unit/test_extractors/test_metadata/test_first_page_parser.py`
  - Test typical academic paper layouts
  - Test different formatting styles
  - Test papers with unusual layouts

#### 1.4 GROBID Extractor (`grobid_extractor.py`)
- POST PDF to `http://172.17.0.1:8070/api/processHeaderDocument`
- Parse XML response for:
  - Title, authors, affiliations
  - Publication venue, year
  - Abstract, keywords (store but don't display)
- Return: dict with extracted fields including document type if available
- Document type: use GROBID's type if provided, else unknown
- **Tests**: `tests/unit/test_extractors/test_metadata/test_grobid_extractor.py`
  - Test successful extraction
  - Test GROBID service unavailable (mock)
  - Test malformed XML response
  - Test timeout handling

#### 1.5 DOI Extractor + CrossRef Lookup (`doi_crossref.py`)
- Extract DOI from first few pages: pattern `10\.\d+\/[^\s]+`
- If DOI found, query CrossRef API: `https://api.crossref.org/works/{doi}`
- Parse JSON response for:
  - Title, authors, year
  - Publication venue (container-title)
  - Document type (article, proceedings, etc.)
- Return: dict with extracted fields
- Document type: use CrossRef type if available
- **Tests**: `tests/unit/test_extractors/test_metadata/test_doi_crossref.py`
  - Test DOI extraction from text
  - Test CrossRef API lookup (mock)
  - Test API failure handling
  - Test missing DOI handling

### Phase 2: Metadata Models and Utilities
Location: `rkb/extractors/metadata/`

#### 2.1 Metadata Models (`models.py`)
- Define `DocumentMetadata` dataclass:
  ```python
  @dataclass
  class DocumentMetadata:
      doc_type: Optional[str] = None  # article, inproceedings, etc.
      title: Optional[str] = None
      authors: Optional[List[str]] = None
      year: Optional[int] = None
      journal: Optional[str] = None
      page_count: Optional[int] = None
      extractor: str = ""  # name of extractor that produced this
  ```
- **Tests**: Basic validation tests

#### 2.2 Base Extractor Interface (`base.py`)
- Abstract base class for all metadata extractors:
  ```python
  class MetadataExtractor(ABC):
      @abstractmethod
      def extract(self, pdf_path: Path) -> DocumentMetadata:
          pass

      @property
      @abstractmethod
      def name(self) -> str:
          pass
  ```
- **Tests**: Interface compliance tests

### Phase 3: Inspection Script
Location: `rkb/cli/inspect_metadata.py` (standalone script, not integrated with CLI)

#### 3.1 Script Features
- Walk ~/Zotero/storage directory tree for PDFs
- Find 30 most recent PDFs by modification time
- For each PDF:
  1. Run all 5 extractors
  2. Format output as specified
  3. Print file:// link as header
  4. Print one line per extractor with results
- Handle errors gracefully (log and continue)
- Progress indicator for user feedback

#### 3.2 Output Format
```
file:///home/user/Zotero/storage/ABC123/paper.pdf

[pdf_metadata]      Smith, "Machine Learning Applications"
                    2023, unknown, unknown, 15

[filename]          Smith, unknown
                    2023, unknown, unknown, unknown

[first_page]        Smith et al., "Machine Learning Applications"
                    2023, unknown, Journal of AI, unknown

[grobid]            Smith, J., "Machine Learning Applications in Healthcare"
                    2023, article, Journal of AI Research, 15

[doi_crossref]      Smith, J., "Machine Learning Applications in Healthcare"
                    2023, journal-article, Journal of AI Research, unknown
```

#### 3.3 Script Arguments
- `--limit N`: Process N documents (default: 30)
- `--dir PATH`: Directory to scan (default: ~/Zotero/storage)
- `--output FILE`: Save to file instead of stdout

**Tests**: `tests/integration/test_inspect_metadata.py`
- Test directory walking
- Test with sample PDFs
- Test error handling
- Test output formatting

### Phase 4: Testing and Validation

#### 4.1 Unit Tests
- Each extractor has comprehensive unit tests
- Mock external services (GROBID, CrossRef)
- Test edge cases and error conditions
- Coverage target: >90%

#### 4.2 Integration Tests
- Test extractors on real sample PDFs
- Test inspection script end-to-end
- Verify all extractors can be run sequentially

#### 4.3 Quality Checks
- Run `pytest` - all tests pass
- Run `ruff check` - no linting errors
- Run `lint-imports` - no layer violations

## Dependencies to Add
- PyPDF2 (or pymupdf if not already present)
- requests (for CrossRef API)
- lxml (for GROBID XML parsing)

## Success Criteria
1. All 5 extractors implemented and tested
2. All tests pass (pytest)
3. No linting errors (ruff check)
4. No import violations (lint-imports)
5. Inspection script runs successfully on Zotero storage
6. Output is human-readable and follows specified format
7. Handles errors gracefully (missing PDFs, API failures, etc.)

## Notes
- Start with local extractors (pdf_metadata, filename, first_page)
- Test GROBID connectivity before implementing extractor
- CrossRef API has rate limits - be respectful during testing
- Document type field may be "unknown" for many extractors
- Page count should always be available from PyPDF2/pymupdf
