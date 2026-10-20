Forked from [ECIR2026 LISP - A Rich Interaction Dataset and Loggable Interactive Search Platform](https://github.com/irgroup/LISP_Dataset_and_Platform)

This repository accompanies the resource paper submission "LISP - A Rich Interaction Dataset and Loggable Interactive Search Platform" for ECIR 2026. It contains all data collected during the user study, as well as the full setup used to conduct the study. This enables others to either reproduce our results in a new user study or adapt the framework to create their own study.

## Structure of this Repository

* `logs/`: Contains the log files of the user study and additional metadata from the Perceptual Speed Test and both questionnaires
* `search-app/`: Contains the implementation of the front end of the search engine used in the user study
* `search-engine/`: Contains the implementation of the search engine backend

## Private research dashboard

Researchers can use `/dashboard` with a shared server-configured password. See
[setup, study rules, security and export documentation](docs/research_dashboard.md).
V2 collection writes to a fresh directory; existing logs remain available separately
under Legacy. The research roster defaults to IDs 1–20 (4th Grade) and 21–40 (5th Grade).

Open **Prepare a session** to choose the year/class, set a session date, check
participant IDs and save or approve the questions. Every active ID enrolled in
that class/year is included in every session automatically. IDs remain permanent
across years. Legacy questions remain a library; student eligibility uses the
scheduled Zurich date and approved assignments. Puzzle assets are optional.

### Dashboard foundation

For research setup, see [the dashboard guide](docs/research_dashboard.md). For
progress-saving development, start with [the source integration contract](docs/dashboard_integration.md).
For deployment and backups, use [the readiness guide](docs/production_readiness.md).
For the current checkpoint, remaining merge checks and next V2 work, see
[Merge and V2 readiness](docs/merge_v2_readiness.md).
