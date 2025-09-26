## AI Sports Event Finder Project

This is my project for finding sports events in Belgium. I was tired of checking a bunch of different websites, so I tried to make a bot that you can just ask questions in plain English (or Dutch) :) 

## What's in the Database?
For now, I've added these:
Football: Jupiler Pro League (Men), Lotto Super League (Women)
Basketball: BNXT League 2025-2026
Volleyball: Belgian Volley League (Women), Lotto Volley League (Men)

## Where is data obtained ? 
I used official websites of each competetions. Also I shared scrappers in repo.

Unfortunately, not all venue coordinates are accurate. Nominatim, which uses OpenStreetMap data, was employed. 
However, it did not provide the most accurate coordinates for all venues.
Still, upon skimming through the data, it can be said that most of them are correct.

What can you ask it?
You can ask it things like:
"Matches in Brussels this weekend?" 
"Are there any Pro League matches in Antwerp next week"
"What leagues are available?"
"Events near me tomorrow" (this works if you provide your location)

The bot tries to understand your question, figures out the dates and places, and finds the relevant matches from Belgian leagues in the database.

<img width="1037" height="632" alt="Screenshot 2025-09-26 at 20 49 12" src="https://github.com/user-attachments/assets/322edd09-c587-488b-98ab-0bcd9562a8d8" />

## Tech I Used
Cursor: It helped me a lot on fixing syntax errors and consturcting boilerplate code.
FastAPI: async, query validation
Pydantic: data validation, expecially refraining injections.
AsyncPG: Parameterized queries
Ollama: To run the llama3.1 model locally on my mac!
PostgreSQL + PostGIS: For storing the match and stadium locations on a map. PostGIS is for geo queries.
LangGraph: This helped me build a flowchart for the AI to decide what to do.
LangSmith:  Observability

## How it Works 
So when you ask something, first a small AI model (I'm using llama3.1 with Ollama) tries to figure out what you want. Like, are you looking for a place, a time, or a league? Then I ask the AI again to turn stuff like "next week" into actual dates like 2025-10-03. Once it has the location (it geocodes it), it uses all that info to search the PostGIS database.

I connected all these steps together using LangGraph. Each step is a "node", so the AI doesn't get confused about what to do next.

Getting it to run

Option 1: Docker (Easiest!)
```bash
docker-compose up -d
# Test it
curl "http://localhost:8000/agent/query?q=Brussels+sports+events&limit=3"
```

Option 2: Manual Setup
First, make sure you have Ollama running. Then you gotta pull the model:

```bash
ollama serve
ollama pull llama3.1:8b
```

Install the python packages. 
```bash
uv sync
```
There's a python script to set up the database, setup_database.py. You'll need to have postgres installed and a database created first for it to work.

```bash
python setup_database.py
```

And then run it!

```bash
uvicorn app.main:app --reload
```

The --reload flag is nice, it restarts automatically when you save a file.

Other API pages
/agent/query?q=... -> This is the main one you'll use.
/health -> To check if it's running.
/geocode?q=Brussels -> Just finds the coordinates for a city. ()

Real Examples 

Simple Query: "Brussels sports events this weekend"
```json
{
  "intent": "events_in_cities",
  "count": 3,
  "results": [
    {
      "match_name": "Royale Union St-Gilloise vs KVC Westerlo",
      "datetime_local": "2025-09-27T18:45:00+00:00",
      "competition": "Jupiler Pro League",
      "venue": "Stade Joseph Marien",
      "distance_km": 3.85
    },
    {
      "match_name": "Brussels Basketball vs Okapi Aalst", 
      "datetime_local": "2025-09-28T15:00:00+00:00",
      "competition": "BNXT League 2025 - 2026",
      "venue": "Complexe Sportif Neder-Over-Heembeek",
      "distance_km": 5.17
    }
  ],
  "filters": {
    "cities": ["Brussels"],
    "date_from": "2025-09-27",
    "date_to": "2025-09-28",
    "time_keyword": "this_weekend"
  }
}
```

Complex Query: "Pro League matches in Antwerp next week"
```json
{
  "intent": "events_by_competition",
  "count": 2,
  "results": [
    {
      "match_name": "Royal Antwerp FC vs Cercle Brugge KSV",
      "datetime_local": "2025-10-04T18:45:00+00:00",
      "competition": "Jupiler Pro League",
      "venue": "Bosuilstadion",
      "distance_km": 5.21
    }
  ],
  "filters": {
    "cities": ["Antwerp"],
    "competitions": ["Pro League"],
    "date_from": "2025-09-29",
     "date_to": "2025-10-5",
    "time_keyword": "next_week"
  }
}
```

List Competitions: "what leagues are available"
```json
{
  "intent": "list_competitions",
  "count": 5,
  "results": [
    {"name": "Jupiler Pro League", "season": "Pro League JPL"},
    {"name": "Lotto Super League", "season": "Lotto Super League"},
    {"name": "BNXT League 2025 - 2026", "season": "BNXT League"},
    {"name": "BELGIAN VOLLEY LEAGUE WOMEN", "season": "BELGIAN VOLLEY LEAGUE WOMEN"},
    {"name": "LOTTO VOLLEY LEAGUE MEN", "season": "LOTTO VOLLEY LEAGUE MEN"}
  ]
}
```

Error Handling: "xyz123 random text"
```json
{
  "detail": {
    "message": "I didn't understand your request. Please ask about sports events, competitions, or venues in Belgium.",
    "error": "UNCLEAR_QUERY"
  }
}
```

To-Do / Future Ideas
Add more sports!! (Handball, Futsal?)
Make a real frontend for it instead of just using curl.
Get conversational memory working so it remembers what you asked before.
Maybe let it buy tickets? (lol probably not)

This was just a project for me to learn, so feel free to mess around with the code. 
