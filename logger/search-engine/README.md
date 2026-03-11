# Micro template of the STELLA infrastructure

This repository provides interested experimenters with a template for integrating their ranking and recommendation systems into the [STELLA infrastructure](https://stella-project.org/). 
Currently, the infrastructure supports two different types of submission. 
Experimenters can choose to submit pre-computed runs with TREC run file syntax *OR* use this repository in order to integrate their system as a micro-service into the [STELLA App](https://github.com/stella-project/stella-app).
In contrast to pre-computed results, these dockerized systems can deliver more comprehensive search result since they are not limited to pre-selected queries or items.

![workflow](./doc/STELLA_participate_ani.gif)

## Development notes

As a starting point we provide a web-service based on [flask](https://palletsprojects.com/p/flask/) in [`app.py`](./app.py). **The classes in [`systems.py`](./systems.py) need to be adapted**.
Of course, experimenters are not restricted to use Flask or Python at all as long as the resulting Docker containers implement the required REST endpoints and deliver technically correct responses.

We provide tutorials in the form of setup guides and videos. For starters, following one of the provided resources should be enough.

#### Implementing a ranking service
- :memo: [Setup guide of ranking systems](./doc/rank/README.md)

#### Implementing a recommendation service
- :memo: [Setup guide of recommender systems](./doc/rec/README.md)
- :movie_camera: [Video guide of recommender systems](https://drive.google.com/file/d/15pR_xjrDfms32Yi4U6FnTd2aE8Rhmxyn/view)

#### Requirements

Before starting your implementations, some requirements have to be fullfiled:

* docker: [get-started](https://docs.docker.com/get-started/) | [get docker](https://docs.docker.com/get-docker/)
* [git](https://github.com/git-guides/install-git)
* [python3](https://wiki.python.org/moin/BeginnersGuide/Download)

Besides a Python distribution like [Anaconda](https://www.anaconda.com/) and an IDE like [PyCharm](https://www.jetbrains.com/de-de/pycharm/) can be helpful. Likewise, you should be familiar with [virtual environments](https://docs.python.org/3/tutorial/venv.html).

## REST endpoints

For ranking systems the following endpoint has to be implemented:

**GET** `container_name/ranking?query=<string:qstr>&page=<int:pnum>&rpp=<int:rppnum>`

For recommending datasets this endpoint has to be implemented:

**GET** `container_name/recommendation/datasets?itemid=<string:itemidstr>&page=<int:pnum>&rpp=<int:rppnum>`  

For recommending publications this endpoint has to be implemented:

**GET** `container_name/recommendation/publications?itemid=<string:itemidstr>&page=<int:pnum>&rpp=<int:rppnum>`

Whereas the parameters contain the following information:

| Parameter | Explanation |
| --- | --- |
| query | String-formatted query corresponding to the ranking |
| itemid | Identifier of the target item corresponding to the recommendation |
| page | Number of page |
| rpp | Number of **r**esults **p**er **p**age |

**Requirements:** The submitted system has run in a single Docker container and this repository should be self-contained. As a starting point, please have a look at the [Dockerfile](./Dockerfile). 

## Testing

Before registering your ready-to-be-evaluated system, make sure you run the tests provided in [`test/`](./test).
Beside unit tests, we provide Python scripts to build, run, stop and remove the Docker images/containers.
Once the Docker container is started run either `test_ranking`, `test_recommendation_datasets`, or `test_recommendation_publications`.

## Data

Datasets can be retrieved after registration. Experimenters can choose to implement their system with datasets provided by LIVIVO or GESIS.
Recommendation systems are going to be deployed at GESIS, whereas ranking systems at LIVIVO.

## Register

In order to get access and submit systems, experimenters have to [register here](https://lilas.stella-project.org/). As soon as you have registered, you can submit your system by adding a link to your GitHub repository. After approval your system is ready to be integrated into the [STELLA App](https://github.com/stella-project/stella-app).

## FAQ & Known Issues

As far as we know, the development process works fine within a UNIX environment. However we received the following feedback from Windows users:

- Instead of using the address `0.0.0.0`, it should be `localhost` when starting flask.
- For some Windows users the [`docker-sdk`](https://docker-py.readthedocs.io/en/stable/) did not work at the first try and a reinstallation of [Anaconda](https://www.anaconda.com/) could solve the issue.
