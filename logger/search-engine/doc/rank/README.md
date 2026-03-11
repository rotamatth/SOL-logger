<!--- ![LOGO](https://github.com/stella-project/Participand_Recommendation/blob/main/img/logo-st.JPG) --->
![LOGO](https://avatars1.githubusercontent.com/u/47419314?s=200&v=4)


<b>STELLA - Infrastructures for Living Labs </b><br>
https://stella-project.org/ 


# How to integrate a ranking microservice into STELLA

## 1. Introduction

The STELLA-framework enables participants to run and evaluate ranking and recommendation-systems in a Living-Lab scenario. The heart of STELLA-framework is the STELLA application, which is implemented as a a multi-container-application (MCA) by the sites (the search-engines) and handles communication between the site and participant-containers. This means every participant-system must be deployed as a docker image, which runs as a container inside STELLA application. In principle you have full freedom in choice of programming language and software tools. Your container only has to satisfy the constraints of a predefined REST-API. If you want to learn more about STELLA, please [see our blog posts](https://stella-project.org/blog/). This tutorial will guide you step-by-step through the process of integrating a ranking microservice into STELLA-infrastructure.
You will learn how to build your own dockerized ranking-system with python.
For this purpose we will use a document subset from the LIVIVO search engine.
To give you a head start, we prepared a code template. That means, you just have to write a few lines of code to get your ranking-system running.

## 2. Prerequisites 

Before starting this tutorial, make sure all requirements in the [README.md](https://github.com/stella-project/stella-micro-template/blob/master/README.md#requirements) are fulfilled.

<!---

## 2. Requirements
You will need the following software installed on your system to build your own ranking-system:

* git: https://github.com/git-guides/install-git
* docker: https://docs.docker.com/get-started/
* python3: https://wiki.python.org/moin/BeginnersGuide/Download

Hint: Don't forget to add your user to the docker group

## 3. How STELLA works

The STELLA-framework enables participants to run and evaluate ranking and recommendation-systems in a Living-Lab scenario. The heart of STELLA-framework is the STELLA application, which is implemented as a a multi-container-application (MCA) by the sites (the search-engines) and handles communication between the site and participant-containers. This means every participant-system must be deployed as a docker image, which runs as a container inside STELLA application. In principle you have full freedom in choice of programming language and software tools. Your container only has to satisfy the constraints of a predefined REST-API.
In this tutorial we will create a ranker with python and we will use a code template with predefined REST-endpoints. If you want to learn more about STELLA, please [see our blog posts](https://stella-project.org/blog/).

--->

## 3. LIVIVO Dataset

LIVIVO is an interdisciplinary search engine for literature and information in the field of life sciences. It is run by ZB MED – Information Centre for Life Sciences. LIVIVO draws on relevant scientific information from the ZB MED subject areas of medicine, health, nutrition, and environmental and agricultural sciences. (https://www.livivo.de/app/misc/help/about)  
In this tutorial we will work with a small subset of LIVIVO (30000 documents). See the following table for an explanation of fields.

|field|description|
|---|---|
|DBRECORDID|primary document key|
|TITLE|document title|
|ABSTRACT|document abstract|
|AUTHOR|list of authors|
|INSTITUTION|list of Institutions connected with the paper|
|SOURCE|publiction source|
|VOLUME|volume (for journal articles)|
|ISSUE|issue (for journal articles)|
|PAGES|page numbers referring to|
|PUBLISHER|document publisher|
|LANGUAGE|document language|
|PUBLDATE|publishing date|
|PUBLYEAR|publishing year|
|PUBLPLACE|publishing place|
|PUBLCOUNTRY|publishing country|
|IDENTIFIER|list of additional identifiers (pmid, pmcid, nlmid,...)|
|DOI|Document Object identifier|
|ISSN|International Standard Serial Number|
|EISSN|Electronic International Standard Serial Number|
|PISSN|Print International Standard Serial Number|
|DATABASE|Source Database from wich LIVIVO collected the document (MEDLINE,NLM,AGRIS,..)|
|DOCUMENTURL|URL for accessing document|
|MESH|list of MESH-terms|
|KEYWORDS|additional keywords|
|CHEM|list of chemical substances|

The dataset is provided in jsonlines-format.
Download the LIVIVO-testset here: https://th-koeln.sciebo.de/s/OBm0NLEwz1RYl9N/download?path=%2Flivivo%2Fdocuments&files=livivo_testset.jsonl

## 4. Forking and cloning STELLA-microservice Template

Before you start working on your own ranking-system, you should fork our template.  
Navigate with your browser to our template repository https://github.com/stella-project/stella-micro-template and click the "fork"-button on the top right. This will create a fork in your personal github-account. 
Now navigate to your working directory and run the following command to clone the forked repository to your local system.

```bash
$ git clone https://github.com/your-username/stella-micro-template.git
```

## 5. Adding dataset to your local environment

Please download the LIVIVO-testset here: https://th-koeln.sciebo.de/s/OBm0NLEwz1RYl9N/download?path=%2Flivivo%2Fdocuments&files=livivo_testset.jsonl  
Place the file into stella-micro-template/data/livivo/datasets. If these subfolders do not exist, create them.

```.
├── stella-micro-template
│   ├── data
│   │   ├── livivo
│   │       ├── documents
│   │           ├── livivo_testset.jsonl
```


## 6. REST-Endpoints with Flask

To connect your system with STELLA, your container has to provide REST-endpoints according to the STELLA-interface.
Your system should provide three endpoints.  
First of all, your system has to implement an indexing-endpoint. This endpoint is called when your system is used for the first time. It builds a search-index from the data provided by the site.
The ranking-endpoint must return an ordered list of document-ids in JSON format. If you provide these endpoints, your results will be integrated seamlessly into the sites’ pages.
The test-endpoint is, as you may have guessed, for testing if your container is up and running. It just displays the name of your container.

* **GET** `/index`  
  Starts indexing data, when starting ranking-system for the first time

* **GET** `/ranking?query=<string:qstr>&page=<int:pnum>&rpp=<int:rppnum>`
  Returns an ordered list of document-ids in JSON-Format

* **GET** `/test`  
  This Endpoints is for testing purposes and just prints the name of your container

For a more detailled explanation of the API-Interface please visit our [API-interface-documentation](https://github.com/stella-project/concept/tree/master/interfaces).

All these endpoints are already existing in the template. Please have a look into the file `app.py`.
Plese don't do any changes in that file.

```python
from flask import Flask, request, jsonify, redirect
from systems import Ranker, Recommender


app = Flask(__name__)
ranker = Ranker()
recommender = Recommender()


@app.route('/')
def redirect_to_test():
    return redirect("/test", code=302)


@app.route('/test', methods=["GET"])
def test():
    return 'Container is running', 200


@app.route('/index', methods=["GET"])
def index():
    ranker.index()
    recommender.index()
    return 'Indexing done!', 200


@app.route('/ranking', methods=["GET"])
def ranking():
    query = request.args.get('query', None)
    page = request.args.get('page', default=0, type=int)
    rpp = request.args.get('rpp', default=20, type=int)
    response = ranker.rank_publications(query, page, rpp)
    return jsonify(response)


@app.route('/recommendation/datasets', methods=["GET"])
def rec_data():
    item_id = request.args.get('item_id', None)
    page = request.args.get('page', default=0, type=int)
    rpp = request.args.get('rpp', default=20, type=int)
    response = recommender.recommend_datasets(item_id, page, rpp)
    return jsonify(response)


@app.route('/recommendation/publications', methods=["GET"])
def rec_pub():
    item_id = request.args.get('item_id', None)
    page = request.args.get('page', default=0, type=int)
    rpp = request.args.get('rpp', default=20, type=int)
    response = recommender.recommend_publications(item_id, page, rpp)
    return jsonify(response)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
```

You might have registered some endpoints for building recommendation-systems. Since we are only building a ranking-system, please ignore these endpoints for now.


## 7. Indexing data

Let's start indexing the data from "livivo_test.jsonl".
This file contains data in jsonlines format, which means, each line is an individual json-object, which represents a single document.
Open the file ``systems.py``. This file contains to classes: Ranker and Recommender. As the name says, the first one is for implementing a rankings, the second one for recommender-systems. In this tutorial we will only change the Ranker-Class.

At first, we will implement the code for indexing documents.  
We will read the documents with the help of the jsonlines-package. Don't forget to import the package first. 
For the sake of simplicity, we will just extract the unique identifier of any document and store them in the python built-in type "list".
At a later stage, when you work with the full corpus of LIVIVO, which contains more than 60 mio documents, you should switch to a more sophisticated Index. 
You will change the method ```index(self)``` so it reads the documents from ```livivo_testset.jsonl```

The Ranker-Class in your file ``systems.py`` should now look like this:

```python
import jsonlines

class Ranker(object):

    def __init__(self):
        self.idx = None

    def index(self):
        self.idx = []
        with jsonlines.open('./data/livivo/documents/livivo_testset.jsonl') as reader:
            for obj in reader:
                self.idx.append(obj['DBRECORDID'])

    def rank_publications(self, query, page, rpp):

        itemlist = []

        return {
            'page': page,
            'rpp': rpp,
            'query': query,
            'itemlist': itemlist,
            'num_found': len(itemlist)
        }


```

## 8. ranking documents (shuffled)

Now we will implement our personal ranking-algorithm. To keep it simple, our ranking-algorithm picks just a number of random documents.
This will give you an idea, how it works and enables you to implement some smart ranking-algorithms after this tutorial.
For picking some random entries from our item-list, we can use the choice-method from the random package which is part of the python library and doese not need any installation (i.e. you do not need to add it to the requirements.txt file). You will be changing the first line of the method ```rank_publications(self, query, page, rpp)``` to get a randomized item list ```itemlist = random.choices(self.idx, k=rpp)```

The Ranker-Class in your file ``systems.py`` should now look like this:

```python
import jsonlines
import random

class Ranker(object):

    def __init__(self):
        self.idx = None

    def index(self):
        self.idx = []
        with jsonlines.open('./data/livivo/documents/livivo_testset.jsonl') as reader:
            for obj in reader:
                self.idx.append(obj['DBRECORDID'])

    def rank_publications(self, query, page, rpp):

        itemlist = random.choices(self.idx, k=rpp)

        return {
            'page': page,
            'rpp': rpp,
            'query': query,
            'itemlist': itemlist,
            'num_found': len(itemlist)
        }
```

If you decide to use external packages, please add them to the file ``requirements.py``.
In our example, we decided to use the package ``jsonlines``.
Your file ``requirements.py`` should now look like this

```python
flask
jsonlines
```

## 9. setup virtual environment

We are now ready to run your application. Before pushing your code to github, you should verify, that everything works as expected.
To do so, you should create a virtual-environment, install the necessary dependencies there and run your Ranker on your local machine.
Python IDEs (like PyCharm) offer functionalities to create a virtual python environment inside your project.
Since we don't know which IDE you are using, we show you, how to create Virtual-Environment manually.
Inside the directory of your cloned-repository, please run this command.


On Linux and MacOS
```shell
$ python3 -m venv venv
```

On Windows
```shell
$ py -m venv venv
```

This creates a virtual python environment in the folder ``venv``.
To activate and work with your virtual python environment, please run this commadn:

On Linux and MacOs
```shell
$ source venv/bin/activate
```

On Windows
```shell
.\venv\Scripts\activate
```

Now, you have to make sure, that all necessary packages are available in your virtual python environment.

```shell
pip install -r requirements.txt
```
Don't push the folder ``venv`` which contains the virtual python environment to your github-repository. It's just for testing your Ranker on your local machine. 

## 10. run ranker in virtual environment

In your activated virtual environment, start the application.

```shell
$ python app.py
```

You will get some messages on the shell, indicating, that your Flask-App is running.
Now we can do some checks to see if everything works as it should.

Please open your browser and access the following address http://0.0.0.0:5000/test (you might need to use http://localhost:5000/test in Windows).
Your browser should reply with the message "Container is running". This means, Flask is running and serving at Port 5000. Do not worry if your try http://0.0.0.0:5000/ as that entry point is not implemented (i.e. it is expected that you will get an error).

Now we want to start indexing documents with our ranker. Please access the following address with your browser http://0.0.0.0:5000/index (or http://localhost:5000/index in Windows).
This may take some time, when indexing a big collection. After indexing was successful, your browser should replay with "Indexing done!".

We are ready to send queries to our ranking-system and get results.
Access the following address with your browser http://0.0.0.0:5000/ranking?query=test (you might need to use http://localhost:5000/ranking?query=test in Windows).
Your browser will reply with a JSON-Document, that look like to this (itemlist will be different, because the results are randomized):

```JSON
{
  "itemlist": [
    "M7064959", 
    "NLM7513803", 
    "NLM8300642A", 
    "AGRISUS201600020713", 
    "AGRISFR2016217161", 
    "NLM26061140R", 
    "NLM101220129", 
    "M28128407", 
    "AGRISUS201400054734", 
    "NLM101070554", 
    "NLM101230052", 
    "M17665832", 
    "M28313204", 
    "NLM9412462", 
    "NLM101068566", 
    "AGRISJP2009005254", 
    "NLM101173006", 
    "M4793495", 
    "M2965586", 
    "M2082902"
  ], 
  "num_found": 20, 
  "page": 0, 
  "query": "test", 
  "rpp": 20
}
``` 

Congratulations! Your ranker is running! We can now start to build a dockerized version and run unit-tests!

## 11. Build docker-contaner and run unit-tests

You are now ready to build your ranker as a docker-container and run unit-tests to check if everything is working as expected, before pushing your code back to github.

Navigate to the folder ``test``.
Make sure, you still have your virtual environment activated and stopped your ranking application.
First, install the python-dependencies needed for running the unit-tests:

```shell
$ pip install -r requirements.txt
```

Next, we are ready to build and run your ranker as docker-container.
Please run the python-script "docker_build_run.py".

```shell
$ python docker_build_run.py
```

Open your browser and please verifiy, if the endpoints are accessible:
- http://0.0.0.0:5000/test (http://localhost:5000/test in Windows)
- http://0.0.0.0:5000/index (http://localhost:5000/index in Windows)
- http://0.0.0.0:5000/ranking?query=test (http://localhost:5000/ranking?query=test in Windows)

Now we can run the unit-tests:

```shell
$ python test_ranking.py 
```

This will run 6 different tests, which your container has to pass, before it can be integrated into STELLA
The Script should print the message "OK". If you are using Windows, make sure you target 'localhost' rather than '0.0.0.0' on the IP variable in the test (i.e. ```IP = 'localhost'``` for Windows; for other OS ```IP = '0.0.0.0.``` should work).


## 12. push your changes to github

Now you are ready to push your ranker back to github.

Add the changed files to the the staging area.

``` shell
git add systems.py requirements.txt
```

Save the changes to you local repository.

``` shell
git commit -m "add systems and requirements"
```

Update remote branch with local commit.

``` shell
git push origin main
```

Your ranker is now ready for integration into the STELLA-infrastructure. Please make sure, that the visibility of your repository is set to "public".
