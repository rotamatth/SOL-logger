# SOL+: Controlled Search Platform for Educational Search Studies

SOL+ is a controlled search platform designed to support the study of search behaviour in educational and research settings. It provides a web-based search interface, a backend search engine operating over a local corpus, and a client-side logger that records detailed user interactions during search sessions.

The platform is intended for controlled experiments in which reproducibility, safety, and fine-grained behavioural data are important. Rather than relying on the open web, SOL+ operates on a curated local collection, making it suitable for research scenarios that require consistency, transparency, and experimental control.

---

## Overview

This repository contains a small search system composed of three main components:

- **Search App** – the user-facing web application that manages the participant flow and renders the search interface
- **Search Engine** – the backend retrieval service that indexes a local corpus and returns ranked results
- **Logger** – the client-side component that records interaction events such as queries, clicks, hover behaviour, pagination, and task completion

Together, these components enable structured search tasks and support the collection of interaction data for later analysis.

---

## Main Features

- Controlled search environment based on a local corpus
- Reproducible retrieval behaviour through a dedicated ranking pipeline
- Web-based search interface for participants
- Session and task management
- Fine-grained interaction logging
- Modular structure for research-oriented extensions and customization

---

## Repository Structure

### 1. Search App

The **Search App** is the main web application used by participants.

It is responsible for:

- managing participant flow (`welcome`, `start`, `task`, `home`, `result`, `thank_you`)
- handling sessions
- rendering HTML templates
- sending search queries to the backend search engine
- receiving and storing interaction logs from the browser

Typical files include:

- `search_app.py`
- `forms.py`
- `templates/layout.html`
- `templates/home.html`
- `templates/search.html`
- `templates/start.html`
- `templates/welcome.html`

---

### 2. Search Engine

The **Search Engine** is the backend retrieval component.

It is responsible for:

- loading the corpus
- building or loading the PyTerrier index
- ranking documents for a given query
- returning ranked results as JSON

Typical files include:

- `app.py`
- `systems.py`

---

### 3. Logger

The **Logger** runs in the browser and captures interaction events during a session.

It is responsible for:

- generating or tracking a session identifier
- logging user actions during the task
- tracking browsing and result interaction behaviour
- sending the collected log data to the backend

Typical events include:

- participant ID submission
- task start
- query submission
- SERP generation
- result hover
- result click
- pagination
- task completion
- session ending

Typical file:

- `static/logger.js`

---

## Architecture Overview

```text
Browser
   ↓
Search App (Flask)
   ↓ HTTP request
Search Engine (/ranking)
   ↓
Ranking Pipeline (PyTerrier)
   ↓
JSON results
   ↓
Search App renders results
   ↓
Browser logger captures interactions
   ↓
/log_session
   ↓
Log file storage
