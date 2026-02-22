import arxiv

# 1. Initialize the Client
# This allows you to define global settings like delay and retries
client = arxiv.Client(
  page_size = 100,
  delay_seconds = 3.0,
  num_retries = 3
)

# 2. Construct your Search object
search = arxiv.Search(
  query = 'all:"Hilbert curve"',
  max_results = 5,
  sort_by = arxiv.SortCriterion.SubmittedDate
)

# 3. Use client.results() instead of search.results()
results_generator = client.results(search)

for result in results_generator:
    print(f"ID: {result.entry_id}")
    print(f"Title: {result.title}")
    print(f"Published: {result.published}")
    print(f"PDF Link: {result.pdf_url}\n")
