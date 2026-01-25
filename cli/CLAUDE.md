# CLI Module

Command-line interface entry points.

## Files

- `ask.py` - Rules Q&A CLI (`pfrules`)
- `server.py` - API server (`pfrules-server`)
- `vectordb.py` - Vector store management (`pfrules-vectordb`)
- `preprocess.py` - Preprocessing CLI (`pfrules-preprocess`)
- `db.py` - Database queries (`pfrules-db`)

## Commands

### pfrules
Ask rules questions:
```bash
poetry run pfrules "How does grappling work?"
poetry run pfrules -v                    # verbose
poetry run pfrules --timing              # show timing breakdown
poetry run pfrules --no-rerank           # disable reranking
poetry run pfrules --no-tools            # no follow-up searches
poetry run pfrules                       # interactive mode
```

### pfrules-vectordb
Manage the vector search index:
```bash
poetry run pfrules-vectordb --build      # build/rebuild index
poetry run pfrules-vectordb -q "grapple" # query
poetry run pfrules-vectordb              # show stats
```

### pfrules-preprocess
Process markdown into manifests:
```bash
poetry run pfrules-preprocess --stats    # show what would be processed
poetry run pfrules-preprocess --dry-run  # preview without API calls
poetry run pfrules-preprocess -v         # process all
poetry run pfrules-preprocess --category "Spells"  # specific category

# Markdown modification commands
poetry run pfrules-preprocess --list-modifications           # list configured modifications
poetry run pfrules-preprocess --preview-modifications URL    # preview changes for a URL
```

### pfrules-server
Run the FastAPI web server:
```bash
poetry run pfrules-server                # start on localhost:8000
poetry run pfrules-server --port 8080    # custom port
poetry run pfrules-server --host 0.0.0.0 # bind to all interfaces
poetry run pfrules-server --reload       # development mode with auto-reload
poetry run pfrules-server --workers 4    # multiple workers
```

### pfrules-db
Query the HTML cache database:
```bash
poetry run pfrules-db stats              # database statistics
poetry run pfrules-db get URL            # get markdown for URL
poetry run pfrules-db list               # list all URLs
poetry run pfrules-db search 'feats/%'   # search URLs
```
