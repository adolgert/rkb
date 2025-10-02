# Goals

We need document metadata because it helps us decide what to read from searches. The parts of the metadata
that are the most meaningful are:

 1. Type of document, such as: article, inproceedings, report, book, presentation, notes, supplemental.
 2. Title
 3. Authors
 4. Year
 5. Journal/conference
 6. Page count

This tool needs document metadata in order to succeed, but it is currently unclear how
to get good metadata and how to judge when the metadata is good.

I would like to implement several of the methods below as "extractors" of document metadata.
I would like then to run these extractors on articles that are in subdirectories of ~/Zotero/storage.
Then print results for human review. Print them as a list where the header is the file:// link to the document
and then below are a list of document descriptions, as a single line for each, with the 6 pieces
of information above, identified by the method of extraction.

We need to be conscious of resource limits when exploring document metadata extraction.

 - Limit queries to outside databases. These queries are very useful so they should be used, but sparingly during exploration.
 - Start with methods that don't query outside databases.


I think we may eventually collect document information using several methods and then
batch process them with an LLM that decides whether the metadata makes sense for the
information returned.

```bash
ollama run gemma2:9b-instruct-q4_K_M
```

There are several approaches for extracting metadata from academic PDFs, each with different strengths:

  1. PDF Metadata Fields (Built-in)

  import PyPDF2
  # or
  import pymupdf  # fitz

  def extract_pdf_metadata(pdf_path):
      with open(pdf_path, 'rb') as file:
          reader = PyPDF2.PdfReader(file)
          metadata = reader.metadata
          return {
              'title': metadata.get('/Title'),
              'author': metadata.get('/Author'),
              'subject': metadata.get('/Subject'),
              'creator': metadata.get('/Creator'),
              'creation_date': metadata.get('/CreationDate')
          }

  Pros: Fast, reliable when presentCons: Often missing or incomplete in academic PDFs

  2. Text-Based Extraction (First Page Parsing)

  def extract_first_page_metadata(pdf_path):
      # Extract first page text
      text = extract_first_page(pdf_path)

      # Pattern matching for common formats
      title = extract_title_from_text(text)  # Usually largest font/first lines
      authors = extract_authors(text)        # Look for name patterns
      year = extract_year(text)             # \d{4} patterns
      publication = extract_venue(text)      # Journal/conference patterns

  Patterns to look for:
  - Title: Usually first 1-3 lines, larger font
  - Authors: Names with academic affiliations
  - Year: 4-digit numbers, often in citations or headers
  - Venue: Journal names, conference acronyms

  3. Specialized Academic Libraries

  PyPaperBot / Scholarly

  from scholarly import scholarly

  def lookup_by_title(title):
      search_query = scholarly.search_pubs(title)
      return next(search_query, None)

  CrossRef API

  import requests

  def crossref_lookup(title, author=None):
      url = "https://api.crossref.org/works"
      params = {"query": title}
      if author:
          params["query.author"] = author
      response = requests.get(url, params=params)
      return response.json()

  4. Machine Learning Approaches

  GROBID (Most Robust for Academic Papers)

  # Setup GROBID server
  docker run -d -p 8070:8070 -e JAVA_TOOL_OPTIONS="-XX:-UseContainerSupport" lfoppiano/grobid:0.8.0
Summary:
  1. Run GROBID on host: docker run -d -p 8070:8070 lfoppiano/grobid:0.8.0
  2. Access from this container using http://host.docker.internal:8070 or http://172.17.0.1:8070
  3. Let me know when it's running and I'll implement the extractors
  
  # Extract structured metadata
  curl -X POST \
    -F "input=@paper.pdf" \
    http://localhost:8070/api/processHeaderDocument

  Returns structured XML with:
  - Title, authors, affiliations
  - Abstract, keywords
  - Publication venue, year
  - References

  Science Parse

  from science_parse import science_parse

  def extract_with_science_parse(pdf_path):
      result = science_parse(pdf_path)
      return {
          'title': result.get('title'),
          'authors': result.get('authors'),
          'year': result.get('year'),
          'venue': result.get('venue')
      }

  5. Nougat + LLM Extraction

  Since you already have Nougat extracting content:

  def extract_metadata_from_nougat(mmd_content):
      # Get first few paragraphs from .mmd file
      header = mmd_content[:2000]

      # Use LLM to parse structured metadata
      prompt = f"""
      Extract metadata from this academic paper header:
      
      {header}
      
      Return JSON with: title, authors, year, publication_venue
      """

      # Send to local LLM or OpenAI
      return parse_llm_response(prompt)

  6. DOI-Based Lookup

  import re
  import requests

  def extract_doi_and_lookup(text):
      # Find DOI in text
      doi_pattern = r'10\.\d+\/[^\s]+'
      doi = re.search(doi_pattern, text)

      if doi:
          # Lookup via CrossRef
          url = f"https://api.crossref.org/works/{doi.group()}"
          response = requests.get(url)
          return response.json()['message']

  7. Filename-Based Heuristics

  def extract_from_filename(filename):
      # Many academic PDFs encode metadata in filename
      # e.g., "Smith2023_MachineLearning_ICML.pdf"

      patterns = {
          'arxiv': r'(\d{4})\.(\d+)v(\d+)',  # 2301.12345v1
          'year': r'(19|20)\d{2}',
          'authors': r'^([A-Z][a-z]+)',
      }

      return parse_filename_patterns(filename, patterns)

  Recommended Hybrid Approach:

  def robust_metadata_extraction(pdf_path):
      results = {}

      # 1. Try PDF metadata first (fastest)
      pdf_meta = extract_pdf_metadata(pdf_path)
      results.update(pdf_meta)

      # 2. Parse first page for missing fields
      if not results.get('title'):
          first_page_meta = extract_first_page_metadata(pdf_path)
          results.update(first_page_meta)

      # 3. DOI lookup if available
      if doi := extract_doi(pdf_path):
          crossref_meta = crossref_lookup(doi)
          results.update(crossref_meta)

      # 4. GROBID for comprehensive extraction
      if still_missing_fields(results):
          grobid_meta = grobid_extract(pdf_path)
          results.update(grobid_meta)

      return results

  For your corpus, I'd recommend:
  1. GROBID for comprehensive academic metadata
  2. First-page parsing using your existing Nougat extractions
  3. CrossRef API for validation/enrichment

  This would integrate well with your existing pipeline and provide rich metadata for enhanced search and organization.
