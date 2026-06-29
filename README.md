# crackeasy-cache

A simple flat-file JSON database of game repack metadata.

It updates automatically every few hours using GitHub Actions, so I don't really have to maintain it manually.

Used by **CrackEasy**: https://github.com/v7upsln/crackeasy

## Data Format

Each file inside metadata/ is a single JSON object containing the game's metadata.
```json
{
  "id": "ff5053007309344b933c84db810c8203",
  "title": "Game Title",
  "url": "https://example.com",
  "provider": "fitgirl",
  "original_size": "10 GB",
  "repack_size": "2 GB",
  "genres": [
    "Action",
    "RPG"
  ]
}
```
## Usage

Use it however you want.

- Parse it
- Fork it
- Build something with it
- Modify the scraper
- Change the format completely

If you end up using this project, I'd appreciate a small credit back to the original repository.

Big thanks to **FitGirl**.