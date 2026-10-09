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
