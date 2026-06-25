# Travel Buddy

A real-time, multi-agent travel assistant — think of it as a **Jarvis for your trip**. Instead of a single chatbot that answers static questions, Travel Buddy is built as a set of cooperating subagents that continuously reason about how your trip is actually going, and proactively trigger actions or recommendations as conditions change.

## The Idea

Most travel apps are static: you book once, get an itinerary, and that's it. Travel Buddy is meant to be **dynamic and situational** — it watches multiple signals about your trip in real time and adapts.

Example: if you tell it *"this place is too far,"* it shouldn't just acknowledge that — it should immediately go look for nearby alternatives that still match what you were trying to do.

The goal is a system that can weigh several factors at once — money, distance, time, mood/preferences — and proactively recommend a next best action, the way a human travel companion would.

## Subagents (planned)

The system is organized as a set of focused subagents, coordinated by an orchestrator:

- **Finance Agent** — tracks running spend vs. budget, flags overspending, suggests cheaper alternatives (stays, transport, activities) when you're trending over budget.
- **Location/Proximity Agent** — knows your current location vs. planned stops; re-ranks or swaps recommendations when something is too far, traffic is bad, or you've gone off-route.
- **Stays Agent** — recommends accommodation based on current plans, budget remaining, and location, and re-recommends if plans shift.
- **Itinerary/Alternatives Agent** — when something falls through (closed, too far, too expensive, weather), proposes alternate options that fit the same time slot and intent.
- **Orchestrator/Decision Agent** — the "Jarvis" layer that takes signals from all subagents, resolves conflicts (e.g., budget vs. proximity), and decides what to actually surface to the user and when.

This list will evolve as the project develops — agents may be split further (e.g., weather, local events) or merged depending on how the system is built.

## Data Sources

Currently scraping travel content for inspiration and place data:
- **Lonely Planet** (`/articles` hub — note: `/search` is blocked by their robots.txt, so crawling goes through article hub pages and individual `/articles/<slug>` pages instead)
- **Thrillophilia** (`/places-to-visit-in-europe` — includes structured fields like Country, Best Time to Visit, Suggested Duration, used for season-based filtering)

See `src/1_crawl.py` for the current scraper.

## Project Status

🚧 Early stage. Currently building out:
- [x] Web crawlers for travel content (Lonely Planet, Thrillophilia)
- [ ] Subagent architecture / orchestration logic
- [ ] Real-time location tracking integration
- [ ] Budget/finance tracking
- [ ] Recommendation engine for "find nearby alternative" type requests
- [ ] User-facing interface (chat? mobile? TBD)

## Setup

```bash
# Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate   # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run the crawler
python src/1_crawl.py
```

## Project Structure

```
travel_buddy/
├── src/
│   └── 1_crawl.py       # Scrapes Lonely Planet + Thrillophilia for Europe travel content
├── requirements.txt
├── .gitignore
└── README.md
```

## Notes

This is a personal/learning project exploring multi-agent system design applied to real-world trip planning. Contributions, ideas, and feedback welcome as the architecture takes shape.
