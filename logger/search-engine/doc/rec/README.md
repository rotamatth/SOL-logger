<!--- ![LOGO](https://github.com/stella-project/Participand_Recommendation/blob/main/img/logo-st.JPG) --->
![LOGO](https://avatars1.githubusercontent.com/u/47419314?s=200&v=4)


<b>STELLA - Infrastructures for Living Labs </b><br>
https://stella-project.org/ 

# Participant Guideline
## Implementing Experimental System for <b style="color:orange">Recommendation</b>
Steps to implement a dockerize application for participating in Living Lab for evaluating your REC systems in a live environment of gesis search which is a search engine for finding information about social science research data and open access publications. 


<!--- ![spb](https://github.com/stella-project/Participand_Recommendation/blob/main/img/patrick.jpg) --->

## Table of Contents

<div class="alert alert-block alert-info" style="margin-top: 20px">

0.  [Prerequisites](#10)<br> 
1.  [Data](#0)<br>
2.  [Implementing Ranking Algorithm](#1)<br>
3.  [Implementing Dockerize Flask App](#2)<br>
4.  [Next Steps](#3)<br>
    </div>
    <hr>

## 0. Prerequisites <a id="10"></a>

Before starting this tutorial, make sure all requirements in the [README.md](https://github.com/stella-project/stella-micro-template/blob/master/README.md#requirements) are fulfilled.

<!---
# Prerequisite <a id="10"></a>
-  Git
-  Install Docker
-  Add user to Docker group

<b> Optional </b>
- Anaconda
- pycharm




- Clone [Participant_Recommendation](https://github.com/stella-project/gesis_rec_micro.git):

```console
git clone https://github.com/stella-project/gesis_rec_micro.git
```


### Some helpful Links

- [Video](https://drive.google.com/file/d/1_Zuw7cxeVP-vDoLUknm96nJI28AP-tnR/view?usp=sharing)
- [stella-micro-template](https://github.com/stella-project/stella-micro-template)
- [Gesis-Search dataset](https://th-koeln.sciebo.de/s/OBm0NLEwz1RYl9N)
- [PyCharm IDE](https://www.jetbrains.com/de-de/pycharm/)
- [Get Docker](https://docs.docker.com/get-docker/)

--->

<hr>

# 1.Data <a id="0"></a>
-  A corpus od <b>publication 93k</b> and <b>Research data 83k</b> metadata from GESIS Leibniz Institute for the Social Sciences
-  Metadata in different languages (mixed and separated)


```python
!cd data && mkdir gesis-search && mkdir gesis-search/datasets && mkdir gesis-search/documents

!wget -O gesis-search/datasets/dataset.jsonl \
https://th-koeln.sciebo.de/s/OBm0NLEwz1RYl9N/download?path=%2Fgesis-search%2Fdatasets&files=dataset.jsonl -Q --show-progress
    
!wget -O gesis-search/publications.jsonl \
https://th-koeln.sciebo.de/s/OBm0NLEwz1RYl9N/download?path=%2Fgesis-search%2Fdocuments&files=publication.jsonl -Q --show-progress
    
!chown -R 775 data/*
```

![trd](https://github.com/stella-project/Participand_Recommendation/blob/main/img/tree-data.png)

```python
PATH = "./data/gesis-search/"
```


```python
import json
import jsonlines
import pandas as pd
import numpy as np
import pickle
import random

pd.set_option("display.max_columns", None)
```


```python
with jsonlines.open(PATH+"publications/publication.jsonl") as f :
    pub = [obj for obj in f]

with jsonlines.open(PATH+"datasets/dataset.jsonl") as f2 :
    dataset = [obj for obj in f2]
```


```python
pubdf = pd.DataFrame(pub)
pubdf = pubdf.set_index('id')
```


```python
datasetdf = pd.DataFrame(dataset)
datasetdf = datasetdf.set_index('id')
```


```python
print("Number of publication: ",len(pubdf))
print("Metadata are: " ,list(pubdf.columns))
pubdf.head(3)

```

    Number of publication:  93953
    Metadata are:  ['title', 'abstract', 'topic', 'person', 'links', 'subtype', 'document_type', 'coreAuthor', 'doi', 'date']





<div>

<table border="1" class="dataframe">
  <thead>
    <tr style="text-align: right;">
      <th></th>
      <th>title</th>
      <th>abstract</th>
      <th>topic</th>
      <th>person</th>
      <th>links</th>
      <th>subtype</th>
      <th>document_type</th>
      <th>coreAuthor</th>
      <th>doi</th>
      <th>date</th>
    </tr>
    <tr>
      <th>id</th>
      <th></th>
      <th></th>
      <th></th>
      <th></th>
      <th></th>
      <th></th>
      <th></th>
      <th></th>
      <th></th>
      <th></th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <th>gesis-ssoar-1002</th>
      <td>New Concerns, More Cooperation? How Non-Tradit...</td>
      <td>None</td>
      <td>[Indien, Wirtschaftsbeziehungen, bilaterale Be...</td>
      <td>[Biba, Sebastian]</td>
      <td>[{'label': 'Link', 'link': 'https://journals.s...</td>
      <td>journal_article</td>
      <td>Zeitschriftenaufsatz</td>
      <td>[Biba, Sebastian]</td>
      <td>None</td>
      <td>2016</td>
    </tr>
    <tr>
      <th>gesis-ssoar-1006</th>
      <td>Buddhism in Current China-India Diplomacy</td>
      <td>Buddhism is being emphasised strongly in both ...</td>
      <td>[China, Indien, bilaterale Beziehungen, Außenp...</td>
      <td>[Scott, David]</td>
      <td>[{'label': 'Link', 'link': 'https://journals.s...</td>
      <td>journal_article</td>
      <td>Zeitschriftenaufsatz</td>
      <td>[Scott, David]</td>
      <td>None</td>
      <td>2016</td>
    </tr>
    <tr>
      <th>gesis-ssoar-10066</th>
      <td>Zukunftsaufgaben der Humanisierung des Arbeits...</td>
      <td>Das seit 1974 vom BMFT geförderte Programm "Fr...</td>
      <td>[Arbeitswelt, Technik, Rationalisierung, Arbei...</td>
      <td>[Altmann, Norbert, Düll, Klaus, Lutz, Burkart]</td>
      <td>[{'label': 'Link', 'link': 'http://www.ssoar.i...</td>
      <td>book</td>
      <td>Buch</td>
      <td>[Altmann, Norbert, Düll, Klaus, Lutz, Burkart]</td>
      <td>None</td>
      <td>1987</td>
    </tr>
  </tbody>
</table>
</div>




```python
print("Number of Research Data: ",len(datasetdf))
print("Metadata are: " ,list(datasetdf.columns))
datasetdf.head(3)
```

    Number of Research Data:  83225
    Metadata are:  ['title', 'subtype', 'abstract', 'person', 'time_collection', 'countries_collection', 'methodology_collection', 'universe', 'selection_method', 'doi', 'publication_year', 'topic']





<div>

<table border="1" class="dataframe">
  <thead>
    <tr style="text-align: right;">
      <th></th>
      <th>title</th>
      <th>subtype</th>
      <th>abstract</th>
      <th>person</th>
      <th>time_collection</th>
      <th>countries_collection</th>
      <th>methodology_collection</th>
      <th>universe</th>
      <th>selection_method</th>
      <th>doi</th>
      <th>publication_year</th>
      <th>topic</th>
    </tr>
    <tr>
      <th>id</th>
      <th></th>
      <th></th>
      <th></th>
      <th></th>
      <th></th>
      <th></th>
      <th></th>
      <th></th>
      <th></th>
      <th></th>
      <th></th>
      <th></th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <th>ZA0018</th>
      <td>Einstellung zur Wehrbereitschaft und Demokrati...</td>
      <td>dbk</td>
      <td>Vergleichsstudie bei der Zivilbevölkerung zu e...</td>
      <td>None</td>
      <td>10.1960 - 11.1960</td>
      <td>[Deutschland]</td>
      <td>Mündliche Befragung mit standardisiertem Frage...</td>
      <td>Alter: 16 Jahre und älter.</td>
      <td>Mehrstufige Zufallsauswahl \r\n</td>
      <td>doi:10.4232/1.11581</td>
      <td>2013</td>
      <td>[Konflikte, Sicherheit und Frieden, Politische...</td>
    </tr>
    <tr>
      <th>ZA0025</th>
      <td>Einstellung zur Monarchie (Niederlande)\r\n</td>
      <td>dbk</td>
      <td>Einstellung der Niederländer zu den Deutschen ...</td>
      <td>None</td>
      <td>06.1965 - 07.1965</td>
      <td>[Niederlande]</td>
      <td>Mündliche Befragung mit standardisiertem Frage...</td>
      <td>Alter: 20 Jahre und älter</td>
      <td>Quotenauswahl</td>
      <td>doi:10.4232/1.0025</td>
      <td>1965</td>
      <td>[Politische Verhaltensweisen und Einstellungen...</td>
    </tr>
    <tr>
      <th>ZA0042</th>
      <td>Politische Einstellungen (Juni 1966)\r\n</td>
      <td>dbk</td>
      <td>Beurteilung der Parteien.&lt;br/&gt;&lt;br/&gt;Themen: Beu...</td>
      <td>None</td>
      <td>06.1966 - 07.1966</td>
      <td>[Deutschland]</td>
      <td>Mündliche Befragung mit standardisiertem Frage...</td>
      <td>Alter: 16-79 Jahre</td>
      <td>Mehrstufige Zufallsauswahl \r\n</td>
      <td>doi:10.4232/1.0042</td>
      <td>1966</td>
      <td>[Politische Verhaltensweisen und Einstellungen...</td>
    </tr>
  </tbody>
</table>
</div>



<hr>

# 2. Implementing the Recommendation Algorithm <a id="1"></a>

In the following we implement a simple app to create randomize recommendation for every publication. You will find out how simple it is.


```python
idx = []
with jsonlines.open('./data/gesis-search/datasets/dataset.jsonl') as reader:
    for obj in reader:
           idx.append(obj.get('id'))
```


```python
def recommend_datasets(item_id, page, rpp):
    itemlist = random.choices(idx, k=rpp)

    return {
        'page': page,
        'rpp': rpp,
        'item_id': item_id,
        'itemlist': itemlist,
        'num_found': len(itemlist)
    }
```


```python
recommend_datasets("gesis-ssoar-1002", 1, 5)
```



```json
{   "page": 1,
    "rpp": 5,
    "item_id": "gesis-ssoar-1002",
    "itemlist": ["datasearch-httpseasy-dans-knaw-nloai--oaieasy-dans-knaw-nleasy-dataset32489",
                "datasearch-httpseasy-dans-knaw-nloai--oaieasy-dans-knaw-nleasy-dataset76673",
                "ZA5859",
                "ZA8682",
                "datasearch-httpwww-da-ra-deoaip--oaioai-da-ra-de4527"],
    "num_found": 5}
```


<hr>

# 3.Implementing Dockerize Flask App <a id="2"></a>


## Application structure
![tree](https://github.com/stella-project/Participand_Recommendation/blob/main/img/tree-all.png)

## API Endpoints 

### Endpoints

To connect your system with STELLA, your container has to provide endpoints according to our interface. Most importantly, your system has to implement an indexing-endpoint. This endpoint is called when your system is used for the first time. It builds a search-index from the data provided by the site. The recommendations endpoints must return an ordered list of document-ids in JSON format. If you provide these endpoints, your results will be integrated seamlessly into the sites’ pages.

- `GET /test`: print the name o container

- `GET /index`: index the data for retrieval
- `GET /recommendation/datasets?<string:item_id>`: Retrieve a ranking corresponding to the query specified at the endpoint. A JSON object with maximally 10 entries will be returned.


## app.py
you don't need to change this file

```python
from flask import Flask, request, jsonify
from systems import Ranker, Recommender


app = Flask(__name__)
ranker = Ranker()
recommender = Recommender()


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

## system.py


```python
import jsonlines
import random

class Ranker(object):

    def __init__(self):
        self.idx = None

    def index(self):
        pass

    def rank_publications(self, query, page, rpp):

        itemlist = []

        return {
            'page': page,
            'rpp': rpp,
            'query': query,
            'itemlist': itemlist,
            'num_found': len(itemlist)
        }


class Recommender(object):

    def __init__(self):
        self.idx = None

    def index(self):
        self.idx = []
        with jsonlines.open('./data/gesis-search/datasets/dataset.jsonl') as reader:
            for obj in reader:
                self.idx.append(obj.get('id'))

    def recommend_datasets(self, item_id, page, rpp):
        
        # implement your ranking algorithm here!
        itemlist = random.choices(self.idx, k=rpp)
        
        return {
            'page': page,
            'rpp': rpp,
            'item_id': item_id,
            'itemlist': itemlist,
            'num_found': len(itemlist)
        }

    def recommend_publications(self, item_id, page, rpp):

        itemlist = []

        return {
            'page': page,
            'rpp': rpp,
            'item_id': item_id,
            'itemlist': itemlist,
            'num_found': len(itemlist)
        }
```

### DockerFile

```bash

FROM python:3.7

COPY requirements.txt requirements.txt
RUN python -m pip install -r requirements.txt

COPY . .

ENTRYPOINT python3 app.py
```

## Running the App

```bash
$ cd gesis_rec_micro
$ docker build -t participant/random-rec .
$ docker run -p 5000:5000 participant/random-rec
```

## Test the app

<url> http://0.0.0.0:5000/index </url> (ignore errors if any)<br>
<url> http://0.0.0.0:5000/recommendation/datasets?item_id=gesis-ssoar-44449 </url>

```json
{
  "item_id": "gesis-ssoar-44449", 
  "itemlist": [
    "datasearch-httpwww-da-ra-deoaip--oaioai-da-ra-de542142", 
    "datasearch-httpwww-da-ra-deoaip--oaioai-da-ra-de462150", 
    "datasearch-httpseasy-dans-knaw-nloai--oaieasy-dans-knaw-nleasy-dataset51047", 
    "datasearch-httpwww-da-ra-deoaip--oaioai-da-ra-de438799", 
    "datasearch-httpwww-da-ra-deoaip--oaioai-da-ra-de585980", 
    "datasearch-httpsoai-datacite-orgoai--oaioai-datacite-org57070", 
    "datasearch-httpwww-da-ra-deoaip--oaioai-da-ra-de438015", 
    "datasearch-httpsoai-datacite-orgoai--oaioai-datacite-org15413441", 
    "datasearch-httpwww-da-ra-deoaip--oaioai-da-ra-de519570", 
    "datasearch-httpwww-da-ra-deoaip--oaioai-da-ra-de7788", 
    "datasearch-httpsdataverse-unc-eduoai--hdl1902-29H-792102", 
    "datasearch-httpwww-da-ra-deoaip--oaioai-da-ra-de549431", 
    "datasearch-httpwww-da-ra-deoaip--oaioai-da-ra-de449775", 
    "datasearch-httpwww-da-ra-deoaip--oaioai-da-ra-de450194", 
    "datasearch-httpwww-da-ra-deoaip--oaioai-da-ra-de656781", 
    "datasearch-httpwww-da-ra-deoaip--oaioai-da-ra-de434948", 
    "datasearch-httpwww-da-ra-deoaip--oaioai-da-ra-de433497", 
    "ZA7177", 
    "ZA8333", 
    "datasearch-httpseasy-dans-knaw-nloai--oaieasy-dans-knaw-nleasy-dataset35905"
  ], 
  "num_found": 20, 
  "page": 0, 
  "rpp": 20
}
```

<hr>
